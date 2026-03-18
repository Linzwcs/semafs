"""LLMAdapter - LLM API call protocol."""

from typing import Protocol, runtime_checkable

from ..core.snapshot import Snapshot


@runtime_checkable
class LLMAdapter(Protocol):
    """LLM API call interface."""

    async def call(self, snapshot: Snapshot) -> dict:
        """
        Call LLM with snapshot context.

        Returns raw LLM response as dict.
        """
        ...
