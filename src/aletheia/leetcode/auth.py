"""LeetCode authentication — credential storage and browser cookie extraction."""

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


class LeetCodeAuthError(Exception):
    """Error during LeetCode authentication."""


@dataclass
class LeetCodeCredentials:
    """LeetCode session credentials."""

    csrftoken: str
    leetcode_session: str
    username: str
    stored_at: str  # ISO format


_AUTH_FILENAME = "leetcode_auth.json"


def save_credentials(state_dir: Path, creds: LeetCodeCredentials) -> Path:
    """Save credentials to state dir as JSON.

    Returns the path to the written file.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / _AUTH_FILENAME
    path.write_text(json.dumps(asdict(creds), indent=2))
    return path


def get_credentials(state_dir: Path) -> LeetCodeCredentials | None:
    """Load credentials, checking env vars first then JSON file.

    Environment variables LEETCODE_CSRFTOKEN and LEETCODE_SESSION
    take precedence over the stored JSON file.
    """
    csrf = os.environ.get("LEETCODE_CSRFTOKEN")
    session = os.environ.get("LEETCODE_SESSION")

    if csrf and session:
        return LeetCodeCredentials(
            csrftoken=csrf,
            leetcode_session=session,
            username=os.environ.get("LEETCODE_USERNAME", "env"),
            stored_at=datetime.now(UTC).isoformat(),
        )

    path = state_dir / _AUTH_FILENAME
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        return LeetCodeCredentials(**data)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        raise LeetCodeAuthError(f"Corrupt credentials file: {e}") from e


def extract_browser_cookies() -> tuple[str, str]:
    """Extract CSRF token and session cookie from browser via rookiepy.

    Returns:
        (csrftoken, leetcode_session) tuple

    Raises:
        LeetCodeAuthError: if rookiepy is not installed or cookies not found
    """
    try:
        import rookiepy
    except ImportError as e:
        raise LeetCodeAuthError(
            "rookiepy not installed. Install with: pip install aletheia[leetcode]"
        ) from e

    raw_cookies = _load_browser_cookies(rookiepy)
    cookies = rookiepy.to_cookiejar(raw_cookies)
    cookie_dict = {c.name: c.value for c in cookies}

    csrftoken = cookie_dict.get("csrftoken")
    leetcode_session = cookie_dict.get("LEETCODE_SESSION")

    if not csrftoken or not leetcode_session:
        missing = []
        if not csrftoken:
            missing.append("csrftoken")
        if not leetcode_session:
            missing.append("LEETCODE_SESSION")
        raise LeetCodeAuthError(
            f"Missing cookies: {', '.join(missing)}. "
            "Make sure you are logged into leetcode.com in your browser."
        )

    return csrftoken, leetcode_session


_BROWSERS = ("chrome", "firefox", "brave", "edge", "chromium", "opera", "vivaldi")


def _load_browser_cookies(rookiepy) -> list:  # type: ignore[no-untyped-def]
    """Load leetcode.com cookies, falling back to per-browser attempts.

    rookiepy.load() silently returns [] when every browser fails
    (missing DB, decryption error, etc.).  When that happens we retry
    each browser individually so we can surface the *real* error.
    """
    domain = ["leetcode.com"]

    try:
        raw = rookiepy.load(domain)
    except Exception as e:
        raise LeetCodeAuthError(f"Failed to extract browser cookies: {e}") from e

    if raw:
        return raw

    # load() returned nothing — probe each browser for a real error message.
    errors: list[str] = []
    for name in _BROWSERS:
        fn = getattr(rookiepy, name, None)
        if fn is None:
            continue
        try:
            result = fn(domain)
            if result:
                return result
        except Exception as e:
            errors.append(f"{name}: {e}")

    detail = "; ".join(errors) if errors else "no supported browser found"
    raise LeetCodeAuthError(
        f"Could not extract cookies from any browser ({detail}). "
        "Make sure you are logged into leetcode.com."
    )


def clear_credentials(state_dir: Path) -> bool:
    """Remove stored credentials file.

    Returns True if file was removed, False if it didn't exist.
    """
    path = state_dir / _AUTH_FILENAME
    if path.exists():
        path.unlink()
        return True
    return False
