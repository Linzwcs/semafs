"""Rule-based summarization algorithm."""

from ...core.snapshot import Snapshot
from ...ports.summarizer import Summarizer


class RuleSummarizer(Summarizer):
    """Rule summarizer that concatenates local child snippets."""

    @staticmethod
    def _rule_summary(snapshot: Snapshot) -> str:
        parts = []
        for leaf in snapshot.leaves:
            if leaf.content:
                parts.append(leaf.content[:100])
        for pending in snapshot.pending:
            if pending.content:
                parts.append(pending.content[:100])
        for sub in snapshot.subcategories:
            if sub.summary:
                parts.append(sub.summary[:100])

        if not parts:
            return snapshot.target.summary or ""

        return "; ".join(parts)[:500]

    async def summarize(
        self,
        snapshot: Snapshot,
    ) -> tuple[str, tuple[str, ...] | None]:
        return self._rule_summary(snapshot), None
