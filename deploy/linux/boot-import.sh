#!/bin/sh
# Runs as root just before the BassBlend service starts (ExecStartPre=+).
# If a settings file was copied onto the SD card's boot drive, hand it to BassBlend
# (which imports it on start) and take it off the boot drive: it may hold the PIN
# hash or the API key, and the boot drive is readable by anyone with the card.
#   boot-import.sh <data folder> <service user>
DATA="$1"; RUN_USER="$2"
for f in /boot/firmware/bassblend-config.json /boot/bassblend-config.json; do
  [ -f "$f" ] || continue
  install -o "$RUN_USER" -m 0600 "$f" "$DATA/import-pending.json" && rm -f "$f"
  echo "BassBlend: settings file found on the boot drive; importing it"
  break
done
exit 0
