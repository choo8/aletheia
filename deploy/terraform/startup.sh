#!/bin/bash
# VM bootstrap script — runs once on first boot via GCE metadata_startup_script.
set -e

apt-get update

# Install Podman + podman-compose
apt-get install -y podman python3-pip git
pip3 install --break-system-packages podman-compose

echo "Startup script complete."
