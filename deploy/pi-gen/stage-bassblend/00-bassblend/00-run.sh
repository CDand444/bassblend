#!/bin/bash -e
# Install BassBlend into the image with the same script used on a running Pi,
# in --image mode (nothing is started; the service comes up on first boot).
# build-image.sh puts a clean copy of the BassBlend source in files/bassblend.
# (Not /tmp: pi-gen mounts an empty tmpfs over the image's /tmp while it works.)
install -d "${ROOTFS_DIR}/opt/bassblend-src"
cp -a files/bassblend/. "${ROOTFS_DIR}/opt/bassblend-src/"

on_chroot << EOF
set -e
bash /opt/bassblend-src/deploy/linux/install.sh --image
rm -rf /opt/bassblend-src
# keep the image small: pip and apt caches aren't needed on the card
rm -rf /root/.cache/pip
apt-get clean
EOF

# Say what this is on the boot partition, next to Raspberry Pi's own issue.txt
cat > "${ROOTFS_DIR}/boot/firmware/BASSBLEND.txt" << EOF
BassBlend ${BASSBLEND_VERSION:-dev}
Plug the Pi into your network with a cable, power it on, wait about two minutes,
then open http://bassblend.local:8765 on your phone or computer.
The first visit walks you through choosing a PIN.
EOF
