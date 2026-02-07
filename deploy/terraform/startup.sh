#!/bin/bash
# VM bootstrap script — runs once on first boot via GCE metadata_startup_script.
set -e

# Install Docker CE
apt-get update
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Enable and start Docker
systemctl enable docker
systemctl start docker

# Add default user to docker group (GCE uses the SSH user, typically your gcloud username)
# The actual username is set at SSH time; adding a group membership here covers the common case.
if id -u aletheia &>/dev/null; then
    usermod -aG docker aletheia
fi

# Install git (should already be present on Debian 12, but ensure)
apt-get install -y git

echo "Startup script complete."
