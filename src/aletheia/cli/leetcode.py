"""CLI subcommands for LeetCode integration."""

import os
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console

from aletheia.cli.helpers import find_card, get_storage, open_in_editor
from aletheia.core.models import DSAProblemCard, LeetcodeSource
from aletheia.leetcode.auth import (
    LeetCodeAuthError,
    LeetCodeCredentials,
    extract_browser_cookies,
    get_credentials,
    save_credentials,
)
from aletheia.leetcode.service import (
    _EXTENSION_MAP,
    LeetCodeError,
    LeetCodeService,
    resolve_code_solution,
    resolve_language,
)

console = Console()

leetcode_app = typer.Typer(
    name="leetcode",
    help="LeetCode integration: login, submit, and manage solutions.",
    no_args_is_help=True,
)


def _get_state_dir() -> Path:
    """Get the state directory path."""
    return Path(os.environ.get("ALETHEIA_STATE_DIR", Path.cwd() / ".aletheia"))


# ============================================================================
# LOGIN command
# ============================================================================


@leetcode_app.command()
def login() -> None:
    """Authenticate with LeetCode via browser cookies or manual paste."""
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
    storage = get_storage()
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
            question_id = service.resolve_question_id(
                card.problem_source.platform_id, title_slug=title_slug
            )
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
                f"[red]Tests failed[/red] ({test_result.passed_cases}/{test_result.total_cases})"
            )
            if test_result.runtime_error:
                rprint(f"[red]Runtime error:[/red] {test_result.runtime_error}")
            rprint("[yellow]Fix tests before submitting. Use --skip-test to override.[/yellow]")
            raise typer.Exit(1)

        rprint(
            f"[green]Tests passed[/green] ({test_result.passed_cases}/{test_result.total_cases})"
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

# Reverse map: LeetCode slug → file extension (for editor temp files)
_SLUG_TO_EXT: dict[str, str] = {}


def _get_slug_to_ext() -> dict[str, str]:
    """Build reverse map from LeetCode language slug to file extension."""
    if not _SLUG_TO_EXT:
        for ext, slug in _EXTENSION_MAP.items():
            _SLUG_TO_EXT.setdefault(slug, ext)
    return _SLUG_TO_EXT


def _format_as_comment(text: str, language: str) -> str:
    """Wrap text as a block comment in the given language."""
    lines = text.splitlines()
    # Hash-style comments
    if language in ("python3", "ruby"):
        return "\n".join(f"# {line}" if line.strip() else "#" for line in lines)
    # Block-style comments
    commented = "\n".join(f" * {line}" if line.strip() else " *" for line in lines)
    return f"/*\n{commented}\n */"


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
    storage = get_storage()
    card = _require_dsa_card(storage, card_id)

    # Resolve language slug: explicit flag > card's existing language > python3
    lang_slug = language
    if not lang_slug and card.problem_source and card.problem_source.language:
        lang_slug = card.problem_source.language

    if file:
        # Use file path
        path = Path(file)
        if not path.exists():
            rprint(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        card.code_solution = str(path.resolve())
        rprint(f"[dim]Solution set to file: {path.resolve()}[/dim]")
    else:
        # Open editor — default to python3 when no language is known
        if not lang_slug:
            lang_slug = "python3"

        existing = card.code_solution or ""

        slug_to_ext = _get_slug_to_ext()
        suffix = slug_to_ext.get(lang_slug, ".py")

        # Determine initial editor content
        is_file_path = existing.endswith(tuple(slug_to_ext.values()))
        initial_content = existing if existing and not is_file_path else ""

        # If no existing code, try to fetch problem description + starter code
        if not initial_content:
            initial_content = _fetch_editor_content(card, lang_slug or "python3")

        code = open_in_editor(initial_content, suffix=suffix)

        if not code.strip():
            rprint("[yellow]Empty content — no changes made.[/yellow]")
            return

        card.code_solution = code
        rprint("[dim]Solution set to inline code.[/dim]")

    # Persist language: explicit --language always wins, otherwise backfill if missing
    if language:
        if card.problem_source is None:
            card.problem_source = LeetcodeSource(platform_id="", title="")
        card.problem_source.language = language
        rprint(f"[dim]Language set to: {language}[/dim]")
    elif lang_slug and (not card.problem_source or not card.problem_source.language):
        if card.problem_source is None:
            card.problem_source = LeetcodeSource(platform_id="", title="")
        card.problem_source.language = lang_slug
        rprint(f"[dim]Language set to: {lang_slug}[/dim]")

    storage.save_card(card)
    rprint(f"[green]Card updated:[/green] {card.id[:8]}")


def _fetch_editor_content(card: "DSAProblemCard", lang_slug: str) -> str:
    """Best-effort fetch of problem description + starter code from LeetCode.

    Returns the formatted content or empty string on any failure.
    """
    state_dir = _get_state_dir()
    creds = get_credentials(state_dir)
    if creds is None:
        rprint("[dim]Skipping problem fetch (not logged in).[/dim]")
        return ""

    try:
        title_slug = _get_title_slug(card)
    except SystemExit:
        rprint("[dim]Skipping problem fetch (no URL or title on card).[/dim]")
        return ""

    try:
        service = LeetCodeService(creds)
        detail = service.get_problem_detail(title_slug)
    except Exception as e:
        rprint(f"[dim]Could not fetch problem detail: {e}[/dim]")
        return ""

    parts: list[str] = []
    if detail.content_text:
        parts.append(_format_as_comment(detail.content_text, lang_slug))
        parts.append("")  # blank line separator

    snippet = detail.code_snippets.get(lang_slug, "")
    if snippet:
        parts.append(snippet)

    return "\n".join(parts)


# ============================================================================
# Helpers
# ============================================================================


def _require_dsa_card(storage, card_id: str) -> DSAProblemCard:
    """Find a DSA problem card by ID or exit with error."""
    card = find_card(storage, card_id)
    if card is None:
        rprint(f"[red]Card not found: {card_id}[/red]")
        raise typer.Exit(1)

    if not isinstance(card, DSAProblemCard):
        rprint(f"[red]Card {card_id[:8]} is not a DSA problem card.[/red]")
        raise typer.Exit(1)

    return card


@leetcode_app.command("review-submit")
def review_submit(
    card_id: str = typer.Argument(..., help="Card ID (or partial ID)"),
) -> None:
    """Submit code as a review: write solution from memory, submit, and auto-rate.

    1. Show problem description
    2. Open editor with starter code
    3. Submit to LeetCode
    4. If accepted: auto-rate GOOD/EASY, FIRe cascades credit
    5. If failed: LLM classifies failure type, differentiated ratings
    """
    storage = get_storage()
    card = _require_dsa_card(storage, card_id)

    if not card.problem_source:
        rprint("[red]Card has no problem_source set.[/red]")
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

    # Resolve question details
    title_slug = _get_title_slug(card)
    question_id = card.problem_source.internal_question_id

    if not question_id:
        rprint("[dim]Resolving question ID...[/dim]")
        try:
            question_id = service.resolve_question_id(
                card.problem_source.platform_id, title_slug=title_slug
            )
            card.problem_source.internal_question_id = question_id
            storage.save_card(card)
        except LeetCodeError as e:
            rprint(f"[red]{e}[/red]")
            raise typer.Exit(1)

    # Show problem front
    rprint(f"\n[bold]Problem:[/bold] {card.front}\n")

    # Determine language
    lang_slug = (card.problem_source.language if card.problem_source else None) or "python3"
    slug_to_ext = _get_slug_to_ext()
    suffix = slug_to_ext.get(lang_slug, ".py")

    # Fetch starter code (without showing existing solution)
    starter = _fetch_editor_content(card, lang_slug)
    # Strip any existing solution to force recall
    if starter:
        # Keep only the comment block (problem description) and starter template
        rprint("[dim]Opening editor with starter code...[/dim]")
    else:
        rprint("[dim]Opening editor...[/dim]")

    code = open_in_editor(starter, suffix=suffix)
    if not code.strip():
        rprint("[yellow]Empty code — review cancelled.[/yellow]")
        return

    # Submit
    with console.status("[bold cyan]Submitting...[/bold cyan]"):
        try:
            result = service.submit_solution(title_slug, question_id, code, lang_slug)
        except LeetCodeError as e:
            rprint(f"[red]Submission failed: {e}[/red]")
            raise typer.Exit(1)

    # Import scheduler and FIRe for rating
    from aletheia.core.fire import FIReEngine
    from aletheia.core.graph import KnowledgeGraph
    from aletheia.core.scheduler import AletheiaScheduler, ReviewRating

    scheduler = AletheiaScheduler(storage.db)
    graph = KnowledgeGraph(storage)
    fire = FIReEngine(storage, graph)

    if result.passed:
        rprint("\n[bold green]Accepted![/bold green]")
        if result.runtime_ms is not None:
            rprint(f"  Runtime: {result.runtime_ms} ms")

        # Auto-rate: GOOD by default, EASY if fast
        rating = ReviewRating.GOOD
        if result.runtime_percentile and result.runtime_percentile > 80:
            rating = ReviewRating.EASY

        review_result = scheduler.review_card(card.id, rating)
        due_str = review_result.due_next.strftime("%Y-%m-%d")
        rprint(f"[dim]Auto-rated: {rating.name} → Next review: {due_str}[/dim]")

        # FIRe credit propagation
        fire_credits = fire.propagate_credit(card.id, rating.value)
        if fire_credits:
            rprint(f"[dim]Implicit credit propagated to {len(fire_credits)} card(s)[/dim]")
    else:
        rprint(f"\n[red]{result.status}[/red]")
        if result.error_message:
            rprint(f"  Error: {result.error_message}")

        # LLM failure classification
        try:
            from aletheia.llm import LLMService

            llm = LLMService()
            classification = llm.classify_failure(
                card.front, code, result.error_message or result.status
            )
            rprint(f"\n[yellow]Failure type: {classification.failure_type.value}[/yellow]")
            rprint(f"[dim]{classification.explanation}[/dim]")

            # Apply differentiated ratings
            understanding_rating = ReviewRating(classification.understanding_rating)
            impl_rating = ReviewRating(classification.implementation_rating)

            u_name = understanding_rating.name
            rprint(f"[dim]Understanding → {u_name}, Implementation → {impl_rating.name}[/dim]")

            # Rate the current card
            review_result = scheduler.review_card(card.id, impl_rating)
            rprint(f"[dim]Next review: {review_result.due_next.strftime('%Y-%m-%d')}[/dim]")

            # Offer resubmit for mechanical/trivial failures
            if classification.failure_type.value in ("mechanical", "trivial"):
                if typer.confirm("\nResubmit (fix the bug)?", default=True):
                    rprint("[dim]Opening editor to fix...[/dim]")
                    fixed_code = open_in_editor(code, suffix=suffix)
                    if fixed_code.strip():
                        with console.status("[bold cyan]Resubmitting...[/bold cyan]"):
                            retry = service.submit_solution(
                                title_slug, question_id, fixed_code, lang_slug
                            )
                        if retry.passed:
                            rprint("[bold green]Accepted on retry![/bold green]")
                        else:
                            rprint(f"[red]Still failing: {retry.status}[/red]")
        except (ImportError, Exception) as e:
            rprint(f"[dim]Could not classify failure: {e}[/dim]")
            # Fall back to AGAIN rating
            scheduler.review_card(card.id, ReviewRating.AGAIN)


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
