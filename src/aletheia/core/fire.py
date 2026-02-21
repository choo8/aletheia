"""FIRe — Fractional Implicit Repetition engine.

Propagates fractional review credit through encompasses links and selects
minimum covering sets of due cards to reduce review queue size.
"""

from datetime import UTC, datetime, timedelta

from aletheia.core.graph import KnowledgeGraph
from aletheia.core.storage import AletheiaStorage

# Rating factor: how much credit cascades down on each rating
_RATING_FACTOR = {
    1: 0.0,  # AGAIN — no implicit credit
    2: 0.4,  # HARD
    3: 0.8,  # GOOD
    4: 1.0,  # EASY
}


class FIReEngine:
    """Propagates fractional review credit through encompasses links."""

    def __init__(self, storage: AletheiaStorage, graph: KnowledgeGraph):
        self.storage = storage
        self.graph = graph

    def propagate_credit(
        self,
        reviewed_card_id: str,
        rating: int,
    ) -> list[tuple[str, float]]:
        """Propagate fractional credit to encompassed cards.

        For each encompassed card: credit = weight * rating_factor.
        Multi-level: credit cascades through transitive encompasses
        with multiplicative decay.

        Returns list of (card_id, credit) tuples.
        """
        factor = _RATING_FACTOR.get(rating, 0.0)
        if factor == 0.0:
            return []

        credits: list[tuple[str, float]] = []
        self._propagate_recursive(reviewed_card_id, reviewed_card_id, factor, credits, set())
        return credits

    def _propagate_recursive(
        self,
        source_id: str,
        current_id: str,
        accumulated_factor: float,
        credits: list[tuple[str, float]],
        visited: set[str],
    ) -> None:
        """Recursively propagate credit through encompasses links."""
        if current_id in visited:
            return
        visited.add(current_id)

        encompassed = self.graph.get_encompassed(current_id)
        for target_card, weight in encompassed:
            credit = weight * accumulated_factor
            if credit > 0.01:  # Minimum threshold
                credits.append((target_card.id, credit))
                self.storage.db.log_implicit_credit(target_card.id, source_id, credit)
                # Cascade deeper with decayed factor
                self._propagate_recursive(source_id, target_card.id, credit, credits, visited)

    def propagate_penalty(self, reviewed_card_id: str) -> list[str]:
        """On AGAIN: penalize cards that encompass the failed card.

        If a sub-skill fails, the encompassing card's mastery is suspect.
        Returns list of penalized card IDs (for UI feedback).
        """
        encompassing = self.graph.get_encompassing(reviewed_card_id)
        penalized = []
        for parent_card, weight in encompassing:
            if weight >= 0.3:  # Only penalize if significant overlap
                penalized.append(parent_card.id)
        return penalized

    def compute_covering_set(self, due_card_ids: list[str]) -> list[str]:
        """Greedy set-cover: prefer encompassing cards to reduce queue.

        For each encompassing card in the due set, compute how many
        other due cards it covers. Greedily pick the card with max
        coverage, remove covered cards from the due set, repeat.
        """
        if not due_card_ids:
            return []

        due_set = set(due_card_ids)
        result: list[str] = []

        # Build coverage map: card_id -> set of due cards it encompasses
        coverage: dict[str, set[str]] = {}
        for cid in due_card_ids:
            encompassed = self.graph.get_encompassed(cid)
            covered = {t.id for t, w in encompassed if t.id in due_set and w >= 0.5}
            if covered:
                coverage[cid] = covered

        # Greedy set cover
        while due_set:
            # Find the card with the most coverage of remaining due cards
            best_id = None
            best_covered: set[str] = set()

            for cid in list(due_set):
                if cid in coverage:
                    current_covered = coverage[cid] & due_set
                    if len(current_covered) > len(best_covered):
                        best_id = cid
                        best_covered = current_covered

            if best_id is None or not best_covered:
                # No more covering cards; add remaining individually
                result.extend(sorted(due_set))
                break

            result.append(best_id)
            # Remove the covering card and all covered cards
            due_set.discard(best_id)
            due_set -= best_covered

        return result

    def apply_implicit_extension(self, card_id: str) -> datetime | None:
        """If enough implicit credit accumulated, push due date forward.

        Checks credit accumulated since the card's last review. If
        cumulative credit >= 0.5, extends the due date proportionally.

        Returns the new due date, or None if no extension applied.
        """
        state = self.storage.db.get_card_state(card_id)
        if state is None:
            return None

        last_review_str = state.get("last_review")
        due_str = state.get("due")
        if not last_review_str or not due_str:
            return None

        credit = self.storage.db.get_implicit_credit_since(card_id, last_review_str)
        if credit < 0.5:
            return None

        # Extend due date by credit * remaining_interval
        due = datetime.fromisoformat(due_str)
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        last_review = datetime.fromisoformat(last_review_str)
        if last_review.tzinfo is None:
            last_review = last_review.replace(tzinfo=UTC)

        interval = (due - last_review).total_seconds()
        extension_seconds = interval * min(credit, 1.0) * 0.5  # Conservative: 50% of credit
        new_due = due + timedelta(seconds=extension_seconds)

        # Update the due date in the database
        self.storage.db.upsert_card_state(
            card_id=card_id,
            stability=state.get("stability", 0.0),
            difficulty=state.get("difficulty", 0.0),
            due=new_due,
            last_review=last_review,
            reps=state.get("reps", 0),
            lapses=state.get("lapses", 0),
            state=state.get("state", "new"),
        )

        return new_due
