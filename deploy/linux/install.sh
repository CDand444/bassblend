#!/usr/bin/env bash
# htTamer setup for Linux (Raspberry Pi OS 64-bit, Debian 12+, Ubuntu 22.04+).
#
# Turns a fresh install into a htTamer box: installs what it needs, the
# minidsp-rs control tool, a USB permission rule for the miniDSP, and a service
# that starts the dashboard at boot on your home network (PIN protected).
#
#   sudo ./deploy/linux/install.sh            # normal: copies htTamer to /opt/httamer
#   sudo ./deploy/linux/install.sh --dev      # development: runs straight from this folder,
#                                             # as your own user, so edits apply after a restart
# Options:
#   --port N            dashboard port (default 8765)
#   --hostname NAME     rename this computer, so the dashboard is at http://NAME.local:PORT
#   --pin               choose the dashboard PIN here instead of in the browser
#   --image             used by the SD card image build (pi-gen): installs into an
#                       offline system, so nothing is started and no PIN is asked
#
# Without --pin, the first person to open the dashboard is walked through
# choosing a PIN (and the mic file, receiver and AI key) in the browser.
#
# Safe to run again: it updates what's there and keeps your data.
set -euo pipefail

MINIDSP_VERSION="0.1.12"
PORT=8765
DEV=0
IMAGE=0
SET_PIN=0
NEW_HOSTNAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dev) DEV=1 ;;
    --port) PORT="$2"; shift ;;
    --hostname) NEW_HOSTNAME="$2"; shift ;;
    --pin) SET_PIN=1 ;;
    --image) IMAGE=1 ;;
    --no-pin) SET_PIN=0 ;;                     # the default now; kept so older notes still work
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\nError: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run this with sudo"
[ "$DEV" -eq 1 ] || [ ! -d /opt/bassblend ] || die "this computer has a htTamer from before its files were renamed (in /opt/bassblend). Update it from its own page (Tools > Updates) twice: the second update moves it over."
if [ "$IMAGE" -eq 1 ]; then
  [ "$DEV" -eq 0 ] || die "--image and --dev can't be used together"
  SET_PIN=0
fi
live() { [ "$IMAGE" -eq 0 ]; }                 # false while building an SD card image
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[ -f "$SRC/subtune/__main__.py" ] || [ -f "$SRC/subtune/cli.py" ] || die "run this from inside the htTamer folder"
case "$PORT" in ''|*[!0-9]*) die "--port must be a number" ;; esac

if [ "$DEV" -eq 1 ]; then
  RUN_USER="${SUDO_USER:-}"
  [ -n "$RUN_USER" ] && [ "$RUN_USER" != "root" ] || die "--dev needs to be run with sudo from your normal user account"
  APP="$SRC"
  RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
  DATA="$RUN_HOME/.local/share/httamer"
  CONF="$RUN_HOME/.config/httamer"
  VENV="$RUN_HOME/.local/share/httamer-venv"
else
  RUN_USER="httamer"
  APP="/opt/httamer"
  DATA="/var/lib/httamer"
  CONF="/var/lib/httamer/config"
  VENV="/opt/httamer/venv"
fi

case "$(uname -m)" in
  aarch64|arm64) ARCH="aarch64"; MD_ASSET="minidsp.aarch64-unknown-linux-gnu.tar.gz" ;;
  x86_64|amd64)  ARCH="x86_64";  MD_ASSET="minidsp.x86_64-unknown-linux-gnu.tar.gz" ;;
  armv7l|armv6l) die "this is a 32-bit system. Install Raspberry Pi OS (64-bit): numpy and scipy need it" ;;
  *) die "unsupported processor: $(uname -m)" ;;
esac

say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip libportaudio2 avahi-daemon curl ca-certificates rsync >/dev/null

if [ "$DEV" -eq 0 ]; then
  say "Creating the 'httamer' service account"
  id -u httamer >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin httamer
  usermod -a -G audio,plugdev httamer

  say "Copying htTamer to $APP"
  mkdir -p "$APP"
  rsync -a --delete --exclude '.git/' --exclude 'data/' --exclude 'tools/' --exclude 'venv/' \
        --exclude '__pycache__/' --exclude '.claude/' "$SRC/" "$APP/"
  chown -R root:root "$APP"
else
  usermod -a -G audio,plugdev "$RUN_USER"
fi

say "Setting up Python in $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$SRC/requirements.txt"
[ "$DEV" -eq 1 ] && chown -R "$RUN_USER:" "$VENV"

say "Installing the miniDSP control tool (minidsp-rs $MINIDSP_VERSION, $ARCH)"
MD_DIR="$APP/tools/minidsp/linux-$ARCH"
if [ ! -x "$MD_DIR/minidsp" ] || ! "$MD_DIR/minidsp" --version 2>/dev/null | grep -q "$MINIDSP_VERSION"; then
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/md.tar.gz" "https://github.com/mrene/minidsp-rs/releases/download/v$MINIDSP_VERSION/$MD_ASSET"
  mkdir -p "$tmp/x" "$MD_DIR"
  tar -xzf "$tmp/md.tar.gz" -C "$tmp/x"
  bin="$(find "$tmp/x" -type f -name minidsp | head -n1)"
  [ -n "$bin" ] || die "the minidsp download didn't contain the minidsp tool"
  install -m 0755 "$bin" "$MD_DIR/minidsp"
  rm -rf "$tmp"
