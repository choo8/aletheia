"""Main CLI entry point for Aletheia."""

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aletheia.cli.helpers import find_card, get_storage, open_in_editor
from aletheia.cli.leetcode import leetcode_app
from aletheia.cli.links import links_app
from aletheia.core.fire import FIReEngine
from aletheia.core.git_sync import GitSyncError, init_data_repo, pull_data_repo, sync_data_repo
from aletheia.core.graph import KnowledgeGraph
from aletheia.core.metrics import ProgressMetrics
from aletheia.core.models import (
    AnyCard,
    CardType,
    Complexity,
    CreationMode,
    DSAConceptCard,
    DSAProblemCard,
    LeetcodeSource,
    Maturity,
    SystemDesignCard,
    card_from_dict,
    utcnow,
)
from aletheia.core.queue import QueueBuilder
from aletheia.core.scheduler import AletheiaScheduler, ReviewRating
from aletheia.core.storage import AletheiaStorage
from aletheia.llm import LLMError, LLMService

load_dotenv()

app = typer.Typer(
    name="aletheia",
    help="Personal knowledge management and spaced repetition for technical learning.",
    no_args_is_help=True,
)

# Register LeetCode subcommands
app.add_typer(leetcode_app, name="leetcode")

# Register Links subcommands
app.add_typer(links_app, name="links")

# Graph subcommand group
graph_app = typer.Typer(help="Knowledge graph queries and statistics.")
app.add_typer(graph_app, name="graph")

console = Console()


def prompt_or_editor(label: str, default: str = "", required: bool = True) -> str:
    """Prompt for input, opening $EDITOR if the user types 'e'.

    For multi-line fields (front, back, intuition, etc.), the user can either
    type a single-line value directly or type 'e' to open their editor.
    """
    hint = " ('e' for editor)" if required else " ('e' for editor, empty to skip)"
    value = typer.prompt(f"{label}{hint}", default=default)

    if value.strip().lower() == "e":
        value = open_in_editor("", suffix=".txt").strip()
        if not value and required:
            rprint("[red]Editor returned empty content.[/red]")
            raise typer.Exit(1)

    return value


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
        help="Quick add mode (skip optional fields)",
    ),
    guided: bool = typer.Option(
        False,
        "--guided",
        "-g",
        help="Use LLM-guided extraction (Mode 1: Socratic questions)",
    ),
) -> None:
    """Add a new card interactively."""
    storage = get_storage()

    if guided:
        card = _add_guided(card_type)
    elif card_type == "dsa-problem":
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
    front = prompt_or_editor("Front (question)")

    rprint("\n[dim]Enter the answer/explanation:[/dim]")
    back = prompt_or_editor("Back (answer)")

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
        intuition = prompt_or_editor("Key intuition (why does this approach work?)", required=False)
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
    front = prompt_or_editor("Front (question)")
    back = prompt_or_editor("Back (answer)")

    definition = prompt_or_editor("Definition (optional)", required=False)
    intuition = prompt_or_editor("Intuition - when/why to use (optional)", required=False)

    patterns_str = typer.prompt("Common patterns (comma-separated)", default="")
    common_patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]

    when_to_use = ""
    when_not_to_use = ""
    if not quick:
        when_to_use = prompt_or_editor("When to use (signals)", required=False)
        when_not_to_use = prompt_or_editor("When NOT to use", required=False)

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
    front = prompt_or_editor("Front (question)")
    back = prompt_or_editor("Back (answer)")

    definition = prompt_or_editor("Definition (optional)", required=False)
    how_it_works = ""
    if not quick:
        how_it_works = prompt_or_editor("How it works (optional)", required=False)

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


