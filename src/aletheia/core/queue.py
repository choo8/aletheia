"""Prerequisite-aware queue builder with non-interference and interleaving."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aletheia.core.graph import KnowledgeGraph
from aletheia.core.storage import AletheiaStorage

if TYPE_CHECKING:
    from aletheia.core.fire import FIReEngine


class QueueBuilder:
    """Builds review queues that respect prerequisite ordering,
    minimize interference between similar cards, and interleave
    cards from different taxonomy branches.
    """

    def __init__(
        self,
        storage: AletheiaStorage,
        graph: KnowledgeGraph,
        fire_engine: FIReEngine | None = None,
    ):
        self.storage = storage
        self.graph = graph
        self.fire_engine = fire_engine

    def build_queue(
        self,
        due_ids: list[str],
        new_ids: list[str],
        new_limit: int = 5,
    ) -> list[str]:
        """Build an ordered review queue.

        1. Filter new cards to only those whose prerequisites are mastered.
        2. Combine due + eligible new (respecting new_limit).
        3. Apply non-interference spacing for similar_to/contrasts_with pairs.
        4. Interleave by taxonomy branch.
        """
        eligible_new = self._filter_prerequisite_ready(new_ids)[:new_limit]
        combined = due_ids + [c for c in eligible_new if c not in due_ids]

        # Apply FIRe covering set to reduce due cards
        if self.fire_engine and due_ids:
            covered_due = self.fire_engine.compute_covering_set(due_ids)
            # Replace due portion with covering set, keep new cards
            combined = covered_due + [c for c in eligible_new if c not in covered_due]

        combined = self._apply_non_interference(combined)
        combined = self._apply_interleaving(combined)

        return combined

    def _filter_prerequisite_ready(self, card_ids: list[str]) -> list[str]:
        """Filter to cards whose prerequisites are all mastered."""
        return [cid for cid in card_ids if self.graph.prerequisites_mastered(cid)]

    def _apply_non_interference(self, card_ids: list[str]) -> list[str]:
        """Maximize distance between similar_to/contrasts_with pairs.

        Uses greedy insertion: build the queue one card at a time,
        placing each card at the position that maximizes minimum
        distance to any conflicting card already placed.
        """
        if len(card_ids) <= 2:
            return card_ids

        # Build conflict sets: card_id -> set of conflicting card_ids
        conflicts: dict[str, set[str]] = {}
        for cid in card_ids:
            card = self.storage.load_card(cid)
            if card is None:
                conflicts[cid] = set()
                continue
            related = set(card.links.similar_to) | set(card.links.contrasts_with)
            conflicts[cid] = related & set(card_ids)

        # Check if any conflicts exist at all
        has_conflicts = any(bool(s) for s in conflicts.values())
        if not has_conflicts:
            return card_ids

        # Separate into non-conflicting and conflicting items.
        # Place non-conflicting first to create gaps, then greedily
        # insert conflicting items to maximize distance.
        no_conflict = [c for c in card_ids if not conflicts.get(c)]
        has_conflict = [c for c in card_ids if conflicts.get(c)]

        result: list[str] = list(no_conflict)

        for cid in has_conflict:
            if not result:
                result.append(cid)
                continue

            best_pos = len(result)
            best_min_dist = -1
            my_conflicts = conflicts[cid]

            for pos in range(len(result) + 1):
                min_dist = float("inf")
                for i, placed in enumerate(result):
                    if placed in my_conflicts:
                        if i < pos:
                            dist = pos - i
                        else:
                            dist = i + 1 - pos
                        min_dist = min(min_dist, dist)

                if min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_pos = pos

            result.insert(best_pos, cid)

        return result

    def _apply_interleaving(self, card_ids: list[str]) -> list[str]:
        """Interleave cards from different taxonomy branches.

        Round-robin by first taxonomy element to avoid clustering
        cards from the same domain.
        """
        if len(card_ids) <= 2:
            return card_ids

        # Group by first taxonomy element
        buckets: dict[str, list[str]] = {}
        for cid in card_ids:
            card = self.storage.load_card(cid)
            branch = card.taxonomy[0] if card and card.taxonomy else "_none"
            buckets.setdefault(branch, []).append(cid)

        # If only one bucket, no interleaving needed
        if len(buckets) <= 1:
            return card_ids

        # Round-robin across buckets
        result: list[str] = []
        bucket_lists = list(buckets.values())
        max_len = max(len(b) for b in bucket_lists)

        for i in range(max_len):
            for bucket in bucket_lists:
                if i < len(bucket):
                    result.append(bucket[i])

        return result
