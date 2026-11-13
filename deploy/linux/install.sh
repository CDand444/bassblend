#!/usr/bin/env bash
# BassBlend setup for Linux (Raspberry Pi OS 64-bit, Debian 12+, Ubuntu 22.04+).
#
# Turns a fresh install into a BassBlend box: installs what it needs, the
# minidsp-rs control tool, a USB permission rule for the miniDSP, and a service
# that starts the dashboard at boot on your home network (PIN protected).
#
#   sudo ./deploy/linux/install.sh            # normal: copies BassBlend to /opt/bassblend
#   sudo ./deploy/linux/install.sh --dev      # development: runs straight from this folder,
#                                             # as your own user, so edits apply after a restart
# Options:
#   --port N            dashboard port (default 8765)
#   --hostname NAME     rename this computer, so the dashboard is at http://NAME.local:PORT
#   --no-pin            skip the PIN prompt (the service won't start until a PIN is set)
#
# Safe to run again: it updates what's there and keeps your data.
set -euo pipefail

MINIDSP_VERSION="0.1.12"
PORT=8765
DEV=0
SET_PIN=1
NEW_HOSTNAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dev) DEV=1 ;;
    --port) PORT="$2"; shift ;;
    --hostname) NEW_HOSTNAME="$2"; shift ;;
    --no-pin) SET_PIN=0 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\nError: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run this with sudo"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[ -f "$SRC/subtune/__main__.py" ] || [ -f "$SRC/subtune/cli.py" ] || die "run this from inside the BassBlend folder"
case "$PORT" in ''|*[!0-9]*) die "--port must be a number" ;; esac

if [ "$DEV" -eq 1 ]; then
  RUN_USER="${SUDO_USER:-}"
  [ -n "$RUN_USER" ] && [ "$RUN_USER" != "root" ] || die "--dev needs to be run with sudo from your normal user account"
  APP="$SRC"
  RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
  DATA="$RUN_HOME/.local/share/bassblend"
  CONF="$RUN_HOME/.config/bassblend"
  VENV="$RUN_HOME/.local/share/bassblend-venv"
else
  RUN_USER="bassblend"
  APP="/opt/bassblend"
  DATA="/var/lib/bassblend"
  CONF="/var/lib/bassblend/config"
  VENV="/opt/bassblend/venv"
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
  say "Creating the 'bassblend' service account"
  id -u bassblend >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin bassblend
  usermod -a -G audio,plugdev bassblend

  say "Copying BassBlend to $APP"
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
# BassBlend talks to the miniDSP directly; minidsp-rs's own background service would hold the USB device.
if systemctl list-unit-files minidspd.service >/dev/null 2>&1; then
  systemctl disable --now minidspd.service >/dev/null 2>&1 || true
fi

say "Letting BassBlend use the miniDSP over USB without root"
cat > /etc/udev/rules.d/60-bassblend-minidsp.rules <<'RULES'
# miniDSP (USB vendor 2752): control access for the plugdev group (BassBlend's account is in it)
SUBSYSTEM=="usb", ATTRS{idVendor}=="2752", MODE="0660", GROUP="plugdev"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2752", MODE="0660", GROUP="plugdev"
RULES
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --subsystem-match=hidraw || true

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

say "Installing the BassBlend service"
HARDEN="NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=$DATA
PrivateTmp=yes
ProtectHome=yes"
[ "$DEV" -eq 1 ] && HARDEN="NoNewPrivileges=yes
PrivateTmp=yes"
cat > /etc/systemd/system/bassblend.service <<UNIT
[Unit]
Description=BassBlend dashboard
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP
Environment=BASSBLEND_DATA=$DATA
Environment=BASSBLEND_CONFIG=$CONF
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/python -m subtune serve --lan --port $PORT
Restart=on-failure
RestartSec=3
$HARDEN

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable bassblend.service >/dev/null

pin_is_set() { [ -s "$CONF/auth.json" ] && grep -q pin_hash "$CONF/auth.json"; }
if [ "$SET_PIN" -eq 1 ] && ! pin_is_set; then
  say "Choose a PIN for the dashboard"
  echo "Anyone on your network who opens BassBlend will need it. Use 6 or more characters."
  sudo -u "$RUN_USER" env BASSBLEND_DATA="$DATA" BASSBLEND_CONFIG="$CONF" \
      bash -c "cd '$APP' && '$VENV/bin/python' -m subtune set-pin"
fi

if pin_is_set; then
  systemctl restart bassblend.service
  sleep 2
  systemctl is-active --quiet bassblend.service || die "the service didn't start. See: journalctl -u bassblend -n 50"
  say "Done"
  echo "Open:  http://$(hostname).local:$PORT   (or http://$(hostname -I | awk '{print $1}'):$PORT)"
else
  say "Almost done"
  echo "Set a PIN, then start the service:"
  echo "  sudo -u $RUN_USER env BASSBLEND_DATA=$DATA BASSBLEND_CONFIG=$CONF $VENV/bin/python -m subtune set-pin"
  echo "  sudo systemctl start bassblend"
fi
echo
echo "Your tunes and settings live in $DATA. To bring them over from Windows, copy the"
echo "contents of the BassBlend 'data' folder there (then: sudo chown -R $RUN_USER: $DATA)"
echo "and upload the mic calibration file again from Setup checklist."
echo "Logs:  journalctl -u bassblend -f      Restart:  sudo systemctl restart bassblend"
