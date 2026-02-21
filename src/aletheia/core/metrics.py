"""Progress metrics and automaticity analysis."""

from aletheia.core.storage import AletheiaStorage


class ProgressMetrics:
    """Computes learning progress metrics from review data."""

    def __init__(self, storage: AletheiaStorage):
        self.storage = storage

    def mastery_percentage(self) -> float:
        """Fraction of cards in 'review' state (mastered).

        Returns 0.0 if there are no cards.
        """
        with self.storage.db._connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM card_states").fetchone()[0]
            if total == 0:
                return 0.0
            review = conn.execute(
                "SELECT COUNT(*) FROM card_states WHERE state = 'review'"
            ).fetchone()[0]
            return review / total

    def learning_velocity(self, window_days: int = 7) -> float:
        """Cards reaching REVIEW state per week within the given window.

        Counts review_logs entries where state_after='review' and
        state_before != 'review' within the window.
        """
        with self.storage.db._connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM review_logs
                WHERE state_after = 'review'
                  AND state_before != 'review'
                  AND reviewed_at >= datetime('now', ?)
                """,
                (f"-{window_days} days",),
            ).fetchone()
            count = row["cnt"]
            # Normalize to per-week rate
            weeks = window_days / 7.0
            return count / weeks if weeks > 0 else 0.0

    def automaticity_candidates(
        self,
        min_stability: float = 30.0,
        max_response_ms: int = 5000,
    ) -> list[dict]:
        """Cards with high stability but slow response times.

        These are cards the user "knows" but hasn't automated — they
        recall correctly but take a long time.
        """
        with self.storage.db._connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    cs.card_id,
                    cs.stability,
                    AVG(rl.response_time_ms) as avg_response_ms,
                    COUNT(rl.response_time_ms) as response_count
                FROM card_states cs
                JOIN review_logs rl ON cs.card_id = rl.card_id
                WHERE cs.state = 'review'
                  AND cs.stability >= ?
                  AND rl.response_time_ms IS NOT NULL
                GROUP BY cs.card_id
                HAVING avg_response_ms > ? AND response_count >= 3
                ORDER BY avg_response_ms DESC
                """,
                (min_stability, max_response_ms),
            ).fetchall()
            return [dict(row) for row in rows]
