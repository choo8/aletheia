"""Main CLI entry point for Aletheia."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aletheia.core.models import (
    CardType,
    Complexity,
    CreationMode,
    DSAConceptCard,
    DSAProblemCard,
    LeetcodeSource,
    Maturity,
    SystemDesignCard,
)
from aletheia.core.scheduler import AletheiaScheduler, ReviewRating
from aletheia.core.storage import AletheiaStorage

app = typer.Typer(
    name="aletheia",
    help="Personal knowledge management and spaced repetition for technical learning.",
    no_args_is_help=True,
)
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


def open_in_editor(content: str, suffix: str = ".yaml") -> str:
    """Open content in the user's editor and return the edited content."""
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vim"))

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        subprocess.run([editor, temp_path], check=True)
        with open(temp_path) as f:
            return f.read()
    finally:
        os.unlink(temp_path)


# ============================================================================
# ADD command
# ============================================================================


@app.command()
def add(
    card_type: str = typer.Argument(
        ...,
        help="Type of card: dsa-problem, dsa-concept, system-design",
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        "-q",
        help="Quick add mode (skip guided extraction)",
    ),
) -> None:
    """Add a new card interactively."""
    storage = get_storage()

    if card_type == "dsa-problem":
        card = _add_dsa_problem(quick)
    elif card_type == "dsa-concept":
        card = _add_dsa_concept(quick)
    elif card_type == "system-design":
        card = _add_system_design(quick)
    else:
        rprint(f"[red]Unknown card type: {card_type}[/red]")
        rprint("Supported types: dsa-problem, dsa-concept, system-design")
        raise typer.Exit(1)

    if card:
        path = storage.save_card(card)
        rprint("\n[green]Card saved![/green]")
        rprint(f"  ID: {card.id}")
        rprint(f"  Path: {path}")


def _add_dsa_problem(quick: bool) -> DSAProblemCard | None:
    """Interactive flow for adding a DSA problem card."""
    rprint("\n[bold]Adding DSA Problem Card[/bold]\n")

    # Get problem source
    platform = typer.prompt("Platform", default="leetcode")
    problem_id = typer.prompt("Problem ID (e.g., 42)")
    title = typer.prompt("Problem title")
    url = typer.prompt("URL (optional)", default="")
    difficulty = typer.prompt("Difficulty (easy/medium/hard)", default="medium")

    source = LeetcodeSource(
        platform=platform,
        platform_id=problem_id,
        title=title,
        url=url or None,
        difficulty=difficulty,
    )

    # Get card content
    rprint("\n[dim]Enter the main question for this card:[/dim]")
    front = typer.prompt("Front (question)")

    rprint("\n[dim]Enter the answer/explanation:[/dim]")
    back = typer.prompt("Back (answer)")

    # Patterns and data structures
    patterns_str = typer.prompt(
        "Patterns used (comma-separated, e.g., two-pointers,sliding-window)",
        default="",
    )
    patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]

    ds_str = typer.prompt(
        "Data structures (comma-separated, e.g., array,hashmap)",
        default="",
    )
    data_structures = [d.strip() for d in ds_str.split(",") if d.strip()]

    # Complexity
    time_complexity = typer.prompt("Time complexity (e.g., O(n))", default="")
    space_complexity = typer.prompt("Space complexity (e.g., O(1))", default="")
    complexity = None
    if time_complexity or space_complexity:
        complexity = Complexity(time=time_complexity or "?", space=space_complexity or "?")

    # Optional fields
    intuition = ""
    edge_cases: list[str] = []

    if not quick:
        rprint("\n[dim]Optional: Add intuition and edge cases[/dim]")
        intuition = typer.prompt("Key intuition (why does this approach work?)", default="")
        edge_cases_str = typer.prompt("Edge cases (comma-separated)", default="")
        edge_cases = [e.strip() for e in edge_cases_str.split(",") if e.strip()]

    # Tags and taxonomy
    tags_str = typer.prompt("Tags (comma-separated, e.g., #interview-classic)", default="")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    taxonomy = ["dsa", "problems"] + patterns[:1]  # Auto-add first pattern to taxonomy

    card = DSAProblemCard(
        front=front,
        back=back,
        problem_source=source,
        patterns=patterns,
        data_structures=data_structures,
        complexity=complexity,
        intuition=intuition or None,
        edge_cases=edge_cases,
        tags=tags,
        taxonomy=taxonomy,
        creation_mode=CreationMode.MANUAL,
    )

    # Preview
    rprint("\n[bold]Preview:[/bold]")
    _display_card(card)

    if typer.confirm("\nSave this card?", default=True):
        return card
    return None


