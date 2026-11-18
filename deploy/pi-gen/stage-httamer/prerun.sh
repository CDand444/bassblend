#!/bin/bash -e
# Start from the finished Raspberry Pi OS Lite (stage2) root filesystem.
if [ ! -d "${ROOTFS_DIR}" ]; then
	copy_previous
fi
