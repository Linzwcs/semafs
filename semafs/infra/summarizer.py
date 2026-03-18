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


class LLMSummarizer:
    """LLM-powered summarizer — calls LLM to generate category summary."""

    def __init__(self, adapter):
        self._adapter = adapter

    async def summarize(self, snapshot: Snapshot) -> str:
        """Generate summary via LLM call."""
        parts = []
        for leaf in snapshot.leaves + snapshot.pending:
            if leaf.content:
                parts.append(f"- {leaf.content[:150]}")
        for sub in snapshot.subcategories:
            if sub.summary:
                parts.append(f"- [category] {sub.summary[:150]}")

        if not parts:
            return snapshot.target.summary or ""

        content = "\n".join(parts)
        prompt = (
            f"Summarize the following items under category "
            f"'{snapshot.target.name}' in 1-2 sentences:\n{content}"
        )

        try:
            result = await self._adapter.call(snapshot)
            return result.get("updated_content", "")[:500] or snapshot.target.summary or ""
        except Exception:
            # Fallback to rule-based
            return "; ".join(p.lstrip("- ") for p in parts)[:500]
