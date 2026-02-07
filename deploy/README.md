# Aletheia Deployment

Deploy Aletheia to a GCP e2-micro VM with private access via Tailscale.

## Architecture

```
GitHub Actions (build) --> GHCR (image registry)
You (Tailscale) --------> GCP e2-micro (Tailscale) --> Podman --> uvicorn:8000
```

- Container image built via GitHub Actions, pulled from GHCR on the VM
- No public web exposure; access is via Tailscale mesh VPN only
- SSH is the only port open on the GCP firewall (for initial setup)
- Data persists in a Podman named volume, backed by a git repo

## Prerequisites

- [GCP account](https://cloud.google.com/) with billing enabled
- [Tailscale account](https://tailscale.com/) (free personal tier)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated
- [Terraform CLI](https://developer.hashicorp.com/terraform/install) >= 1.5
- SSH deploy key for your `aletheia-data` repo

### Create a deploy key

```bash
ssh-keygen -t ed25519 -f ~/.ssh/aletheia_deploy -N "" -C "aletheia-deploy"
# Add the public key (~/.ssh/aletheia_deploy.pub) as a deploy key in your
# aletheia-data repo settings on GitHub (read-write access for sync)
```

## 1. Local Testing

Test the container locally before deploying to GCP.

```bash
cd deploy/docker

# Create .env from example
cp .env.example .env
# Edit .env with your repo URL

# Register your deploy key as a podman secret
podman secret create deploy_key ~/.ssh/aletheia_deploy

# Build locally (CI builds from GHCR are used in production)
podman build -t aletheia -f Dockerfile ../..

# Run
podman-compose up

# Verify
curl http://localhost:8000/health   # {"status": "ok"}
# Open http://localhost:8000/review in browser
```

To stop: `podman-compose down` (data persists in the named volume).

## 2. Deploy to GCP

### Provision the VM

```bash
cd deploy/terraform

# Create tfvars from example
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your GCP project ID

# Deploy
terraform init
terraform plan     # Review resources
terraform apply    # Create VM + firewall + static IP
```

Note the output IP and SSH command.

### Set up the VM

```bash
# SSH into the instance
gcloud compute ssh aletheia --zone=us-central1-a

# Wait for startup script to finish (Podman install)
sudo journalctl -u google-startup-scripts -f
# Look for "Startup script complete." then Ctrl+C
```

### Install Tailscale

```bash
# On the VM:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up   # Opens a URL — authenticate in your browser
```

After this, the VM is accessible via its Tailscale IP (e.g., `100.x.y.z`).

### Deploy the app

```bash
# Copy your deploy key to the VM (from your local machine):
gcloud compute scp ~/.ssh/aletheia_deploy aletheia:~/.ssh/aletheia_deploy --zone=us-central1-a

# SSH into the VM:
gcloud compute ssh aletheia --zone=us-central1-a

# Register the deploy key as a podman secret
podman secret create deploy_key ~/.ssh/aletheia_deploy

# Clone the app repo
git clone https://github.com/choo8/aletheia.git ~/aletheia
cd ~/aletheia/deploy/docker

# Create .env
cat > .env << 'EOF'
ALETHEIA_DATA_REPO=git@github.com:youruser/aletheia-data.git
EOF

# Pull and start the app
podman-compose pull
podman-compose up -d

# Verify
curl http://localhost:8000/health
```

Access the app at `http://<tailscale-ip>:8000` from any device on your Tailscale network.

## 3. Operations

### View logs

```bash
podman logs -f aletheia
```

### Sync reviews (commit + push to aletheia-data)

```bash
podman exec aletheia aletheia sync
```

### Automated sync via cron

```bash
# On the VM, add to crontab:
crontab -e
# Sync every hour:
0 * * * * podman exec aletheia aletheia sync >> /tmp/aletheia-sync.log 2>&1
```

### Pull latest cards

```bash
podman exec aletheia bash -c "cd /data && git pull --ff-only"
# Reindex after pulling new cards:
podman exec aletheia python -c "
from aletheia.core.storage import AletheiaStorage
from pathlib import Path
import os
s = AletheiaStorage(Path(os.environ['ALETHEIA_DATA_DIR']), Path(os.environ['ALETHEIA_STATE_DIR']))
print(f'Indexed {s.reindex_all()} cards.')
"
```

### Update app (pull new image from GHCR)

```bash
cd ~/aletheia/deploy/docker
podman-compose pull
podman-compose up -d
```

### Destroy the volume (lose all data)

```bash
podman-compose -f ~/aletheia/deploy/docker/docker-compose.yml down -v
```

## 4. Tear Down

```bash
cd deploy/terraform
terraform destroy
```

This removes the VM, static IP, and firewall rules. The Podman volume data is gone with the VM.
Your `aletheia-data` git repo remains safe on GitHub.