def _add_guided(card_type: str) -> DSAProblemCard | DSAConceptCard | SystemDesignCard | None:
    """LLM-guided card creation using Socratic questions."""
    rprint(f"\n[bold]Guided Card Creation ({card_type})[/bold]")
    rprint("[dim]The LLM will ask Socratic questions to help you articulate understanding.[/dim]\n")

    # Get initial context from user
    rprint("Describe what you learned (problem solved, concept understood, etc.):")
    context = prompt_or_editor("Context")

    if not context.strip():
        rprint("[red]Context cannot be empty.[/red]")
        return None

    # Initialize LLM service
    try:
        llm = LLMService()
    except Exception as e:
        rprint(f"[red]Failed to initialize LLM: {e}[/red]")
        rprint("[dim]Make sure ANTHROPIC_API_KEY or OPENAI_API_KEY is set.[/dim]")
        return None

    # Get Socratic questions from LLM
    rprint("\n[dim]Generating questions...[/dim]")
    try:
        questions = llm.guided_extraction(context, card_type)
    except LLMError as e:
        rprint(f"[red]LLM error: {e}[/red]")
        return None

    if not questions:
        rprint("[red]No questions generated. Please try again.[/red]")
        return None

    # Ask each question and collect answers
    rprint("\n[bold]Answer these questions to create your card:[/bold]")
    rprint("[dim]Press Enter to skip a question.[/dim]\n")
    answers = []
    for i, question in enumerate(questions, 1):
        rprint(f"[cyan]Q{i}:[/cyan] {question}")
        answer = typer.prompt("Your answer", default="")
        if answer.strip():
            answers.append((question, answer))
        rprint("")

    # Structure answers into card content
    # Use first Q&A as front/back, rest as supporting content
    front = answers[0][0] if answers else "What did you learn?"
    back = answers[0][1] if answers else context

    # Combine other answers into intuition/notes
    intuition_parts = []
    for q, a in answers[1:]:
        if a.strip():
            intuition_parts.append(f"{a}")
    intuition = " ".join(intuition_parts) if intuition_parts else None

    # Create card based on type
    if card_type == "dsa-problem":
        # Prompt for minimal required fields
        rprint("\n[bold]Additional details:[/bold]")
        platform = typer.prompt("Platform", default="leetcode")
        problem_id = typer.prompt("Problem ID", default="")
        title = typer.prompt("Problem title", default="")

        source = LeetcodeSource(
            platform=platform,
            platform_id=problem_id,
            title=title,
            url=None,
            difficulty="medium",
        )

        patterns_str = typer.prompt("Patterns (comma-separated)", default="")
        patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]

        card = DSAProblemCard(
            front=front,
            back=back,
            problem_source=source,
            patterns=patterns,
            intuition=intuition,
            creation_mode=CreationMode.GUIDED_EXTRACTION,
        )
    elif card_type == "dsa-concept":
        name = typer.prompt("Concept name", default="")
        card = DSAConceptCard(
            name=name,
            front=front,
            back=back,
            intuition=intuition,
            creation_mode=CreationMode.GUIDED_EXTRACTION,
        )
    elif card_type == "system-design":
        name = typer.prompt("Concept name", default="")
        card = SystemDesignCard(
            name=name,
            front=front,
            back=back,
            creation_mode=CreationMode.GUIDED_EXTRACTION,
        )
    else:
        rprint(f"[red]Guided mode not supported for: {card_type}[/red]")
        return None

    # Preview and confirm
    rprint("\n[bold]Preview:[/bold]")
    _display_card(card, full=True)

    # Offer to edit in $EDITOR
    if typer.confirm("\nEdit in editor before saving?", default=False):
        editable = {
            "front": card.front,
            "back": card.back,
        }
        if hasattr(card, "intuition") and card.intuition:
            editable["intuition"] = card.intuition

        content = json.dumps(editable, indent=2)
        edited = open_in_editor(content, suffix=".json")

        if edited.strip():
            try:
                data = json.loads(edited)
                card.front = data.get("front", card.front)
                card.back = data.get("back", card.back)
                if "intuition" in data and hasattr(card, "intuition"):
                    card.intuition = data.get("intuition")
            except json.JSONDecodeError:
                rprint("[yellow]Invalid JSON, keeping original content.[/yellow]")

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
    """Show details of a specific card, including FSRS review scheduling info."""
    storage = get_storage()
    card = _require_card(storage, card_id)
    review_state = storage.db.get_card_state(card.id)
    _display_card(card, full=True, review_state=review_state)


def _require_card(storage: AletheiaStorage, card_id: str) -> AnyCard:
    """Find a card by ID or exit with an error."""
    card = find_card(storage, card_id)
    if card is None:
        rprint(f"[red]Card not found: {card_id}[/red]")
        raise typer.Exit(1)
    return card


def _exhaust_card(storage: AletheiaStorage, card, reason: str) -> None:
    """Mark a card as exhausted and save it."""
    card.maturity = Maturity.EXHAUSTED
    card.lifecycle.exhausted_at = utcnow()
    card.lifecycle.exhausted_reason = reason
    storage.save_card(card)


def _display_card(card, full: bool = False, review_state: dict | None = None) -> None:
    """Display a card in a formatted panel.

    Args:
        card: The card to display.
        full: If True, show all metadata (ID, maturity, tags, etc.).
        review_state: Optional FSRS state dict from ReviewDatabase.get_card_state().
            When provided and ``full`` is True, displays the next review date,
            review state, and review count.
    """
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

        # Links
        links = card.links
        link_parts = []
        if links.prerequisite:
            link_parts.append(f"Prerequisites: {', '.join(i[:8] for i in links.prerequisite)}")
        if links.leads_to:
            link_parts.append(f"Leads to: {', '.join(i[:8] for i in links.leads_to)}")
        if links.similar_to:
            link_parts.append(f"Similar to: {', '.join(i[:8] for i in links.similar_to)}")
        if links.contrasts_with:
            link_parts.append(f"Contrasts with: {', '.join(i[:8] for i in links.contrasts_with)}")
        if links.applies:
            link_parts.append(f"Applies: {', '.join(i[:8] for i in links.applies)}")
        if links.encompasses:
            enc_strs = [f"{wl.card_id[:8]}(w={wl.weight})" for wl in links.encompasses]
            link_parts.append(f"Encompasses: {', '.join(enc_strs)}")
        if link_parts:
            content += "\n\n[bold]Links:[/bold]\n" + "\n".join(
                f"  [dim]{p}[/dim]" for p in link_parts
            )

        # FSRS review scheduling info
        content += _format_review_info(review_state)

    console.print(Panel(content, title=title, border_style="blue"))


