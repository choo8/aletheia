#!/bin/bash
set -e

ALETHEIA_HOME=$(eval echo ~aletheia)

# --- SSH deploy key setup (via podman secret) ---
if [ -f /run/secrets/deploy_key ]; then
    mkdir -p "$ALETHEIA_HOME/.ssh"
    cp /run/secrets/deploy_key "$ALETHEIA_HOME/.ssh/id_ed25519"
    chmod 600 "$ALETHEIA_HOME/.ssh/id_ed25519"
    chown -R aletheia:aletheia "$ALETHEIA_HOME/.ssh"
    ssh-keyscan -t ed25519 github.com >> "$ALETHEIA_HOME/.ssh/known_hosts" 2>/dev/null
    echo "SSH deploy key configured."
fi

# --- Clone or pull data repo (as aletheia user) ---
if [ -n "$ALETHEIA_DATA_REPO" ] && [ ! -d /data/.git ]; then
    echo "Cloning data repo: $ALETHEIA_DATA_REPO"
    gosu aletheia git clone "$ALETHEIA_DATA_REPO" /data
elif [ -d /data/.git ]; then
    echo "Pulling latest data..."
    gosu aletheia bash -c "cd /data && git pull --ff-only" || echo "Warning: git pull failed (non-fatal)"
fi

# --- Ensure state directory exists ---
mkdir -p "$ALETHEIA_STATE_DIR"
chown aletheia:aletheia "$ALETHEIA_STATE_DIR"

# --- Reindex FTS5 search ---
echo "Reindexing search..."
gosu aletheia python -c "
from aletheia.core.storage import AletheiaStorage
from pathlib import Path
import os
s = AletheiaStorage(
    Path(os.environ['ALETHEIA_DATA_DIR']),
    Path(os.environ['ALETHEIA_STATE_DIR']),
)
n = s.reindex_all()
print(f'Indexed {n} cards.')
"

# --- Configure git identity for sync commits ---
if [ -d /data/.git ]; then
    gosu aletheia git -C /data config user.email "aletheia@container"
    gosu aletheia git -C /data config user.name "Aletheia"
fi

# --- Drop to aletheia user for the main process ---
exec gosu aletheia "$@"
