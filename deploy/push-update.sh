#!/usr/bin/env bash
# Send this folder's htTamer code to the Pi over SSH (an over-the-air update from your laptop).
#
#   deploy/push-update.sh            # push once
#   deploy/push-update.sh --watch    # keep pushing whenever a file changes (Ctrl+C to stop)
#
# Options / environment:
#   --host NAME      SSH host to update (default: bassblend, set up in ~/.ssh/config)
#   BASSBLEND_HOST   same as --host
#
# Sends the tracked and new (not ignored) files, including uncommitted edits,
# never data/, tools/, build output or keys. On the Pi, bassblend-update checks
# the code compiles, installs it, restarts only if Python changed, and rolls
# back by itself if the new version doesn't start.
set -euo pipefail
HOST="${BASSBLEND_HOST:-bassblend}"
WATCH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --watch) WATCH=1 ;;
    --host) HOST="$2"; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST")

files() {           # NUL-separated list of files to send (deleted-but-tracked files left out)
  git ls-files -z --cached --others --exclude-standard \
    | while IFS= read -r -d '' f; do
        case "$f" in data/*|tools/*|build/*|dist/*|.claude/*) continue ;; esac
        [ -f "$f" ] && printf '%s\0' "$f"
      done
}

version() {
  local v; v="$(git describe --tags --always --dirty 2>/dev/null || echo dev)"
  case "$v" in *-dirty) v="$v.$(date +%H%M%S)" ;; esac
  printf '%s' "$v"
}

push() {
  local v; v="$(version)"
  printf '\033[1m==> Pushing %s to %s\033[0m\n' "$v" "$HOST"
  # the updater travels first, so a Pi from an older image can always take the update
  "${SSH[@]}" 'sudo install -m 0755 /dev/stdin /usr/local/sbin/bassblend-update' < deploy/linux/bassblend-update
  files | tar -czf - --null -T - | "${SSH[@]}" "sudo /usr/local/sbin/bassblend-update '$v'"
}

signature() {       # changes whenever a file is edited, added or removed
  files | xargs -0 stat -c '%n %Y %s' 2>/dev/null | md5sum | cut -d' ' -f1
}

"${SSH[@]}" true 2>/dev/null || { echo "Can't reach $HOST over SSH. Is the Pi on? Try: ssh $HOST" >&2; exit 1; }
[ "$WATCH" -eq 1 ] || { push; exit; }
push || true
echo "Watching for changes (Ctrl+C to stop)…"
last="$(signature)"
while sleep 2; do
  now="$(signature)"
  if [ "$now" != "$last" ]; then
    sleep 1; last="$(signature)"         # let the editor finish saving
    push || echo "(push failed; will try again on the next change)" >&2
  fi
done