def _format_review_info(review_state: dict | None) -> str:
    """Format FSRS review state as a string for display.

    Args:
        review_state: FSRS state dict from ReviewDatabase.get_card_state(),
            or None for cards that have never been reviewed.

    Returns:
        Formatted string with review scheduling details, prefixed with
        newlines for panel layout. Empty string if ``review_state`` is None.
    """
    if review_state is None:
        return "\n\n[dim]Next review: new card (not yet reviewed)[/dim]"

    lines: list[str] = []

    due_str = review_state.get("due")
    if due_str:
        due = datetime.fromisoformat(due_str)
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delta = due - now

        due_display = due.strftime("%Y-%m-%d %H:%M")
        if delta.total_seconds() <= 0:
            lines.append(
                f"[dim]Next review: [bold yellow]{due_display} (overdue)[/bold yellow][/dim]"
            )
        elif delta.days == 0:
            hours = int(delta.total_seconds() // 3600)
            if hours == 0:
                mins = int(delta.total_seconds() // 60)
                lines.append(f"[dim]Next review: {due_display} (in {mins}m)[/dim]")
            else:
                lines.append(f"[dim]Next review: {due_display} (in {hours}h)[/dim]")
        elif delta.days == 1:
            lines.append(f"[dim]Next review: {due_display} (tomorrow)[/dim]")
        else:
            lines.append(f"[dim]Next review: {due_display} (in {delta.days} days)[/dim]")

    state = review_state.get("state", "unknown")
    reps = review_state.get("reps", 0)
    lapses = review_state.get("lapses", 0)
    lines.append(f"[dim]State: {state} | Reviews: {reps} | Lapses: {lapses}[/dim]")

    return "\n\n" + "\n".join(lines) if lines else ""


# ============================================================================
# EDIT command
# ============================================================================


@app.command()
def edit(
    card_id: str = typer.Argument(..., help="Card ID to edit"),
    guided: bool = typer.Option(
        False,
        "--guided",
        "-g",
        help="Use LLM-guided Socratic questions to refine the card",
    ),
) -> None:
    """Edit a card in your editor."""
    storage = get_storage()
    card = _require_card(storage, card_id)

    if guided:
        _edit_guided(card, storage)
        return

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


def _build_editable_from_card(card) -> dict:
    """Extract editable fields from a card for use in the editor."""
    editable = {
        "type": card.type.value,
        "front": card.front,
        "back": card.back,
        "tags": card.tags,
        "taxonomy": card.taxonomy,
    }

    # Add type-specific fields
    if hasattr(card, "name"):
        editable["name"] = card.name
    if hasattr(card, "patterns"):
        editable["patterns"] = card.patterns
    if hasattr(card, "intuition"):
        editable["intuition"] = card.intuition or ""
    if hasattr(card, "edge_cases"):
        editable["edge_cases"] = card.edge_cases
    if hasattr(card, "definition"):
        editable["definition"] = card.definition or ""
    if hasattr(card, "when_to_use"):
        editable["when_to_use"] = card.when_to_use or ""
    if hasattr(card, "when_not_to_use"):
        editable["when_not_to_use"] = card.when_not_to_use or ""
    if hasattr(card, "how_it_works"):
        editable["how_it_works"] = card.how_it_works or ""
    if hasattr(card, "use_cases"):
        editable["use_cases"] = card.use_cases
    if hasattr(card, "anti_patterns"):
        editable["anti_patterns"] = card.anti_patterns
    if hasattr(card, "common_patterns"):
        editable["common_patterns"] = card.common_patterns
    if hasattr(card, "data_structures"):
        editable["data_structures"] = card.data_structures

    return editable


def _create_card_from_edited(edited: dict) -> AnyCard:
    """Create a new card (fresh ID) from editor output dict."""
    # Remove id if present — new card gets a fresh one
    edited.pop("id", None)
    # Remove underscore-prefixed keys (transient editor references)
    cleaned = {k: v for k, v in edited.items() if not k.startswith("_")}
    return card_from_dict(cleaned)


def _format_card_for_llm(card) -> str:
    """Convert a card to a readable string for LLM context."""
    lines = [
        f"Type: {card.type.value}",
        f"Front: {card.front}",
        f"Back: {card.back}",
    ]

    if hasattr(card, "name") and card.name:
        lines.append(f"Name: {card.name}")
    if hasattr(card, "intuition") and card.intuition:
        lines.append(f"Intuition: {card.intuition}")
    if hasattr(card, "patterns") and card.patterns:
        lines.append(f"Patterns: {', '.join(card.patterns)}")
    if hasattr(card, "edge_cases") and card.edge_cases:
        lines.append(f"Edge cases: {', '.join(card.edge_cases)}")
    if hasattr(card, "definition") and card.definition:
        lines.append(f"Definition: {card.definition}")
    if hasattr(card, "when_to_use") and card.when_to_use:
        lines.append(f"When to use: {card.when_to_use}")
    if hasattr(card, "when_not_to_use") and card.when_not_to_use:
        lines.append(f"When not to use: {card.when_not_to_use}")
    if hasattr(card, "how_it_works") and card.how_it_works:
        lines.append(f"How it works: {card.how_it_works}")
    if hasattr(card, "use_cases") and card.use_cases:
        lines.append(f"Use cases: {', '.join(card.use_cases)}")
    if hasattr(card, "anti_patterns") and card.anti_patterns:
        lines.append(f"Anti-patterns: {', '.join(card.anti_patterns)}")
    if hasattr(card, "common_patterns") and card.common_patterns:
        lines.append(f"Common patterns: {', '.join(card.common_patterns)}")
    if hasattr(card, "data_structures") and card.data_structures:
        lines.append(f"Data structures: {', '.join(card.data_structures)}")
    if hasattr(card, "complexity") and card.complexity:
        lines.append(f"Complexity: Time {card.complexity.time}, Space {card.complexity.space}")
    if card.tags:
        lines.append(f"Tags: {', '.join(card.tags)}")

    return "\n".join(lines)


def _build_edit_from_answers(card, answers: list[tuple[str, str]], new_context: str) -> dict:
    """Build an editable dict from guided Q&A answers and existing card.

    Includes transient _guided_qa_reference and _new_context keys as editor
    reference material. These underscore-prefixed keys are silently skipped
    when applying updates (no matching attribute on card).
    """
    # Build Q&A reference string
    qa_lines = []
    for q, a in answers:
        qa_lines.append(f"Q: {q}")
        qa_lines.append(f"A: {a}")
        qa_lines.append("")
    qa_reference = "\n".join(qa_lines).strip()

    editable = {
        "_guided_qa_reference": qa_reference,
        "_new_context": new_context,
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
    if hasattr(card, "intuition"):
        editable["intuition"] = card.intuition or ""
    if hasattr(card, "edge_cases"):
        editable["edge_cases"] = card.edge_cases
    if hasattr(card, "definition"):
        editable["definition"] = card.definition or ""
    if hasattr(card, "when_to_use"):
        editable["when_to_use"] = card.when_to_use or ""
    if hasattr(card, "when_not_to_use"):
        editable["when_not_to_use"] = card.when_not_to_use or ""
    if hasattr(card, "how_it_works"):
        editable["how_it_works"] = card.how_it_works or ""
    if hasattr(card, "use_cases"):
        editable["use_cases"] = card.use_cases
    if hasattr(card, "anti_patterns"):
        editable["anti_patterns"] = card.anti_patterns

    return editable


def _edit_guided(card, storage: AletheiaStorage) -> None:
    """LLM-guided card editing using Socratic questions about the delta."""
    rprint(f"\n[bold]Guided Edit ({card.type.value})[/bold]")
    rprint("[dim]The LLM will ask questions about what changed in your understanding.[/dim]\n")

    # Display existing card
    _display_card(card, full=True)

    # Get new context from user
    rprint("\nDescribe what changed in your understanding:")
    new_context = prompt_or_editor("New context")

    if not new_context.strip():
        rprint("[red]Context cannot be empty.[/red]")
        return

    # Initialize LLM service
    try:
        llm = LLMService()
    except Exception as e:
        rprint(f"[red]Failed to initialize LLM: {e}[/red]")
        rprint("[dim]Make sure ANTHROPIC_API_KEY or OPENAI_API_KEY is set.[/dim]")
        return

    # Format existing card for LLM
    existing_content = _format_card_for_llm(card)

    # Get Socratic questions from LLM
    rprint("\n[dim]Generating questions...[/dim]")
    try:
        questions = llm.guided_edit_extraction(existing_content, new_context, card.type.value)
    except LLMError as e:
        rprint(f"[red]LLM error: {e}[/red]")
        return

    if not questions:
        rprint("[red]No questions generated. Please try again.[/red]")
        return

    # Ask each question and collect answers
    rprint("\n[bold]Answer these questions to refine your card:[/bold]")
    rprint("[dim]Press Enter to skip a question.[/dim]\n")
    answers = []
    for i, question in enumerate(questions, 1):
        rprint(f"[cyan]Q{i}:[/cyan] {question}")
        answer = typer.prompt("Your answer", default="")
        if answer.strip():
            answers.append((question, answer))
        rprint("")

    # Build editable dict with Q&A reference
    editable = _build_edit_from_answers(card, answers, new_context)

    # Open in editor for fine-tuning
    content = json.dumps(editable, indent=2)
    edited_content = open_in_editor(content, suffix=".json")

    if not edited_content.strip():
        rprint("[yellow]Edit cancelled (empty content).[/yellow]")
        return

    try:
        edited = json.loads(edited_content)
    except json.JSONDecodeError as e:
        rprint(f"[red]Invalid JSON: {e}[/red]")
        return

    # Apply updates (skip underscore-prefixed keys and immutable fields)
    for key, value in edited.items():
        if key.startswith("_") or key in ["id", "type"]:
            continue
        if hasattr(card, key):
            setattr(card, key, value)

    # Handle maturity separately (it's an enum)
    if "maturity" in edited:
        card.maturity = Maturity(edited["maturity"])

    # Preview
    rprint("\n[bold]Preview:[/bold]")
    _display_card(card, full=True)

    if typer.confirm("\nSave changes?", default=True):
        path = storage.save_card(card)
        rprint(f"[green]Card updated![/green] {path}")
    else:
        rprint("[yellow]Changes discarded.[/yellow]")


# ============================================================================
# STATS command
# ============================================================================


@app.command()
def stats() -> None:
    """Show review statistics."""
    storage = get_storage()
    full = storage.get_full_stats()

    table = Table(title="Aletheia Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Cards", str(full["total_cards"]))
    table.add_row("Total Reviews", str(full["total_reviews"]))
    table.add_row("Due Today", str(full["due_today"]))
    table.add_row("New Cards", str(full["new_cards"]))
    table.add_row("Success Rate", f"{full['success_rate']:.0%}")
    table.add_row("Current Streak", f"{full['current_streak']} day(s)")
    table.add_row("Longest Streak", f"{full['longest_streak']} day(s)")

    by_type = full.get("by_type", {})
    if by_type:
        table.add_row("", "")
        table.add_row("[bold]By Type[/bold]", "")
        for card_type, count in sorted(by_type.items()):
            table.add_row(f"  {card_type}", str(count))

    by_domain = full.get("by_domain", {})
    if by_domain:
        table.add_row("", "")
        table.add_row("[bold]By Domain[/bold]", "")
        for domain, count in sorted(by_domain.items()):
            table.add_row(f"  {domain}", str(count))

    # Progress metrics
    metrics = ProgressMetrics(storage)
    mastery = metrics.mastery_percentage()
    velocity = metrics.learning_velocity()
    table.add_row("", "")
    table.add_row("[bold]Progress[/bold]", "")
    table.add_row("  Mastery", f"{mastery:.0%}")
    table.add_row("  Learning Velocity", f"{velocity:.1f} cards/week")

    auto_candidates = metrics.automaticity_candidates()
    if auto_candidates:
        table.add_row("  Automaticity Candidates", str(len(auto_candidates)))

    console.print(table)


# ============================================================================
# SEARCH command
# ============================================================================


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    card_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter results by card type (e.g. dsa-problem, dsa-concept, system-design)",
    ),
) -> None:
    """Search cards by content."""
    storage = get_storage()
    results = storage.search(query)

    # Filter by type if specified
    if card_type:
        try:
            ct = CardType(card_type)
        except ValueError:
            rprint(f"[red]Invalid card type: {card_type}[/red]")
            raise typer.Exit(1)
        results = [c for c in results if c.type == ct]

    if not results:
        rprint(f"[dim]No cards found matching '{query}'[/dim]")
        return

    rprint(f"\n[bold]Found {len(results)} card(s):[/bold]\n")

    for card in results:
        _display_card(card, full=True)
        rprint("")


@app.command()
def reindex() -> None:
    """Rebuild the search index from all cards on disk."""
    storage = get_storage()
    count = storage.reindex_all()
    rprint(f"[green]Reindexed {count} card(s).[/green]")


# ============================================================================
# CHECK command (Quality Feedback - Mode 4)
# ============================================================================


@app.command()
def check(
    card_id: str = typer.Argument(..., help="Card ID to check (or 'all')"),
) -> None:
    """Get LLM quality feedback on a card (Mode 4)."""
    storage = get_storage()

    # Handle --all case
    if card_id.lower() == "all":
        cards = storage.list_cards()
        if not cards:
            rprint("[dim]No cards found.[/dim]")
            return

        rprint(f"\n[bold]Checking {len(cards)} card(s)...[/bold]\n")
        for card in cards:
            _check_card(card)
            rprint("")
        return

    card = _require_card(storage, card_id)
    _check_card(card)


def _check_card(card) -> None:
    """Check a single card and display feedback."""
    rprint(f"[bold]Checking card:[/bold] {card.id[:8]}...")
    rprint(f"[dim]Front: {card.front[:50]}{'...' if len(card.front) > 50 else ''}[/dim]\n")

    try:
        llm = LLMService()
    except Exception as e:
        rprint(f"[red]Failed to initialize LLM: {e}[/red]")
        rprint("[dim]Make sure ANTHROPIC_API_KEY or OPENAI_API_KEY is set.[/dim]")
        return

    try:
        feedback = llm.quality_feedback(card.front, card.back, card.type.value)
    except LLMError as e:
        rprint(f"[red]LLM error: {e}[/red]")
        return

    # Display overall quality
    quality_color = {
        "good": "green",
        "needs_work": "yellow",
        "poor": "red",
    }.get(feedback.overall_quality, "white")
    rprint(f"[{quality_color}]Overall: {feedback.overall_quality.upper()}[/{quality_color}]")

    # Display strengths
    if feedback.strengths:
        rprint("\n[green]Strengths:[/green]")
        for strength in feedback.strengths:
            rprint(f"  [green]✓[/green] {strength}")

    # Display issues
    if feedback.issues:
        rprint("\n[yellow]Issues:[/yellow]")
        for issue in feedback.issues:
            rprint(f"  [yellow]⚠[/yellow] {issue.type}: {issue.description}")
            if issue.suggestion:
                rprint(f"    [dim]→ {issue.suggestion}[/dim]")

    # Display suggestions
    if feedback.suggested_front:
        rprint(f"\n[cyan]Suggested front:[/cyan] {feedback.suggested_front}")
    if feedback.suggested_back:
        rprint(f"[cyan]Suggested back:[/cyan] {feedback.suggested_back}")


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
    graph = KnowledgeGraph(storage)
    fire_engine = FIReEngine(storage, graph)
    queue_builder = QueueBuilder(storage, graph, fire_engine=fire_engine)

    # Get cards to review using queue builder (prerequisite-aware)
    due_ids = scheduler.get_due_cards(limit)
    new_ids = scheduler.get_new_cards(new_cards)
    card_ids = queue_builder.build_queue(due_ids, new_ids, new_limit=new_cards)

    # Filter out non-active cards (suspended/exhausted)
    card_ids = [
        cid for cid in card_ids if (c := storage.load_card(cid)) and c.maturity == Maturity.ACTIVE
    ]

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
        reveal_time = time.monotonic()

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

        # Compute response time (time from reveal to rating)
        response_time_ms = int((time.monotonic() - reveal_time) * 1000)

        # Process review
        result = scheduler.review_card(card_id, rating, response_time_ms=response_time_ms)
        rprint(f"[dim]Next review: {result.due_next.strftime('%Y-%m-%d %H:%M')}[/dim]")

        # FIRe: propagate credit to encompassed cards
        fire_credits = fire_engine.propagate_credit(card_id, rating.value)
        if fire_credits:
            rprint(
                f"[dim]Implicit credit propagated to {len(fire_credits)} encompassed card(s)[/dim]"
            )

        # FIRe: on AGAIN, propagate penalty upward
        if rating == ReviewRating.AGAIN:
            penalized = fire_engine.propagate_penalty(card_id)
            if penalized:
                rprint(
                    f"[yellow]Penalty flagged for {len(penalized)} encompassing card(s)[/yellow]"
                )

        # On AGAIN, suggest remediation
        if rating == ReviewRating.AGAIN:
            remediation = scheduler.get_remediation_cards(card_id, graph)
            if remediation:
                rprint(
                    f"[yellow]Suggested remediation: {len(remediation)}"
                    " prerequisite(s) may need review[/yellow]"
                )
                for rid in remediation:
                    rcard = storage.load_card(rid)
                    if rcard:
                        rprint(f"  [dim]{rid[:8]}: {rcard.front[:50]}[/dim]")

        rprint("")
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
# LIFECYCLE commands (suspend, resume, exhaust, reformulate, split, merge)
# ============================================================================


@app.command()
def suspend(
    card_id: str = typer.Argument(..., help="Card ID to suspend"),
) -> None:
    """Suspend a card (pause reviews without losing progress)."""
    storage = get_storage()
    card = _require_card(storage, card_id)

    if card.maturity == Maturity.EXHAUSTED:
        rprint(f"[red]Cannot suspend an exhausted card: {card.id[:8]}[/red]")
        raise typer.Exit(1)

    if card.maturity == Maturity.SUSPENDED:
        rprint(f"[yellow]Card is already suspended: {card.id[:8]}[/yellow]")
        return

    card.maturity = Maturity.SUSPENDED
    card.lifecycle.suspended_at = utcnow()
    storage.save_card(card)
    rprint(f"[green]Card suspended:[/green] {card.id[:8]}")


@app.command()
def resume(
    card_id: str = typer.Argument(..., help="Card ID to resume"),
) -> None:
    """Resume a suspended card (re-enable reviews)."""
    storage = get_storage()
    card = _require_card(storage, card_id)

    if card.maturity != Maturity.SUSPENDED:
        mat = card.maturity.value
        rprint(f"[yellow]Card is not suspended: {card.id[:8]} (maturity: {mat})[/yellow]")
        return

    card.maturity = Maturity.ACTIVE
    card.lifecycle.suspended_at = None
    storage.save_card(card)
    rprint(f"[green]Card resumed:[/green] {card.id[:8]}")


@app.command()
def exhaust(
    card_id: str = typer.Argument(..., help="Card ID to exhaust"),
    reason: str = typer.Option(
        "",
        "--reason",
        "-r",
        help="Reason for exhausting (e.g., understanding_deepened, duplicate, split, merged)",
    ),
) -> None:
    """Mark a card as exhausted (permanently retire from reviews)."""
    storage = get_storage()
    card = _require_card(storage, card_id)

    if card.maturity == Maturity.EXHAUSTED:
        rprint(f"[yellow]Card is already exhausted: {card.id[:8]}[/yellow]")
        return

    _display_card(card)

    if not reason:
        reason = typer.prompt(
            "Reason for exhausting",
            default="understanding_deepened",
        )

    if not typer.confirm(f"\nExhaust card {card.id[:8]}?", default=True):
        rprint("[yellow]Cancelled.[/yellow]")
        return

    _exhaust_card(storage, card, reason)
    rprint(f"[green]Card exhausted:[/green] {card.id[:8]} (reason: {reason})")


@app.command()
def revive(
    card_id: str = typer.Argument(..., help="Card ID to revive"),
) -> None:
    """Revive an exhausted card (return to active reviews)."""
    storage = get_storage()
    card = _require_card(storage, card_id)

    if card.maturity != Maturity.EXHAUSTED:
        mat = card.maturity.value
        rprint(f"[yellow]Card is not exhausted: {card.id[:8]} (maturity: {mat})[/yellow]")
        return

    card.maturity = Maturity.ACTIVE
    card.lifecycle.exhausted_at = None
    card.lifecycle.exhausted_reason = None
    storage.save_card(card)
    rprint(f"[green]Card revived:[/green] {card.id[:8]}")


# ============================================================================
# REFORMULATE command
# ============================================================================


@app.command()
def reformulate(
    card_id: str = typer.Argument(..., help="Card ID to reformulate"),
    guided: bool = typer.Option(
        False,
        "--guided",
        "-g",
        help="Use LLM-guided Socratic questions for the new card",
    ),
) -> None:
    """Create a new card from an existing one, exhausting the original."""
    storage = get_storage()
    card = _require_card(storage, card_id)

    if card.maturity == Maturity.EXHAUSTED:
        rprint(f"[red]Cannot reformulate an exhausted card: {card.id[:8]}[/red]")
        raise typer.Exit(1)

    rprint("\n[bold]Reformulating card:[/bold]")
    _display_card(card, full=True)

    if not typer.confirm("\nProceed with reformulation?", default=True):
        rprint("[yellow]Cancelled.[/yellow]")
        return

    if guided:
        new_card = _add_guided(card.type.value)
    else:
        editable = _build_editable_from_card(card)
        content = json.dumps(editable, indent=2)
        edited_content = open_in_editor(content, suffix=".json")

        if not edited_content.strip():
            rprint("[yellow]Reformulation cancelled (empty content).[/yellow]")
            return

        try:
            edited = json.loads(edited_content)
        except json.JSONDecodeError as e:
            rprint(f"[red]Invalid JSON: {e}[/red]")
            raise typer.Exit(1)

        new_card = _create_card_from_edited(edited)

    if new_card is None:
        rprint("[yellow]Reformulation cancelled.[/yellow]")
        return

    # Set lifecycle link
    new_card.lifecycle.reformulated_from = card.id

    # Save new card
    new_path = storage.save_card(new_card)
    rprint(f"\n[green]New card created:[/green] {new_card.id[:8]} ({new_path})")

    # Exhaust original
    _exhaust_card(storage, card, "understanding_deepened")
    rprint(f"[dim]Original card exhausted:[/dim] {card.id[:8]}")


# ============================================================================
# SPLIT command
# ============================================================================


@app.command()
def split(
    card_id: str = typer.Argument(..., help="Card ID to split"),
) -> None:
    """Split a card into multiple new cards, exhausting the original."""
    storage = get_storage()
    card = _require_card(storage, card_id)

    if card.maturity == Maturity.EXHAUSTED:
        rprint(f"[red]Cannot split an exhausted card: {card.id[:8]}[/red]")
        raise typer.Exit(1)

    rprint("\n[bold]Splitting card:[/bold]")
    _display_card(card, full=True)

    count = typer.prompt("\nHow many new cards?", default="2", type=int)
    if count < 2:
        rprint("[red]Must split into at least 2 cards.[/red]")
        raise typer.Exit(1)

    new_cards = []
    for i in range(count):
        rprint(f"\n[bold]--- New card {i + 1}/{count} ---[/bold]")
        editable = _build_editable_from_card(card)
        content = json.dumps(editable, indent=2)
        edited_content = open_in_editor(content, suffix=".json")

        if not edited_content.strip():
            rprint(f"[yellow]Card {i + 1} skipped (empty content).[/yellow]")
            continue

        try:
            edited = json.loads(edited_content)
        except json.JSONDecodeError as e:
            rprint(f"[red]Invalid JSON for card {i + 1}: {e}[/red]")
            continue

        new_card = _create_card_from_edited(edited)
        new_card.lifecycle.split_from = card.id
        new_cards.append(new_card)

    if not new_cards:
        rprint("[yellow]No cards created. Split cancelled.[/yellow]")
        return

    # Save all new cards
    for nc in new_cards:
        path = storage.save_card(nc)
        rprint(f"[green]New card created:[/green] {nc.id[:8]} ({path})")

    # Exhaust original
    _exhaust_card(storage, card, "split")
    rprint(f"\n[dim]Original card exhausted:[/dim] {card.id[:8]}")
    rprint(f"[bold]Split into {len(new_cards)} card(s).[/bold]")


# ============================================================================
# MERGE command
# ============================================================================


@app.command()
def merge(
    card_ids: list[str] = typer.Argument(..., help="Card IDs to merge (2 or more)"),
) -> None:
    """Merge multiple cards into one new card, exhausting all originals."""
    storage = get_storage()

    if len(card_ids) < 2:
        rprint("[red]Must provide at least 2 card IDs to merge.[/red]")
        raise typer.Exit(1)

    # Resolve all cards
    cards = []
    for cid in card_ids:
        card = _require_card(storage, cid)
        if card.maturity == Maturity.EXHAUSTED:
            rprint(f"[red]Cannot merge an exhausted card: {card.id[:8]}[/red]")
            raise typer.Exit(1)
        cards.append(card)

    # Guard: all cards must be the same type
    types = {c.type for c in cards}
    if len(types) > 1:
        rprint(
            f"[red]Cannot merge cards of different types: {', '.join(t.value for t in types)}[/red]"
        )
        raise typer.Exit(1)

    rprint("\n[bold]Merging cards:[/bold]")
    for card in cards:
        _display_card(card)
        rprint("")

    # Build combined editable
    combined = _build_editable_from_card(cards[0])
    combined["front"] = "\n---\n".join(c.front for c in cards)
    combined["back"] = "\n---\n".join(c.back for c in cards)

    # Union tags
    all_tags: list[str] = []
    for c in cards:
        for t in c.tags:
            if t not in all_tags:
                all_tags.append(t)
    combined["tags"] = all_tags

    # Union taxonomy
    all_taxonomy: list[str] = []
    for c in cards:
        for t in c.taxonomy:
            if t not in all_taxonomy:
                all_taxonomy.append(t)
    combined["taxonomy"] = all_taxonomy

    # Union list fields (type-specific)
    for field in [
        "patterns",
        "data_structures",
        "edge_cases",
        "common_patterns",
        "use_cases",
        "anti_patterns",
    ]:
        if field in combined:
            values: list[str] = []
            for c in cards:
                for v in getattr(c, field, []):
                    if v not in values:
                        values.append(v)
            combined[field] = values

    content = json.dumps(combined, indent=2)
    edited_content = open_in_editor(content, suffix=".json")

    if not edited_content.strip():
        rprint("[yellow]Merge cancelled (empty content).[/yellow]")
        return

    try:
        edited = json.loads(edited_content)
    except json.JSONDecodeError as e:
        rprint(f"[red]Invalid JSON: {e}[/red]")
        raise typer.Exit(1)

    new_card = _create_card_from_edited(edited)
    new_card.lifecycle.merged_from = [c.id for c in cards]

    # Save new card
    new_path = storage.save_card(new_card)
    rprint(f"\n[green]Merged card created:[/green] {new_card.id[:8]} ({new_path})")

    # Exhaust all originals
    for card in cards:
        _exhaust_card(storage, card, "merged")
        rprint(f"[dim]Original card exhausted:[/dim] {card.id[:8]}")

    rprint(f"\n[bold]Merged {len(cards)} cards into 1.[/bold]")


# ============================================================================
# INIT / SYNC commands
# ============================================================================


@app.command("init")
def init_cmd(
    path: str = typer.Argument(..., help="Path for the new data repository"),
) -> None:
    """Initialize a new Aletheia data repository."""
    try:
        resolved = init_data_repo(Path(path))
    except GitSyncError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    rprint(f"[green]Data repository created at:[/green] {resolved}")
    rprint("\nSet these environment variables to use it:")
    rprint(f"  ALETHEIA_DATA_DIR={resolved}")
    rprint(f"  ALETHEIA_STATE_DIR={resolved / '.aletheia'}")


@app.command()
def sync(
    pull: bool = typer.Option(
        False,
        "--pull",
        help="Pull latest changes from remote instead of pushing",
    ),
) -> None:
    """Sync the data repository (commit & push, or pull)."""
    data_dir = Path(os.environ.get("ALETHEIA_DATA_DIR", Path.cwd() / "data"))

    try:
        if pull:
            result = pull_data_repo(data_dir)
            rprint(f"[green]{result}[/green]")
            # Rebuild search index after pulling new data
            storage = get_storage()
            count = storage.reindex_all()
            rprint(f"[dim]Reindexed {count} card(s).[/dim]")
        else:
            result = sync_data_repo(data_dir)
            rprint(f"[green]{result}[/green]")
    except GitSyncError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)


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
    rprint(f"  Search: http://{host}:{port}/search")
    rprint(f"  Stats: http://{host}:{port}/stats")
    rprint("\n[dim]Press Ctrl+C to stop[/dim]\n")

    uvicorn.run(
        "aletheia.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


# ============================================================================
# GRAPH commands
# ============================================================================


@graph_app.command("frontier")
def graph_frontier(
    min_stability: float = typer.Option(
        5.0,
        "--min-stability",
        "-s",
        help="Minimum stability for a prerequisite to count as mastered",
    ),
) -> None:
    """Show cards ready to learn (prerequisites mastered)."""
    storage = get_storage()
    graph = KnowledgeGraph(storage)
    frontier = graph.get_knowledge_frontier(min_stability)

    if not frontier:
        rprint("[dim]No cards on the knowledge frontier.[/dim]")
        return

    table = Table(title=f"Knowledge Frontier ({len(frontier)} cards)")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Type", style="cyan")
    table.add_column("Front", max_width=50)
    table.add_column("Prerequisites", style="green")

    for card in frontier:
        prereq_count = len(card.links.prerequisite)
        prereq_str = str(prereq_count) if prereq_count > 0 else "none"
        table.add_row(
            card.id[:8],
            card.type.value,
            card.front[:50] + "..." if len(card.front) > 50 else card.front,
            prereq_str,
        )

    console.print(table)


@graph_app.command("prereqs")
def graph_prereqs(
    card_id: str = typer.Argument(..., help="Card ID (or partial ID)"),
    transitive: bool = typer.Option(
        False,
        "--transitive",
        "-t",
        help="Show full transitive prerequisite chain",
    ),
) -> None:
    """Show prerequisite chain for a card."""
    storage = get_storage()
    graph = KnowledgeGraph(storage)
    card = _require_card(storage, card_id)

    if transitive:
        prereqs = graph.get_transitive_prerequisites(card.id)
        title = f"Transitive Prerequisites for {card.id[:8]}"
    else:
        prereqs = graph.get_prerequisites(card.id)
        title = f"Direct Prerequisites for {card.id[:8]}"

    if not prereqs:
        rprint(f"[dim]No prerequisites for {card.id[:8]}.[/dim]")
        return

    table = Table(title=title)
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Type", style="cyan")
    table.add_column("Front", max_width=50)
    table.add_column("State", style="green")
    table.add_column("Stability", justify="right")

    for prereq in prereqs:
        state = storage.db.get_card_state(prereq.id)
        state_str = state.get("state", "?") if state else "?"
        stability_str = f"{state.get('stability', 0):.1f}" if state else "?"
        table.add_row(
            prereq.id[:8],
            prereq.type.value,
            prereq.front[:50] + "..." if len(prereq.front) > 50 else prereq.front,
            state_str,
            stability_str,
        )

    console.print(table)


@graph_app.command("stats")
def graph_stats() -> None:
    """Show knowledge graph statistics."""
    storage = get_storage()
    graph = KnowledgeGraph(storage)
    stats_data = graph.get_graph_stats()

    table = Table(title="Knowledge Graph Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Nodes", str(stats_data["total_nodes"]))
    table.add_row("Total Edges", str(stats_data["total_edges"]))
    table.add_row("Orphan Cards", str(stats_data["orphans"]))
    table.add_row("Max Prereq Depth", str(stats_data["max_depth"]))

    console.print(table)


# ============================================================================
# Main entry point
# ============================================================================


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