fi
[ "$DEV" -eq 1 ] && chown -R "$RUN_USER:" "$APP/tools"
# htTamer talks to the miniDSP directly; minidsp-rs's own background service would hold the USB device.
if systemctl list-unit-files minidspd.service >/dev/null 2>&1; then
  if live; then systemctl disable --now minidspd.service >/dev/null 2>&1 || true
  else systemctl disable minidspd.service >/dev/null 2>&1 || true; fi
fi

say "Letting htTamer use the miniDSP over USB without root"
cat > /etc/udev/rules.d/60-httamer-minidsp.rules <<'RULES'
# miniDSP (USB vendor 2752): control access for the plugdev group (htTamer's account is in it)
SUBSYSTEM=="usb", ATTRS{idVendor}=="2752", MODE="0660", GROUP="plugdev"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2752", MODE="0660", GROUP="plugdev"
RULES
if live; then
  udevadm control --reload-rules || true
  udevadm trigger --subsystem-match=usb --subsystem-match=hidraw || true
fi

say "Preparing the data folder ($DATA)"
mkdir -p "$DATA" "$CONF"
chown -R "$RUN_USER:" "$DATA" "$CONF"
chmod 700 "$CONF"

if [ -n "$NEW_HOSTNAME" ]; then
  say "Renaming this computer to $NEW_HOSTNAME"
  hostnamectl set-hostname "$NEW_HOSTNAME"
  sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$NEW_HOSTNAME/" /etc/hosts
  systemctl restart avahi-daemon || true
fi

say "Installing the htTamer service"
HARDEN="NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=$DATA
PrivateTmp=yes
ProtectHome=yes"
[ "$DEV" -eq 1 ] && HARDEN="NoNewPrivileges=yes
PrivateTmp=yes"
cat > /etc/systemd/system/httamer.service <<UNIT
[Unit]
Description=htTamer dashboard
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP
Environment=HTTAMER_DATA=$DATA
Environment=HTTAMER_CONFIG=$CONF
Environment=PYTHONUNBUFFERED=1
ExecStartPre=+/bin/sh $APP/deploy/linux/boot-import.sh $DATA $RUN_USER
ExecStart=$VENV/bin/python -m subtune serve --lan --port $PORT
Restart=on-failure
RestartSec=3
$HARDEN

[Install]
WantedBy=multi-user.target
UNIT
live && systemctl daemon-reload
ota_units() {   # in-app updates: the locked-down dashboard drops a download in $1/update, a root path unit installs it
  install -m 0755 "$APP/deploy/linux/httamer-ota" /usr/local/sbin/httamer-ota
  install -d -m 0755 "$1/update"
  chown --reference="$1" "$1/update" 2>/dev/null || true
  cat > /etc/systemd/system/httamer-ota.path <<OTAP
[Unit]
Description=htTamer: install a downloaded update

[Path]
PathExists=$1/update/incoming.version
Unit=httamer-ota.service

[Install]
WantedBy=multi-user.target
OTAP
  cat > /etc/systemd/system/httamer-ota.service <<OTAS
[Unit]
Description=htTamer: install a downloaded update

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/httamer-ota $1
OTAS
}
if [ "$DEV" -eq 0 ]; then                     # over-the-air updates pushed from your computer (deploy/push-update.sh)
  install -m 0755 "$APP/deploy/linux/httamer-update" /usr/local/sbin/httamer-update
  ota_units "$DATA"                              # ... and from GitHub, started in the app
  live && systemctl daemon-reload
  systemctl enable httamer-ota.path >/dev/null 2>&1 || true
  live && systemctl start httamer-ota.path || true
fi
systemctl enable httamer.service >/dev/null

pin_is_set() { [ -s "$CONF/auth.json" ] && grep -q pin_hash "$CONF/auth.json"; }
if [ "$SET_PIN" -eq 1 ] && ! pin_is_set; then
  say "Choose a PIN for the dashboard"
  echo "Anyone on your network who opens htTamer will need it. Use 6 or more characters."
  sudo -u "$RUN_USER" env HTTAMER_DATA="$DATA" HTTAMER_CONFIG="$CONF" \
      bash -c "cd '$APP' && '$VENV/bin/python' -m subtune set-pin"
fi

if ! live; then
  say "htTamer is installed in the image; it starts on first boot"
  exit 0
fi
systemctl restart httamer.service
sleep 2
systemctl is-active --quiet httamer.service || die "the service didn't start. See: journalctl -u httamer -n 50"
say "Done"
echo "Open:  http://$(hostname).local:$PORT   (or http://$(hostname -I | awk '{print $1}'):$PORT)"
if ! pin_is_set; then
  echo "The first time you open it, htTamer asks you to choose a PIN. Do that straight away:"
  echo "until a PIN is chosen, anyone on your network who opens the page could choose it."
fi
echo
echo "Your tunes and settings live in $DATA. To bring them over from another htTamer,"
echo "download a settings file there (menu: Settings file) and import it here."
echo "Logs:  journalctl -u httamer -f      Restart:  sudo systemctl restart httamer"
