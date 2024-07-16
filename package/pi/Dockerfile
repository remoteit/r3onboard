# Use the latest Ubuntu image
FROM ubuntu:latest

# Set a maintainer label: replace with your name and email
LABEL maintainer="Evan Bowers <evan@remote.it>"

# Update the package list and install necessary packages
RUN apt-get update && apt-get install -y \
    fdisk \
    mount \
    qemu-user-static \
    binfmt-support \
    debootstrap \
    kpartx \
    parted \
    e2fsprogs \
    dosfstools \
    p7zip-full \
    systemd-container \
    tmux \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy qemu-arm-static to the image so ARM binaries can be executed
COPY --from=multiarch/qemu-user-static /usr/bin/qemu-arm-static /usr/bin

# Set up binfmt support
RUN update-binfmts --enable qemu-arm

# Create a directory to mount the Raspberry Pi images
RUN mkdir /images

RUN mkdir /files

# Copy files directory
COPY files /files
 
# Set work directory
WORKDIR /images

# Command to run the image script using shell
CMD ["/bin/bash", "/files/updateImage.sh"]

# # Set the entrypoint to bash
# ENTRYPOINT ["/bin/bash"]
