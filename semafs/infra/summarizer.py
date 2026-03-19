"""Summarizer implementations."""

from ..core.snapshot import Snapshot


class RuleSummarizer:
    """Rule-based summarizer — concatenates leaf content, no LLM."""

    async def summarize(self, snapshot: Snapshot) -> str:
        """Generate summary by concatenating child content."""
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

    async def summarize_with_keywords(
        self,
        snapshot: Snapshot,
    ) -> tuple[str, tuple[str, ...] | None]:
        """Rule summarizer does not generate keywords."""
        return await self.summarize(snapshot), None


class LLMSummarizer:
    """LLM-powered summarizer — calls LLM to generate category summary."""

    def __init__(self, adapter):
        self._adapter = adapter

    async def summarize(self, snapshot: Snapshot) -> str:
        """Compatibility wrapper returning summary only."""
        summary, _ = await self.summarize_with_keywords(snapshot)
        return summary

    async def summarize_with_keywords(
        self,
        snapshot: Snapshot,
    ) -> tuple[str, tuple[str, ...] | None]:
        """Generate summary via LLM call."""
        has_context = bool(snapshot.leaves or snapshot.pending
                           or snapshot.subcategories)

        if not has_context:
            return snapshot.target.summary or "", None

        try:
            result = await self._adapter.call_summary(snapshot)
            summary = str(result.get("summary", "")).strip()
            raw_keywords = result.get("keywords", [])
            if isinstance(raw_keywords, list):
                keywords = tuple(
                    str(v).strip() for v in raw_keywords
                    if isinstance(v, str) and str(v).strip())
            else:
                keywords = ()

            if summary:
                return summary[:500], (keywords or None)
            return snapshot.target.summary or "", (keywords or None)
        except Exception:
            # Keep existing summary if LLM call fails.
            return snapshot.target.summary or "", None
