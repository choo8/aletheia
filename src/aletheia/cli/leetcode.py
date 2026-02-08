"""CLI subcommands for LeetCode integration."""

import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console

from aletheia.core.models import DSAProblemCard, LeetcodeSource

console = Console()

leetcode_app = typer.Typer(
    name="leetcode",
    help="LeetCode integration: login, test, and submit solutions.",
    no_args_is_help=True,
)


def _get_state_dir() -> Path:
    """Get the state directory path."""
    return Path(os.environ.get("ALETHEIA_STATE_DIR", Path.cwd() / ".aletheia"))


def _get_storage():
    """Get the storage instance (lazy import to avoid circular deps)."""
    from aletheia.cli.main import get_storage

    return get_storage()


# ============================================================================
# LOGIN command
# ============================================================================


@leetcode_app.command()
def login() -> None:
    """Authenticate with LeetCode via browser cookies or manual paste."""
    from aletheia.leetcode.auth import (
        LeetCodeAuthError,
        LeetCodeCredentials,
        extract_browser_cookies,
        save_credentials,
    )
    from aletheia.leetcode.service import LeetCodeError, LeetCodeService

    csrftoken = None
    leetcode_session = None

    # Try browser extraction first
    rprint("[dim]Attempting to extract cookies from browser...[/dim]")
    try:
        csrftoken, leetcode_session = extract_browser_cookies()
        rprint("[green]Cookies extracted from browser.[/green]")
    except LeetCodeAuthError as e:
        rprint(f"[yellow]Browser extraction failed: {e}[/yellow]")
        rprint("\n[bold]Manual login:[/bold]")
        rprint("[dim]Paste your cookies from browser DevTools (F12 > Application > Cookies).[/dim]")
        csrftoken = typer.prompt("csrftoken")
        leetcode_session = typer.prompt("LEETCODE_SESSION")

    # Verify credentials
    creds = LeetCodeCredentials(
        csrftoken=csrftoken,
        leetcode_session=leetcode_session,
        username="",
        stored_at=datetime.now(UTC).isoformat(),
    )

    rprint("[dim]Verifying credentials...[/dim]")
    try:
        service = LeetCodeService(creds)
        username = service.whoami()
    except LeetCodeError as e:
        rprint(f"[red]Login failed: {e}[/red]")
        raise typer.Exit(1)

    # Save with verified username
    creds.username = username
    state_dir = _get_state_dir()
    save_credentials(state_dir, creds)
    rprint(f"[green]Logged in as: {username}[/green]")


# ============================================================================
# STATUS command
# ============================================================================


@leetcode_app.command()
def status() -> None:
    """Check LeetCode login status."""
    from aletheia.leetcode.auth import get_credentials
    from aletheia.leetcode.service import LeetCodeError, LeetCodeService

    state_dir = _get_state_dir()
    creds = get_credentials(state_dir)

    if creds is None:
        rprint("[yellow]Not logged in.[/yellow]")
        rprint("[dim]Run: aletheia leetcode login[/dim]")
        return

    # Try to verify session is still valid
    try:
        service = LeetCodeService(creds)
        username = service.whoami()
        rprint(f"[green]Logged in as: {username}[/green]")
        rprint(f"[dim]Session stored at: {creds.stored_at}[/dim]")
    except LeetCodeError:
        rprint(f"[yellow]Session expired for: {creds.username}[/yellow]")
        rprint("[dim]Run: aletheia leetcode login[/dim]")


# ============================================================================
# TEST command
# ============================================================================


