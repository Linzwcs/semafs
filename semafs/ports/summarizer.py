"""Summarizer - Content summarization protocol."""

from typing import Protocol, runtime_checkable

from ..core.snapshot import Snapshot


@runtime_checkable
class Summarizer(Protocol):
    """Content summarization interface."""

    async def summarize(self, snapshot: Snapshot) -> str:
        """
        Generate summary for category from snapshot.

        Returns:
            New summary text
        """
        ...
