"""LLM-powered summarization algorithm."""

from ...core.snapshot import Snapshot
from ...ports.llm import LLMAdapter
from ...ports.summarizer import Summarizer


class LLMSummarizer(Summarizer):
    """Generate category summary and keywords through LLM."""

    def __init__(self, adapter: LLMAdapter):
        self._adapter = adapter

    async def summarize(
        self,
        snapshot: Snapshot,
    ) -> tuple[str, tuple[str, ...] | None]:
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
            return snapshot.target.summary or "", None