def _add_dsa_concept(quick: bool) -> DSAConceptCard | None:
    """Interactive flow for adding a DSA concept card."""
    rprint("\n[bold]Adding DSA Concept Card[/bold]\n")

    name = typer.prompt("Concept name (e.g., Monotonic Stack)")
    front = typer.prompt("Front (question)")
    back = typer.prompt("Back (answer)")

    definition = typer.prompt("Definition (optional)", default="")
    intuition = typer.prompt("Intuition - when/why to use (optional)", default="")

    patterns_str = typer.prompt("Common patterns (comma-separated)", default="")
    common_patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]

    when_to_use = ""
    when_not_to_use = ""
    if not quick:
        when_to_use = typer.prompt("When to use (signals)", default="")
        when_not_to_use = typer.prompt("When NOT to use", default="")

    tags_str = typer.prompt("Tags (comma-separated)", default="")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    taxonomy = ["dsa", "concepts"]

    card = DSAConceptCard(
        name=name,
        front=front,
        back=back,
        definition=definition or None,
        intuition=intuition or None,
        common_patterns=common_patterns,
        when_to_use=when_to_use or None,
        when_not_to_use=when_not_to_use or None,
        tags=tags,
        taxonomy=taxonomy,
        creation_mode=CreationMode.MANUAL,
    )

    rprint("\n[bold]Preview:[/bold]")
    _display_card(card)

    if typer.confirm("\nSave this card?", default=True):
        return card
    return None


def _add_system_design(quick: bool) -> SystemDesignCard | None:
    """Interactive flow for adding a system design card."""
    rprint("\n[bold]Adding System Design Card[/bold]\n")

    name = typer.prompt("Concept name (e.g., Leader-Follower Replication)")
    front = typer.prompt("Front (question)")
    back = typer.prompt("Back (answer)")

    definition = typer.prompt("Definition (optional)", default="")
    how_it_works = ""
    if not quick:
        how_it_works = typer.prompt("How it works (optional)", default="")

    use_cases_str = typer.prompt("Use cases (comma-separated)", default="")
    use_cases = [u.strip() for u in use_cases_str.split(",") if u.strip()]

    anti_patterns_str = typer.prompt(
        "Anti-patterns / when NOT to use (comma-separated)", default=""
    )
    anti_patterns = [a.strip() for a in anti_patterns_str.split(",") if a.strip()]

    tags_str = typer.prompt("Tags (comma-separated)", default="")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    taxonomy = ["system-design"]

    card = SystemDesignCard(
        name=name,
        front=front,
        back=back,
        definition=definition or None,
        how_it_works=how_it_works or None,
        use_cases=use_cases,
        anti_patterns=anti_patterns,
        tags=tags,
        taxonomy=taxonomy,
        creation_mode=CreationMode.MANUAL,
    )

    rprint("\n[bold]Preview:[/bold]")
    _display_card(card)

    if typer.confirm("\nSave this card?", default=True):
        return card
    return None


# ============================================================================
# LIST command
# ============================================================================


@app.command("list")
def list_cards(
    card_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by card type",
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Filter by tag",
    ),
    maturity: str | None = typer.Option(
        None,
        "--maturity",
        "-m",
        help="Filter by maturity (active/exhausted/suspended)",
    ),
) -> None:
    """List all cards with optional filters."""
    storage = get_storage()

    filters = {}
    if card_type:
        try:
            filters["card_type"] = CardType(card_type)
        except ValueError:
            rprint(f"[red]Invalid card type: {card_type}[/red]")
            raise typer.Exit(1)

    if tag:
        filters["tags"] = [tag]

    if maturity:
        filters["maturity"] = maturity

    cards = storage.list_cards(**filters)

    if not cards:
        rprint("[dim]No cards found.[/dim]")
        return

    table = Table(title=f"Cards ({len(cards)} total)")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Type", style="cyan")
    table.add_column("Front", max_width=50)
    table.add_column("Tags", style="green")
    table.add_column("Maturity")

    for card in cards:
        table.add_row(
            card.id[:8],
            card.type.value,
            card.front[:50] + "..." if len(card.front) > 50 else card.front,
            " ".join(card.tags[:3]),
            card.maturity.value,
        )

    console.print(table)


