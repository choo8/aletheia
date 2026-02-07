# Aletheia Deployment

Deploy Aletheia to a GCP e2-micro VM with private access via Tailscale.

## Architecture

```
You (Tailscale) --> GCP e2-micro (Tailscale) --> Docker --> uvicorn:8000
```

- No public web exposure; access is via Tailscale mesh VPN only
- SSH is the only port open on the GCP firewall (for initial setup)
- Data persists in a Docker named volume, backed by a git repo

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
# aletheia-data repo settings on GitHub (read-only is fine for pulling)
```

## 1. Local Testing with Docker

Test the container locally before deploying to GCP.

```bash
cd deploy/docker

# Create .env from example
cp .env.example .env
# Edit .env with your repo URL and deploy key path

# Build and run
docker compose up --build

# Verify
curl http://localhost:8000/health   # {"status": "ok"}
# Open http://localhost:8000/review in browser
```

To stop: `docker compose down` (data persists in the named volume).

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

# Wait for startup script to finish (Docker install)
sudo journalctl -u google-startup-scripts -f
# Look for "Startup script complete."

# Add your user to docker group
sudo usermod -aG docker $USER
# Log out and back in for group to take effect
exit
gcloud compute ssh aletheia --zone=us-central1-a
```

### Install Tailscale

```bash
# On the VM:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=tskey-auth-XXXXX  # One-time auth key from Tailscale admin
```

After this, the VM is accessible via its Tailscale IP (e.g., `100.x.y.z`).

### Deploy the app

```bash
# On the VM:
git clone https://github.com/youruser/aletheia.git ~/aletheia
cd ~/aletheia/deploy/docker

# Create .env
cat > .env << 'EOF'
ALETHEIA_DATA_REPO=git@github.com:youruser/aletheia-data.git
DEPLOY_KEY_PATH=/home/youruser/.ssh/aletheia_deploy
EOF

# Copy your deploy key to the VM (from your local machine):
# gcloud compute scp ~/.ssh/aletheia_deploy aletheia:~/.ssh/aletheia_deploy --zone=us-central1-a

# Start the app
docker compose up -d --build

# Verify
curl http://localhost:8000/health
```

Access the app at `http://<tailscale-ip>:8000` from any device on your Tailscale network.

## 3. Operations

### View logs

```bash
docker logs -f aletheia
```

### Sync reviews (commit + push to aletheia-data)

```bash
docker exec aletheia aletheia sync
```

### Automated sync via cron

```bash
# On the VM, add to crontab:
crontab -e
# Sync every hour:
0 * * * * docker exec aletheia aletheia sync >> /tmp/aletheia-sync.log 2>&1
```

### Pull latest cards

```bash
docker exec aletheia bash -c "cd /data && git pull --ff-only"
# Reindex after pulling new cards:
docker exec aletheia python -c "
from aletheia.core.storage import AletheiaStorage
from pathlib import Path
import os
s = AletheiaStorage(Path(os.environ['ALETHEIA_DATA_DIR']), Path(os.environ['ALETHEIA_STATE_DIR']))
print(f'Indexed {s.reindex_all()} cards.')
"
```

### Update app code

```bash
cd ~/aletheia
git pull
docker compose -f deploy/docker/docker-compose.yml up -d --build
```

### Rebuild from scratch

```bash
docker compose -f deploy/docker/docker-compose.yml down
docker compose -f deploy/docker/docker-compose.yml up -d --build
# Data persists in the named volume; only the app container is rebuilt
```

### Destroy the volume (lose all data)

```bash
docker compose -f deploy/docker/docker-compose.yml down -v
```

## 4. Tear Down

```bash
cd deploy/terraform
terraform destroy
```

This removes the VM, static IP, and firewall rules. The Docker volume data is gone with the VM.
Your `aletheia-data` git repo remains safe on GitHub.
