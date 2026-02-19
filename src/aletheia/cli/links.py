"""CLI subcommands for managing card links."""

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from aletheia.cli.helpers import find_card, get_storage
from aletheia.core.graph import KnowledgeGraph
from aletheia.core.models import LinkType, WeightedLink

links_app = typer.Typer(help="Manage links between cards.")


@links_app.command("show")
def links_show(
    card_id: str = typer.Argument(..., help="Card ID (or partial ID)"),
) -> None:
    """Show all links for a card."""
    storage = get_storage()
    card = find_card(storage, card_id)
    if card is None:
        rprint(f"[red]Card not found: {card_id}[/red]")
        raise typer.Exit(1)

    links = card.links
    has_links = False

    def _show_link_list(label: str, ids: list[str]) -> None:
        nonlocal has_links
        for lid in ids:
            target = storage.load_card(lid)
            name = target.front[:50] if target else "(missing)"
            rprint(f"  [cyan]{label}[/cyan] → {lid[:8]}: {name}")
            has_links = True

    rprint(f"\n[bold]Links for {card.id[:8]}[/bold]")
    _show_link_list("prerequisite", links.prerequisite)
    _show_link_list("leads_to", links.leads_to)
    _show_link_list("similar_to", links.similar_to)
    _show_link_list("contrasts_with", links.contrasts_with)
    _show_link_list("applies", links.applies)
    for enc in links.encompasses:
        target = storage.load_card(enc.card_id)
        name = target.front[:50] if target else "(missing)"
        rprint(f"  [cyan]encompasses[/cyan] → {enc.card_id[:8]} (w={enc.weight}): {name}")
        has_links = True

    # Show reverse links
    graph = KnowledgeGraph(storage)
    dependents = graph.get_dependents(card.id)
    for dep in dependents:
        rprint(f"  [dim]← prerequisite of[/dim] {dep.id[:8]}: {dep.front[:50]}")
        has_links = True
    encompassing = graph.get_encompassing(card.id)
    for enc_card, weight in encompassing:
        rprint(
            f"  [dim]← encompassed by[/dim] {enc_card.id[:8]} (w={weight}): {enc_card.front[:50]}"
        )
        has_links = True

    if not has_links:
        rprint("  [dim]No links.[/dim]")


@links_app.command("add")
def links_add(
    source_id: str = typer.Argument(..., help="Source card ID"),
    target_id: str = typer.Argument(..., help="Target card ID"),
    link_type: str = typer.Argument(
        ...,
        help="Link type (prerequisite, leads_to, similar_to, contrasts_with, applies, encompasses)",
    ),
    weight: float = typer.Option(
        1.0, "--weight", "-w", help="Weight for encompasses links (0.0-1.0)"
    ),
) -> None:
    """Add a link between two cards."""
    storage = get_storage()
    source = find_card(storage, source_id)
    target = find_card(storage, target_id)

    if source is None:
        rprint(f"[red]Source card not found: {source_id}[/red]")
        raise typer.Exit(1)
    if target is None:
        rprint(f"[red]Target card not found: {target_id}[/red]")
        raise typer.Exit(1)

    try:
        lt = LinkType(link_type)
    except ValueError:
        rprint(f"[red]Invalid link type: {link_type}[/red]")
        rprint(f"Valid types: {', '.join(t.value for t in LinkType)}")
        raise typer.Exit(1)

    if lt == LinkType.ENCOMPASSES:
        # Check for duplicates
        if any(wl.card_id == target.id for wl in source.links.encompasses):
            rprint("[yellow]Link already exists.[/yellow]")
            return
        source.links.encompasses.append(WeightedLink(card_id=target.id, weight=weight))
    else:
        link_list = getattr(source.links, lt.value)
        if target.id in link_list:
            rprint("[yellow]Link already exists.[/yellow]")
            return
        link_list.append(target.id)

    storage.save_card(source)
    rprint(f"[green]Link added:[/green] {source.id[:8]} --{lt.value}--> {target.id[:8]}")


@links_app.command("remove")
def links_remove(
    source_id: str = typer.Argument(..., help="Source card ID"),
    target_id: str = typer.Argument(..., help="Target card ID"),
    link_type: str = typer.Argument(..., help="Link type"),
) -> None:
    """Remove a link between two cards."""
    storage = get_storage()
    source = find_card(storage, source_id)
    target = find_card(storage, target_id)

    if source is None:
        rprint(f"[red]Source card not found: {source_id}[/red]")
        raise typer.Exit(1)
    if target is None:
        rprint(f"[red]Target card not found: {target_id}[/red]")
        raise typer.Exit(1)

    try:
        lt = LinkType(link_type)
    except ValueError:
        rprint(f"[red]Invalid link type: {link_type}[/red]")
        raise typer.Exit(1)

    if lt == LinkType.ENCOMPASSES:
        original_len = len(source.links.encompasses)
        source.links.encompasses = [
            wl for wl in source.links.encompasses if wl.card_id != target.id
        ]
        if len(source.links.encompasses) == original_len:
            rprint("[yellow]Link not found.[/yellow]")
            return
    else:
        link_list = getattr(source.links, lt.value)
        if target.id not in link_list:
            rprint("[yellow]Link not found.[/yellow]")
            return
        link_list.remove(target.id)

    storage.save_card(source)
    rprint(f"[green]Link removed:[/green] {source.id[:8]} --{lt.value}--> {target.id[:8]}")