# ============================================================================
# SHOW command
# ============================================================================


@app.command()
def show(
    card_id: str = typer.Argument(..., help="Card ID (or partial ID)"),
) -> None:
    """Show details of a specific card."""
    storage = get_storage()
    card = _find_card(storage, card_id)

    if card is None:
        rprint(f"[red]Card not found: {card_id}[/red]")
        raise typer.Exit(1)

    _display_card(card, full=True)


def _find_card(storage: AletheiaStorage, card_id: str):
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


def _display_card(card, full: bool = False) -> None:
    """Display a card in a formatted panel."""
    name = getattr(card, "name", None)
    title = f"{card.type.value}: {name}" if name else card.type.value

    content = f"[bold]Front:[/bold] {card.front}\n\n[bold]Back:[/bold] {card.back}"

    if full:
        content += f"\n\n[dim]ID: {card.id}[/dim]"
        content += f"\n[dim]Maturity: {card.maturity.value}[/dim]"

        if card.tags:
            content += f"\n[dim]Tags: {' '.join(card.tags)}[/dim]"

        if card.taxonomy:
            content += f"\n[dim]Taxonomy: {' > '.join(card.taxonomy)}[/dim]"

        # Type-specific fields
        if hasattr(card, "patterns") and card.patterns:
            content += f"\n[dim]Patterns: {', '.join(card.patterns)}[/dim]"

        if hasattr(card, "complexity") and card.complexity:
            c = card.complexity
            content += f"\n[dim]Complexity: Time {c.time}, Space {c.space}[/dim]"

        if hasattr(card, "intuition") and card.intuition:
            content += f"\n\n[bold]Intuition:[/bold] {card.intuition}"

    console.print(Panel(content, title=title, border_style="blue"))


# ============================================================================
# EDIT command
# ============================================================================


@app.command()
def edit(
    card_id: str = typer.Argument(..., help="Card ID to edit"),
) -> None:
    """Edit a card in your editor."""
    storage = get_storage()
    card = _find_card(storage, card_id)

    if card is None:
        rprint(f"[red]Card not found: {card_id}[/red]")
        raise typer.Exit(1)

    # Create a simplified editable version
    editable = {
        "id": card.id,
        "type": card.type.value,
        "front": card.front,
        "back": card.back,
        "tags": card.tags,
        "taxonomy": card.taxonomy,
        "maturity": card.maturity.value,
    }

    # Add type-specific fields
    if hasattr(card, "name"):
        editable["name"] = card.name
    if hasattr(card, "patterns"):
        editable["patterns"] = card.patterns
    if hasattr(card, "intuition") and card.intuition:
        editable["intuition"] = card.intuition
    if hasattr(card, "edge_cases"):
        editable["edge_cases"] = card.edge_cases

    # Open in editor
    content = json.dumps(editable, indent=2)
    edited_content = open_in_editor(content, suffix=".json")

    if not edited_content.strip():
        rprint("[yellow]Edit cancelled (empty content).[/yellow]")
        return

    try:
        edited = json.loads(edited_content)
    except json.JSONDecodeError as e:
        rprint(f"[red]Invalid JSON: {e}[/red]")
        raise typer.Exit(1)

    # Update the card
    for key, value in edited.items():
        if key in ["id", "type"]:
            continue  # Don't allow changing these
        if hasattr(card, key):
            setattr(card, key, value)

    # Handle maturity separately (it's an enum)
    if "maturity" in edited:
        card.maturity = Maturity(edited["maturity"])

    path = storage.save_card(card)
    rprint(f"[green]Card updated![/green] {path}")


# ============================================================================
# STATS command
# ============================================================================


@app.command()
def stats() -> None:
    """Show review statistics."""
    storage = get_storage()
    db_stats = storage.db.get_stats()

    table = Table(title="Aletheia Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Cards", str(db_stats["total_cards"]))
    table.add_row("Total Reviews", str(db_stats["total_reviews"]))
    table.add_row("Due Today", str(db_stats["due_today"]))
    table.add_row("New Cards", str(db_stats["new_cards"]))

    # Count by type
    cards = storage.list_cards()
    by_type: dict[str, int] = {}
    for card in cards:
        by_type[card.type.value] = by_type.get(card.type.value, 0) + 1

    if by_type:
        table.add_row("", "")
        table.add_row("[bold]By Type[/bold]", "")
        for card_type, count in sorted(by_type.items()):
            table.add_row(f"  {card_type}", str(count))

    console.print(table)


