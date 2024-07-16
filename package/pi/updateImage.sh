#!/bin/bash

# Define the mount directory and machine name
MOUNT_DIR="/mnt/pi_root"
MACHINE_NAME="pi-container"

# Find the first .img.xz file
IMAGE_XZ=$(find . -type f -name "*.img.xz" | head -n 1)

# Check if an .img.xz file was found
if [ -z "$IMAGE_XZ" ]; then
    echo "No .img.xz file found."
    exit 1
fi

# Define the decompressed image file name based on the compressed file name
IMAGE="${IMAGE_XZ%.xz}"

# Step 1: Check if the image file exists and decompress it
if [ ! -f "$IMAGE" ]; then
    if [ -f "$IMAGE_XZ" ]; then
        echo "Decompressing the image using 7z..."
        7z x "$IMAGE_XZ" -o$(dirname "$IMAGE_XZ")
        if [ $? -ne 0 ]; then
            echo "Failed to decompress the image. Ensure that 7z is installed and functional."
            exit 1
        fi
    else
        echo "Image file $IMAGE_XZ does not exist."
        exit 1
    fi
else
    echo "Image already decompressed."
fi

# Step 2: Identify the start sector of the root partition using fdisk
# The root partition is typically the second partition (especially for Pi images), hence the 'tail -n 1' to pick the last partition listed
START_SECTOR=$(fdisk -l $IMAGE | grep -oP 'img\d+\s+\K\d+' | tail -n 1)
if [ -z "$START_SECTOR" ]; then
    echo "Failed to find the start sector of the root partition."
    exit 1
fi

# Calculate the offset
OFFSET=$(($START_SECTOR * 512))

# Step 3: Prepare the mount directory
if [ ! -d "$MOUNT_DIR" ]; then
    mkdir -p "$MOUNT_DIR"
fi

# Step 4: Mount the image
echo "Mounting the root filesystem at $MOUNT_DIR..."
mount -o loop,offset=$OFFSET $IMAGE $MOUNT_DIR
if [ $? -ne 0 ]; then
    echo "Failed to mount the root filesystem."
    exit 1
fi

echo "Root filesystem mounted successfully. You can now modify the filesystem at $MOUNT_DIR."
echo "Remember to unmount when done with 'sudo umount $MOUNT_DIR'"

# Mount the directory with the install files
mkdir -p $MOUNT_DIR/install_files
mount --bind /files $MOUNT_DIR/install_files


# Step 5: Boot the container using systemd-nspawn and install the package in a new tmux session
echo "Booting the container using systemd-nspawn..."
systemd-nspawn --register=no --keep-unit --machine=MACHINENAME -D /mnt/pi_root --as-pid2 -- \
    apt install -y /install_files/r3onboard.deb
