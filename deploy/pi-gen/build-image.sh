#!/usr/bin/env bash
# Build the htTamer SD card image with pi-gen, inside Docker.
# Works from Linux, macOS, or Git Bash on Windows with Docker Desktop running.
#
#   deploy/pi-gen/build-image.sh            # result: dist/httamer-<version>.img.xz
#   HTTAMER_SETTINGS=my-settings.json deploy/pi-gen/build-image.sh
#                                           # also put a settings file on the card: imported on first boot
#   RESUME=1 deploy/pi-gen/build-image.sh   # after a failed htTamer stage: reuse the finished
#                                           # Raspberry Pi OS stages of that failed build
#   BASE_REFRESH=1 deploy/pi-gen/build-image.sh  # rebuild the cached Raspberry Pi OS now (security updates)
#
# The first build takes about 25 minutes (most of it builds Raspberry Pi OS for the Pi's ARM processor
# through emulation). That finished OS is kept as a cache (container httamer_pigen_base), so later
# builds only add htTamer: about 8 minutes. The cache is rebuilt by itself after BASE_MAX_DAYS.
# The image contains the htTamer files as they are in this folder right now
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
WORK="${HTTAMER_BUILD_DIR:-$ROOT/build/pi-gen}"
OUT="$ROOT/dist"
NAME="httamer_pigen"
VERSION="${VERSION:-$(cd "$ROOT" && git describe --tags --always --dirty 2>/dev/null || date +%Y%m%d)}"   # VERSION=v1.2.3 to name it yourself

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
dk info >/dev/null 2>&1 || { echo "Docker isn't running. Start Docker Desktop and try again." >&2; exit 1; }
RESUME="${RESUME:-0}"
BASE="${NAME}_base"
BASE_MAX_DAYS="${BASE_MAX_DAYS:-30}"
USE_BASE=0
if [ -n "$(dk ps -aq --filter "name=^${BASE}$")" ] && [ "${BASE_REFRESH:-0}" != "1" ] && [ "$RESUME" != "1" ]; then
  created="$(dk inspect -f '{{.Created}}' "$BASE")"
  age=$(( ( $(date +%s) - $(date -d "$created" +%s) ) / 86400 ))
  if [ "$age" -lt "$BASE_MAX_DAYS" ]; then USE_BASE=1
  else echo "The cached Raspberry Pi OS is $age days old: rebuilding it (security updates)."; fi
fi
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
if [ "$RESUME" = "1" ] || [ "$USE_BASE" = "1" ]; then   # the Raspberry Pi OS stages are already built
  for st in stage0 stage1 stage2; do touch "$WORK/$st/SKIP"; done
fi

say "Adding the htTamer stage and settings"
rm -f "$WORK/stage2/EXPORT_IMAGE"              # only export the finished htTamer image
cp "$HERE/config" "$WORK/config"
echo "HTTAMER_VERSION=\"$VERSION\"" >> "$WORK/config"
rm -rf "$WORK/stage-httamer"
cp -R "$HERE/stage-httamer" "$WORK/stage-httamer"
SRC="$WORK/stage-httamer/00-httamer/files/httamer"
mkdir -p "$SRC"
# every tracked or new file, minus the development-only ones marked export-ignore in .gitattributes
(cd "$ROOT" && git ls-files -z --cached --others --exclude-standard \
   | git check-attr -z --stdin export-ignore \
   | awk 'BEGIN { RS = "\0" } NR % 3 == 1 { f = $0 } NR % 3 == 0 && $0 != "set" { printf "%s%c", f, 0 }') \
  | (cd "$ROOT" && xargs -0 tar -cf - --) | tar -xf - -C "$SRC"
rm -rf "$SRC/build" "$SRC/dist" "$SRC/data" "$SRC/tools"
printf '%s\n' "$VERSION" > "$SRC/VERSION"
CFG="$WORK/stage-httamer/00-httamer/files/httamer-config.json"
if [ -n "${HTTAMER_SETTINGS:-}" ]; then      # bake a settings file in: imported on first boot
  [ -f "$HTTAMER_SETTINGS" ] || { echo "HTTAMER_SETTINGS: no such file: $HTTAMER_SETTINGS" >&2; exit 1; }
  cp "$HTTAMER_SETTINGS" "$CFG"
  echo "Including settings file $(basename "$HTTAMER_SETTINGS") (anyone with the image can read it)"
fi
# shell scripts must have Unix line endings, whatever the checkout did
find "$WORK/stage-httamer" "$WORK/config" -type f \( -name '*.sh' -o -name config -o -name EXPORT_IMAGE \) \
  -exec sed -i 's/\r$//' {} +
chmod +x "$WORK"/stage-httamer/*.sh "$WORK"/stage-httamer/*/*.sh "$SRC/deploy/linux/install.sh"

say "Building the pi-gen container"
dk build -q --build-arg BASE_IMAGE=docker.io/debian:trixie -t pi-gen "$(hostpath "$WORK")" >/dev/null

FROM="$NAME"
if [ "$USE_BASE" = "1" ]; then
  FROM="$BASE"; RUN_AS="${NAME}_cont"; RUN_OPTS="--rm --volumes-from=$BASE"
  say "Using the cached Raspberry Pi OS: building only htTamer (about 8 minutes). Progress: docker logs -f $RUN_AS"
elif [ "$RESUME" = "1" ]; then
  RUN_AS="${NAME}_cont"; RUN_OPTS="--rm --volumes-from=$NAME"
  say "Resuming: building only the htTamer stage. Progress: docker logs -f $RUN_AS"
else
  RUN_AS="$NAME"; RUN_OPTS=""
  say "Building the image with a fresh Raspberry Pi OS (about 25 minutes). Progress: docker logs -f $NAME"
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
  rm -rf /pi-gen/deploy/* 2>/dev/null || true      # only the new image ends up in deploy/
  ./build.sh
  cp work/*/build.log deploy/ || true
'

say "Copying the image out"
mkdir -p "$OUT"
rm -rf "$WORK/deploy"
dk cp "$FROM:/pi-gen/deploy" "$(hostpath "$WORK/deploy")"
if [ "$FROM" = "$NAME" ]; then                   # a full (or resumed) build: keep its finished OS as the cache
  [ -z "$(dk ps -aq --filter "name=^${BASE}$")" ] || dk rm -v "$BASE" >/dev/null
  dk rename "$NAME" "$BASE"
fi
img="$(ls "$WORK"/deploy/*.img.xz | head -n1)"
cp "$img" "$OUT/httamer-$VERSION.img.xz"
cp "$WORK"/deploy/build.log "$OUT/httamer-$VERSION.build.log" 2>/dev/null || true
( cd "$OUT" && sha256sum "httamer-$VERSION.img.xz" > "httamer-$VERSION.img.xz.sha256" )
say "Done: dist/httamer-$VERSION.img.xz"
ls -lh "$OUT"