# ============================================================================
# SEARCH command
# ============================================================================


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
) -> None:
    """Search cards by content."""
    storage = get_storage()
    results = storage.search(query)

    if not results:
        rprint(f"[dim]No cards found matching '{query}'[/dim]")
        return

    rprint(f"\n[bold]Found {len(results)} card(s):[/bold]\n")

    for card in results:
        _display_card(card)
        rprint("")


# ============================================================================
# REVIEW command
# ============================================================================


@app.command()
def review(
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Maximum cards to review",
    ),
    new_cards: int = typer.Option(
        5,
        "--new",
        "-n",
        help="Maximum new cards to include",
    ),
) -> None:
    """Start an interactive review session."""
    storage = get_storage()
    scheduler = AletheiaScheduler(storage.db)

    # Get cards to review: due cards + new cards
    due_ids = scheduler.get_due_cards(limit)
    new_ids = scheduler.get_new_cards(new_cards)

    # Combine, avoiding duplicates
    card_ids = due_ids + [c for c in new_ids if c not in due_ids]

    if not card_ids:
        rprint("[green]No cards due for review![/green]")
        return

    rprint(f"\n[bold]Review Session[/bold]: {len(card_ids)} card(s)\n")

    reviewed = 0
    for i, card_id in enumerate(card_ids, 1):
        card = storage.load_card(card_id)
        if not card:
            continue

        # Display card front
        name = getattr(card, "name", None)
        title = f"Card {i}/{len(card_ids)}"
        if name:
            title += f" - {name}"

        console.print(Panel(card.front, title=title, border_style="blue"))

        # Wait for reveal
        typer.prompt("\n[Press Enter to reveal answer]", default="", show_default=False)

        # Display answer
        console.print(Panel(card.back, title="Answer", border_style="green"))

        # Show additional context if available
        if hasattr(card, "intuition") and card.intuition:
            rprint(f"[dim]Intuition: {card.intuition}[/dim]")

        # Get rating
        rating = _prompt_rating()
        if rating is None:
            rprint("\n[yellow]Session ended early.[/yellow]")
            break

        # Process review
        result = scheduler.review_card(card_id, rating)
        rprint(f"[dim]Next review: {result.due_next.strftime('%Y-%m-%d %H:%M')}[/dim]\n")
        reviewed += 1

    # Session summary
    rprint("\n[bold green]Session complete![/bold green]")
    rprint(f"Reviewed {reviewed} card(s).")

    # Show updated stats
    db_stats = storage.db.get_stats()
    rprint(f"[dim]Total reviews: {db_stats['total_reviews']}[/dim]")


def _prompt_rating() -> ReviewRating | None:
    """Prompt user for rating."""
    rprint("\n[bold]Rate this card:[/bold]")
    rprint(
        "  [red]1[/red] Again (forgot)  "
        "[yellow]2[/yellow] Hard  "
        "[green]3[/green] Good  "
        "[cyan]4[/cyan] Easy  "
        "[dim]q[/dim] Quit"
    )

    while True:
        choice = typer.prompt("Rating", default="3")
        if choice.lower() == "q":
            return None
        try:
            rating_value = int(choice)
            if 1 <= rating_value <= 4:
                return ReviewRating(rating_value)
        except ValueError:
            pass
        rprint("[red]Invalid choice. Enter 1-4 or q to quit.[/red]")


# ============================================================================
# SERVE command
# ============================================================================


@app.command()
def serve(
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to run the server on",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        "-h",
        help="Host to bind to",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        "-r",
        help="Enable auto-reload for development",
    ),
) -> None:
    """Start the web server for review sessions."""
    try:
        import uvicorn
    except ImportError:
        rprint("[red]Web dependencies not installed.[/red]")
        rprint("Install with: pip install aletheia[web]")
        raise typer.Exit(1)

    rprint("\n[bold]Starting Aletheia web server[/bold]")
    rprint(f"  URL: http://{host}:{port}")
    rprint(f"  Review: http://{host}:{port}/review")
    rprint("\n[dim]Press Ctrl+C to stop[/dim]\n")

    uvicorn.run(
        "aletheia.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


# ============================================================================
# Main entry point
# ============================================================================


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