@links_app.command("suggest")
def links_suggest(
    card_id: str = typer.Argument(..., help="Card ID to suggest links for"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max candidate cards to consider"),
) -> None:
    """Use LLM to suggest links for a card."""
    storage = get_storage()
    card = find_card(storage, card_id)
    if card is None:
        rprint(f"[red]Card not found: {card_id}[/red]")
        raise typer.Exit(1)

    from aletheia.llm import LLMError, LLMService

    try:
        llm = LLMService()
    except Exception as e:
        rprint(f"[red]Failed to initialize LLM: {e}[/red]")
        raise typer.Exit(1)

    # Get candidate cards (exclude the target card itself)
    all_cards = storage.list_cards()
    candidates = [
        {"id": c.id, "front": c.front, "back": c.back, "type": c.type.value}
        for c in all_cards
        if c.id != card.id
    ][:limit]

    if not candidates:
        rprint("[dim]No candidate cards to link to.[/dim]")
        return

    rprint(f"[dim]Analyzing {len(candidates)} candidate(s)...[/dim]")
    try:
        suggestions = llm.suggest_links(card.front, card.back, card.id, candidates)
    except LLMError as e:
        rprint(f"[red]LLM error: {e}[/red]")
        raise typer.Exit(1)

    if not suggestions:
        rprint("[dim]No links suggested.[/dim]")
        return

    # Present each suggestion for review
    accepted = []
    for i, suggestion in enumerate(suggestions, 1):
        target = storage.load_card(suggestion.target_id)
        target_name = target.front[:60] if target else "(unknown)"

        content = (
            f"[bold]Type:[/bold] {suggestion.link_type}\n"
            f"[bold]Target:[/bold] {suggestion.target_id[:8]}: {target_name}\n"
        )
        if suggestion.weight is not None:
            content += f"[bold]Weight:[/bold] {suggestion.weight}\n"
        content += f"[bold]Rationale:[/bold] {suggestion.rationale}"

        from rich.console import Console

        Console().print(Panel(content, title=f"Suggestion {i}/{len(suggestions)}"))

        choice = typer.prompt("[a]ccept / [s]kip / [q]uit", default="s")
        if choice.lower() == "a":
            accepted.append(suggestion)
        elif choice.lower() == "q":
            break

    if not accepted:
        rprint("[dim]No links accepted.[/dim]")
        return

    # Apply accepted suggestions
    rprint(f"\n[bold]Applying {len(accepted)} link(s)...[/bold]")
    for suggestion in accepted:
        lt = suggestion.link_type
        if lt == "encompasses":
            w = suggestion.weight if suggestion.weight is not None else 1.0
            if not any(wl.card_id == suggestion.target_id for wl in card.links.encompasses):
                card.links.encompasses.append(WeightedLink(card_id=suggestion.target_id, weight=w))
        elif hasattr(card.links, lt):
            link_list = getattr(card.links, lt)
            if suggestion.target_id not in link_list:
                link_list.append(suggestion.target_id)

    storage.save_card(card)
    rprint(f"[green]{len(accepted)} link(s) saved.[/green]")


@links_app.command("health")
def links_health() -> None:
    """Check graph health: orphans, broken links, cycles."""
    storage = get_storage()
    graph = KnowledgeGraph(storage)
    all_cards = storage.list_cards()
    card_ids = {c.id for c in all_cards}

    broken = []
    cycle_suspects = []

    for card in all_cards:
        # Check for broken links (pointing to non-existent cards)
        all_link_ids = (
            card.links.prerequisite
            + card.links.leads_to
            + card.links.similar_to
            + card.links.contrasts_with
            + card.links.applies
            + [wl.card_id for wl in card.links.encompasses]
        )
        for lid in all_link_ids:
            if lid not in card_ids:
                broken.append((card.id, lid))

        # Check for self-referencing prerequisite cycles
        if card.id in card.links.prerequisite:
            cycle_suspects.append(card.id)

    stats = graph.get_graph_stats()

    table = Table(title="Graph Health Report")
    table.add_column("Check", style="cyan")
    table.add_column("Result", justify="right")

    table.add_row("Total Nodes", str(stats["total_nodes"]))
    table.add_row("Total Edges", str(stats["total_edges"]))
    table.add_row("Orphan Cards", str(stats["orphans"]))
    table.add_row("Max Prereq Depth", str(stats["max_depth"]))
    table.add_row("Broken Links", str(len(broken)))
    table.add_row("Self-Referencing Cycles", str(len(cycle_suspects)))

    from rich.console import Console

    Console().print(table)

    if broken:
        rprint("\n[yellow]Broken links:[/yellow]")
        for source_id, target_id in broken:
            rprint(f"  {source_id[:8]} → {target_id[:8]} (missing)")

    if cycle_suspects:
        rprint("\n[yellow]Self-referencing cards:[/yellow]")
        for cid in cycle_suspects:
            rprint(f"  {cid[:8]}")