@leetcode_app.command("test")
def test_solution(
    card_id: str = typer.Argument(..., help="Card ID (or partial ID)"),
) -> None:
    """Test a card's solution against LeetCode sample test cases."""
    from aletheia.leetcode.auth import get_credentials
    from aletheia.leetcode.service import (
        LeetCodeError,
        LeetCodeService,
        resolve_code_solution,
        resolve_language,
    )

    storage = _get_storage()
    card = _require_dsa_card(storage, card_id)

    # Validate prerequisites
    if not card.problem_source:
        rprint("[red]Card has no problem_source set.[/red]")
        raise typer.Exit(1)

    try:
        code = resolve_code_solution(card)
        language = resolve_language(card)
    except LeetCodeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    # Get credentials and service
    state_dir = _get_state_dir()
    creds = get_credentials(state_dir)
    if creds is None:
        rprint("[red]Not logged in. Run: aletheia leetcode login[/red]")
        raise typer.Exit(1)

    try:
        service = LeetCodeService(creds)
    except LeetCodeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    # Resolve question ID (cache on card)
    question_id = card.problem_source.internal_question_id
    title_slug = _get_title_slug(card)

    if not question_id:
        rprint("[dim]Resolving question ID...[/dim]")
        try:
            question_id = service.resolve_question_id(card.problem_source.platform_id)
            card.problem_source.internal_question_id = question_id
            storage.save_card(card)
        except LeetCodeError as e:
            rprint(f"[red]{e}[/red]")
            raise typer.Exit(1)

    # Run test
    with console.status("[bold cyan]Running tests...[/bold cyan]"):
        try:
            result = service.test_solution(title_slug, question_id, code, language)
        except LeetCodeError as e:
            rprint(f"[red]{e}[/red]")
            raise typer.Exit(1)

    # Display results
    if result.passed:
        rprint(f"[green]PASSED[/green] ({result.passed_cases}/{result.total_cases} test cases)")
    else:
        rprint(f"[red]FAILED[/red] ({result.passed_cases}/{result.total_cases} test cases)")
        if result.runtime_error:
            rprint(f"[red]Runtime error:[/red] {result.runtime_error}")
        if result.compile_error:
            rprint(f"[red]Compile error:[/red] {result.compile_error}")
        if result.expected and result.actual:
            rprint(f"[dim]Expected: {result.expected}[/dim]")
            rprint(f"[dim]Actual:   {result.actual}[/dim]")


# ============================================================================
# SUBMIT command
# ============================================================================


@leetcode_app.command()
def submit(
    card_id: str = typer.Argument(..., help="Card ID (or partial ID)"),
    skip_test: bool = typer.Option(
        False,
        "--skip-test",
        help="Skip running tests before submitting",
    ),
) -> None:
    """Submit a card's solution to LeetCode for full judging."""
    from aletheia.leetcode.auth import get_credentials
    from aletheia.leetcode.service import (
        LeetCodeError,
        LeetCodeService,
        resolve_code_solution,
        resolve_language,
    )

    storage = _get_storage()
    card = _require_dsa_card(storage, card_id)

    if not card.problem_source:
        rprint("[red]Card has no problem_source set.[/red]")
        raise typer.Exit(1)

    try:
        code = resolve_code_solution(card)
        language = resolve_language(card)
    except LeetCodeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    # Get credentials and service
    state_dir = _get_state_dir()
    creds = get_credentials(state_dir)
    if creds is None:
        rprint("[red]Not logged in. Run: aletheia leetcode login[/red]")
        raise typer.Exit(1)

    try:
        service = LeetCodeService(creds)
    except LeetCodeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    # Resolve question ID
    question_id = card.problem_source.internal_question_id
    title_slug = _get_title_slug(card)

    if not question_id:
        rprint("[dim]Resolving question ID...[/dim]")
        try:
            question_id = service.resolve_question_id(card.problem_source.platform_id)
            card.problem_source.internal_question_id = question_id
            storage.save_card(card)
        except LeetCodeError as e:
            rprint(f"[red]{e}[/red]")
            raise typer.Exit(1)

    # Run tests first (unless skipped)
    if not skip_test:
        with console.status("[bold cyan]Running tests...[/bold cyan]"):
            try:
                test_result = service.test_solution(title_slug, question_id, code, language)
            except LeetCodeError as e:
                rprint(f"[red]Test failed: {e}[/red]")
                raise typer.Exit(1)

        if not test_result.passed:
            rprint(
                f"[red]Tests failed[/red] "
                f"({test_result.passed_cases}/{test_result.total_cases})"
            )
            if test_result.runtime_error:
                rprint(f"[red]Runtime error:[/red] {test_result.runtime_error}")
            rprint("[yellow]Fix tests before submitting. Use --skip-test to override.[/yellow]")
            raise typer.Exit(1)

        rprint(
            f"[green]Tests passed[/green] "
            f"({test_result.passed_cases}/{test_result.total_cases})"
        )

    # Confirm submission
    if not typer.confirm("Submit solution?", default=True):
        rprint("[yellow]Cancelled.[/yellow]")
        return

    # Submit
    with console.status("[bold cyan]Submitting...[/bold cyan]"):
        try:
            result = service.submit_solution(title_slug, question_id, code, language)
        except LeetCodeError as e:
            rprint(f"[red]Submission failed: {e}[/red]")
            raise typer.Exit(1)

    # Display results
    if result.passed:
        rprint("\n[bold green]Accepted![/bold green]")
        if result.runtime_ms is not None:
            pct = f" (beats {result.runtime_percentile:.1f}%)" if result.runtime_percentile else ""
            rprint(f"  Runtime: {result.runtime_ms} ms{pct}")
        if result.memory_kb is not None:
            pct = f" (beats {result.memory_percentile:.1f}%)" if result.memory_percentile else ""
            rprint(f"  Memory:  {result.memory_kb} KB{pct}")
    else:
        rprint(f"\n[red]{result.status}[/red]")
        if result.passed_cases is not None and result.total_cases is not None:
            rprint(f"  Passed: {result.passed_cases}/{result.total_cases}")
        if result.error_message:
            rprint(f"  Error: {result.error_message}")


