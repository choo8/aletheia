"""Knowledge graph service for querying card relationships."""

from collections import deque

from aletheia.core.models import AnyCard
from aletheia.core.storage import AletheiaStorage


class KnowledgeGraph:
    """Query layer over card link relationships.

    Provides methods to traverse prerequisite chains, encompass relationships,
    and compute the knowledge frontier (cards ready to learn).
    """

    def __init__(self, storage: AletheiaStorage):
        self.storage = storage

    def get_prerequisites(self, card_id: str) -> list[AnyCard]:
        """Get direct prerequisite cards for a given card."""
        card = self.storage.load_card(card_id)
        if card is None:
            return []
        result = []
        for prereq_id in card.links.prerequisite:
            prereq = self.storage.load_card(prereq_id)
            if prereq is not None:
                result.append(prereq)
        return result

    def get_transitive_prerequisites(self, card_id: str) -> list[AnyCard]:
        """Get all transitive prerequisite cards via BFS with cycle detection."""
        visited: set[str] = set()
        queue: deque[str] = deque()
        result: list[AnyCard] = []

        # Seed with direct prerequisites
        card = self.storage.load_card(card_id)
        if card is None:
            return []

        for prereq_id in card.links.prerequisite:
            if prereq_id not in visited:
                queue.append(prereq_id)
                visited.add(prereq_id)

        while queue:
            current_id = queue.popleft()
            current = self.storage.load_card(current_id)
            if current is None:
                continue
            result.append(current)
            for prereq_id in current.links.prerequisite:
                if prereq_id not in visited:
                    visited.add(prereq_id)
                    queue.append(prereq_id)

        return result

    def get_encompassed(self, card_id: str) -> list[tuple[AnyCard, float]]:
        """Get cards that this card encompasses, with weights."""
        card = self.storage.load_card(card_id)
        if card is None:
            return []
        result = []
        for link in card.links.encompasses:
            target = self.storage.load_card(link.card_id)
            if target is not None:
                result.append((target, link.weight))
        return result

    def get_encompassing(self, card_id: str) -> list[tuple[AnyCard, float]]:
        """Get cards that encompass this card (reverse lookup)."""
        result = []
        for card in self.storage.list_cards():
            for link in card.links.encompasses:
                if link.card_id == card_id:
                    result.append((card, link.weight))
        return result

    def get_dependents(self, card_id: str) -> list[AnyCard]:
        """Get cards that have this card as a prerequisite (reverse lookup)."""
        result = []
        for card in self.storage.list_cards():
            if card_id in card.links.prerequisite:
                result.append(card)
        return result

    def get_knowledge_frontier(self, min_stability: float = 5.0) -> list[AnyCard]:
        """Get NEW cards whose prerequisites are all mastered.

        A card is on the frontier if:
        - It has state='new' (never reviewed)
        - All its prerequisite cards have state='review' and stability >= min_stability
        - Cards with no prerequisites are also on the frontier
        """
        frontier = []
        for card in self.storage.list_cards():
            state = self.storage.db.get_card_state(card.id)
            if state is None or state.get("state") != "new":
                continue
            if self.prerequisites_mastered(card.id, min_stability):
                frontier.append(card)
        return frontier

    def prerequisites_mastered(self, card_id: str, min_stability: float = 5.0) -> bool:
        """Check if all prerequisites of a card are mastered.

        A prerequisite is mastered if its FSRS state is 'review' and
        stability >= min_stability.  Returns True if the card has no
        prerequisites.
        """
        card = self.storage.load_card(card_id)
        if card is None:
            return False
        if not card.links.prerequisite:
            return True
        for prereq_id in card.links.prerequisite:
            state = self.storage.db.get_card_state(prereq_id)
            if state is None:
                return False
            if state.get("state") != "review":
                return False
            if (state.get("stability") or 0.0) < min_stability:
                return False
        return True

    def get_graph_stats(self) -> dict:
        """Get statistics about the knowledge graph.

        Returns a dict with:
        - total_nodes: total number of cards
        - total_edges: total number of link relationships
        - orphans: cards with no links at all
        - max_depth: maximum prerequisite chain depth
        """
        cards = self.storage.list_cards()
        total_nodes = len(cards)
        total_edges = 0
        orphans = 0

        for card in cards:
            links = card.links
            edge_count = (
                len(links.similar_to)
                + len(links.prerequisite)
                + len(links.leads_to)
                + len(links.applies)
                + len(links.contrasts_with)
                + len(links.encompasses)
            )
            total_edges += edge_count
            if edge_count == 0:
                # Also check if any other card links TO this card
                has_incoming = False
                for other in cards:
                    if other.id == card.id:
                        continue
                    if card.id in other.links.similar_to:
                        has_incoming = True
                        break
                    if card.id in other.links.prerequisite:
                        has_incoming = True
                        break
                    if card.id in other.links.leads_to:
                        has_incoming = True
                        break
                    if card.id in other.links.applies:
                        has_incoming = True
                        break
                    if card.id in other.links.contrasts_with:
                        has_incoming = True
                        break
                    if any(wl.card_id == card.id for wl in other.links.encompasses):
                        has_incoming = True
                        break
                if not has_incoming:
                    orphans += 1

        # Compute max prerequisite depth via iterative DFS
        max_depth = 0
        for card in cards:
            if card.links.prerequisite:
                depth = self._prereq_depth(card.id, set())
                max_depth = max(max_depth, depth)

        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "orphans": orphans,
            "max_depth": max_depth,
        }

    def _prereq_depth(self, card_id: str, visited: set[str]) -> int:
        """Compute the longest prerequisite chain depth from a card."""
        if card_id in visited:
            return 0  # Cycle detected
        visited.add(card_id)
        card = self.storage.load_card(card_id)
        if card is None or not card.links.prerequisite:
            return 0
        max_child = 0
        for prereq_id in card.links.prerequisite:
            depth = self._prereq_depth(prereq_id, visited.copy())
            max_child = max(max_child, depth)
        return 1 + max_child
