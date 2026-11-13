#!/usr/bin/env bash
# Build the BassBlend SD card image with pi-gen, inside Docker.
# Works from Linux, macOS, or Git Bash on Windows with Docker Desktop running.
#
#   deploy/pi-gen/build-image.sh            # result: dist/bassblend-<version>.img.xz
#   RESUME=1 deploy/pi-gen/build-image.sh   # after a failed BassBlend stage: reuse the finished
#                                           # Raspberry Pi OS stages (saves ~35 minutes)
#
# Takes 1-2 hours (most of it is building for the Pi's ARM processor through emulation).
# The image contains the BassBlend files as they are in this folder right now
# (tracked files, including uncommitted edits), never your data/ folder or keys.
set -euo pipefail
# Git Bash on Windows rewrites arguments that look like Unix paths. Container paths
# (/pi-gen/...) must not be rewritten, so docker runs with MSYS_NO_PATHCONV=1, and host
# paths are handed to it in Windows form (C:/...) via hostpath.
dk() { MSYS_NO_PATHCONV=1 docker "$@"; }
hostpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

PIGEN_REPO="https://github.com/RPi-Distro/pi-gen.git"
PIGEN_COMMIT="c0d2c9f"                          # arm64 branch, Nov 6 2026 (trixie)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WORK="${BASSBLEND_BUILD_DIR:-$ROOT/build/pi-gen}"
OUT="$ROOT/dist"
NAME="bassblend_pigen"
VERSION="$(cd "$ROOT" && git describe --tags --always --dirty 2>/dev/null || date +%Y%m%d)"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
dk info >/dev/null 2>&1 || { echo "Docker isn't running. Start Docker Desktop and try again." >&2; exit 1; }
RESUME="${RESUME:-0}"
HAVE="$(dk ps -aq --filter "name=^${NAME}$")"
if [ -n "$HAVE" ] && [ "$RESUME" != "1" ]; then
  echo "A previous build ($NAME) exists. Resume it with RESUME=1, or start over after:  docker rm -f $NAME" >&2; exit 1
fi
if [ -z "$HAVE" ] && [ "$RESUME" = "1" ]; then
  echo "Nothing to resume; running a full build." >&2; RESUME=0
fi

say "Getting pi-gen ($PIGEN_COMMIT)"
if [ ! -d "$WORK/.git" ]; then
  rm -rf "$WORK"; mkdir -p "$(dirname "$WORK")"
  git -c core.autocrlf=false clone -q -b arm64 "$PIGEN_REPO" "$WORK"
fi
git -C "$WORK" -c core.autocrlf=false fetch -q origin arm64
git -C "$WORK" -c advice.detachedHead=false checkout -q -f "$PIGEN_COMMIT"
git -C "$WORK" clean -qfdx -e work -e deploy
if [ "$RESUME" = "1" ]; then                    # the Raspberry Pi OS stages are already built in the container
  for st in stage0 stage1 stage2; do touch "$WORK/$st/SKIP"; done
fi

say "Adding the BassBlend stage and settings"
rm -f "$WORK/stage2/EXPORT_IMAGE"              # only export the finished BassBlend image
cp "$HERE/config" "$WORK/config"
echo "BASSBLEND_VERSION=\"$VERSION\"" >> "$WORK/config"
rm -rf "$WORK/stage-bassblend"
cp -R "$HERE/stage-bassblend" "$WORK/stage-bassblend"
SRC="$WORK/stage-bassblend/00-bassblend/files/bassblend"
mkdir -p "$SRC"
(cd "$ROOT" && git ls-files -z --cached --others --exclude-standard) | (cd "$ROOT" && xargs -0 tar -cf - --) | tar -xf - -C "$SRC"
rm -rf "$SRC/build" "$SRC/dist" "$SRC/data" "$SRC/tools"
# shell scripts must have Unix line endings, whatever the checkout did
find "$WORK/stage-bassblend" "$WORK/config" -type f \( -name '*.sh' -o -name config -o -name EXPORT_IMAGE \) \
  -exec sed -i 's/\r$//' {} +
chmod +x "$WORK"/stage-bassblend/*.sh "$WORK"/stage-bassblend/*/*.sh "$SRC/deploy/linux/install.sh"

say "Building the pi-gen container"
dk build -q --build-arg BASE_IMAGE=docker.io/debian:trixie -t pi-gen "$(hostpath "$WORK")" >/dev/null

if [ "$RESUME" = "1" ]; then
  RUN_AS="${NAME}_cont"; RUN_OPTS="--rm --volumes-from=$NAME"
  say "Resuming: building only the BassBlend stage. Progress: docker logs -f $RUN_AS"
else
  RUN_AS="$NAME"; RUN_OPTS=""
  say "Building the image (1-2 hours). Progress: docker logs -f $NAME"
fi
# shellcheck disable=SC2086
dk run --name "$RUN_AS" $RUN_OPTS --privileged -e "GIT_HASH=$PIGEN_COMMIT" pi-gen bash -e -o pipefail -c '
  mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc || true
  if ! arch-test -c "$(mktemp -d)" arm64; then
    [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64-rpi ] || echo -1 > /proc/sys/fs/binfmt_misc/qemu-aarch64-rpi
    echo ":qemu-aarch64-rpi:M::\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\xb7\x00:\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff:/usr/bin/qemu-aarch64:F" > /proc/sys/fs/binfmt_misc/register
    trap "echo -1 > /proc/sys/fs/binfmt_misc/qemu-aarch64-rpi" EXIT
  fi
  cd /pi-gen
  ./build.sh
  cp work/*/build.log deploy/ || true
'

say "Copying the image out"
mkdir -p "$OUT"
rm -rf "$WORK/deploy"
dk cp "$NAME:/pi-gen/deploy" "$(hostpath "$WORK/deploy")"
dk rm -v "$NAME" >/dev/null
img="$(ls "$WORK"/deploy/*.img.xz | head -n1)"
cp "$img" "$OUT/bassblend-$VERSION.img.xz"
cp "$WORK"/deploy/build.log "$OUT/bassblend-$VERSION.build.log" 2>/dev/null || true
( cd "$OUT" && sha256sum "bassblend-$VERSION.img.xz" > "bassblend-$VERSION.img.xz.sha256" )
say "Done: dist/bassblend-$VERSION.img.xz"
ls -lh "$OUT"