# ============================================================================
# SET-SOLUTION command
# ============================================================================


@leetcode_app.command("set-solution")
def set_solution(
    card_id: str = typer.Argument(..., help="Card ID (or partial ID)"),
    file: str | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to solution file",
    ),
    language: str | None = typer.Option(
        None,
        "--language",
        "--lang",
        "-l",
        help="Language slug (e.g., python3, cpp, java)",
    ),
) -> None:
    """Set or update the code solution for a DSA problem card."""
    storage = _get_storage()
    card = _require_dsa_card(storage, card_id)

    if file:
        # Use file path
        path = Path(file)
        if not path.exists():
            rprint(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        card.code_solution = str(path.resolve())
        rprint(f"[dim]Solution set to file: {path.resolve()}[/dim]")
    else:
        # Open editor
        existing = card.code_solution or ""
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vim"))
        suffix = ".py"  # Default to python

        if language:
            ext_map = {"python3": ".py", "cpp": ".cpp", "java": ".java", "javascript": ".js"}
            suffix = ext_map.get(language, ".py")

        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            f.write(existing if not existing.endswith(tuple(".py .cpp .java .js".split())) else "")
            f.flush()
            temp_path = f.name

        try:
            subprocess.run([editor, temp_path], check=True)
            with open(temp_path) as f:
                code = f.read()
        finally:
            os.unlink(temp_path)

        if not code.strip():
            rprint("[yellow]Empty content — no changes made.[/yellow]")
            return

        card.code_solution = code
        rprint("[dim]Solution set to inline code.[/dim]")

    # Set language if provided
    if language:
        if card.problem_source is None:
            card.problem_source = LeetcodeSource(platform_id="", title="")
        card.problem_source.language = language
        rprint(f"[dim]Language set to: {language}[/dim]")

    storage.save_card(card)
    rprint(f"[green]Card updated:[/green] {card.id[:8]}")


# ============================================================================
# Helpers
# ============================================================================


def _require_dsa_card(storage, card_id: str) -> DSAProblemCard:
    """Find a DSA problem card by ID or exit with error."""
    from aletheia.cli.main import _find_card

    card = _find_card(storage, card_id)
    if card is None:
        rprint(f"[red]Card not found: {card_id}[/red]")
        raise typer.Exit(1)

    if not isinstance(card, DSAProblemCard):
        rprint(f"[red]Card {card_id[:8]} is not a DSA problem card.[/red]")
        raise typer.Exit(1)

    return card


def _get_title_slug(card: DSAProblemCard) -> str:
    """Derive the title slug from a card's problem source."""
    source = card.problem_source
    if source and source.url:
        # Extract slug from URL like https://leetcode.com/problems/two-sum/
        parts = source.url.rstrip("/").split("/")
        if "problems" in parts:
            idx = parts.index("problems")
            if idx + 1 < len(parts):
                return parts[idx + 1]

    if source and source.title:
        return source.title.lower().replace(" ", "-")

    raise typer.Exit(1)
