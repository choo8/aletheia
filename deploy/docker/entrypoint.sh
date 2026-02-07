#!/bin/bash
set -e

# --- SSH deploy key setup ---
if [ -f /run/deploy_key ]; then
    mkdir -p ~/.ssh
    cp /run/deploy_key ~/.ssh/id_ed25519
    chmod 600 ~/.ssh/id_ed25519
    ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null
    echo "SSH deploy key configured."
fi

# --- Clone or pull data repo ---
if [ -n "$ALETHEIA_DATA_REPO" ] && [ ! -d /data/.git ]; then
    echo "Cloning data repo: $ALETHEIA_DATA_REPO"
    git clone "$ALETHEIA_DATA_REPO" /data
elif [ -d /data/.git ]; then
    echo "Pulling latest data..."
    cd /data && git pull --ff-only || echo "Warning: git pull failed (non-fatal)"
fi

# --- Ensure state directory exists ---
mkdir -p "$ALETHEIA_STATE_DIR"

# --- Reindex FTS5 search ---
echo "Reindexing search..."
python -c "
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
    cd /data
    git config user.email "aletheia@container"
    git config user.name "Aletheia"
fi

exec "$@"
