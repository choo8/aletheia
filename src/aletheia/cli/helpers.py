"""Shared CLI helpers used by main and subcommand modules.

Extracted to break the circular import between cli.main and cli.leetcode.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from rich import print as rprint
from rich.console import Console

from aletheia.core.storage import AletheiaStorage

console = Console()

# Global storage instance (initialized lazily)
_storage: AletheiaStorage | None = None


def get_storage() -> AletheiaStorage:
    """Get or create the storage instance."""
    global _storage
    if _storage is None:
        data_dir = Path(os.environ.get("ALETHEIA_DATA_DIR", Path.cwd() / "data"))
        state_dir = Path(os.environ.get("ALETHEIA_STATE_DIR", Path.cwd() / ".aletheia"))
        _storage = AletheiaStorage(data_dir, state_dir)
    return _storage


def _editor_cmd() -> list[str]:
    """Build the editor command, adding --wait for GUI editors that need it."""
    raw = os.environ.get("EDITOR", os.environ.get("VISUAL", "vim"))
    cmd = shlex.split(raw)
    # GUI editors that return immediately without --wait
    gui_editors = {"code", "code-insiders", "subl", "atom", "zed"}
    if cmd and cmd[0] in gui_editors and "--wait" not in cmd and "-w" not in cmd:
        cmd.append("--wait")
    return cmd


def open_in_editor(content: str, suffix: str = ".yaml") -> str:
    """Open content in the user's editor and return the edited content."""
    cmd = _editor_cmd()

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        subprocess.run([*cmd, temp_path], check=True)
        with open(temp_path) as f:
            return f.read()
    finally:
        os.unlink(temp_path)


def find_card(storage: AletheiaStorage, card_id: str):
    """Find a card by full or partial ID."""
    # Try exact match first
    card = storage.load_card(card_id)
    if card:
        return card

    # Try partial match
    all_cards = storage.list_cards()
    matches = [c for c in all_cards if c.id.startswith(card_id)]

    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        rprint(f"[yellow]Multiple cards match '{card_id}':[/yellow]")
        for c in matches:
            rprint(f"  {c.id[:8]}: {c.front[:40]}...")
        return None

    return None
