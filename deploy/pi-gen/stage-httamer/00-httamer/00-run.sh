#!/bin/bash -e
# Install htTamer into the image with the same script used on a running Pi,
# in --image mode (nothing is started; the service comes up on first boot).
# build-image.sh puts a clean copy of the htTamer source in files/httamer.
# (Not /tmp: pi-gen mounts an empty tmpfs over the image's /tmp while it works.)
install -d "${ROOTFS_DIR}/opt/httamer-src"
cp -a files/httamer/. "${ROOTFS_DIR}/opt/httamer-src/"

on_chroot << EOF
set -e
bash /opt/httamer-src/deploy/linux/install.sh --image
rm -rf /opt/httamer-src
# keep the image small: pip and apt caches aren't needed on the card
rm -rf /root/.cache/pip
apt-get clean
EOF

# Say what this is on the boot partition, next to Raspberry Pi's own issue.txt
BB_VERSION="$(cat files/httamer/VERSION 2>/dev/null || echo dev)"
if [ -f files/httamer-config.json ]; then     # settings baked into this image: imported on first boot
  install -m 0644 files/httamer-config.json "${ROOTFS_DIR}/boot/firmware/httamer-config.json"
fi
cat > "${ROOTFS_DIR}/boot/firmware/HTTAMER.txt" << EOF
htTamer ${BB_VERSION}
Plug the Pi into your network with a cable, power it on, wait about two minutes,
then open http://httamer.local:8765 on your phone or computer.
The first visit walks you through choosing a PIN.

Already set htTamer up somewhere else? Copy your settings file (dashboard: System ->
Settings file -> Download) onto this drive as httamer-config.json before the
first start: it is loaded automatically, then removed from this drive.
EOF
