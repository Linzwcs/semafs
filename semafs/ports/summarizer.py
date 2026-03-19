"""Summarizer - Content summarization protocol."""

from typing import Protocol, runtime_checkable

from ..core.snapshot import Snapshot


@runtime_checkable
class Summarizer(Protocol):
    """Content summarization interface."""

    async def summarize(
        self,
        snapshot: Snapshot,
    ) -> tuple[str, tuple[str, ...] | None]:
        """
        Generate summary and optional keywords.

        Returns:
            (summary, keywords or None)
        """
        ...
