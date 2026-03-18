"""Placer - Routing strategy protocol."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Placer(Protocol):
    """Routing strategy interface."""

    async def place(self, content: str, hint: str | None) -> str:
        """
        Determine target path for new content.

        Args:
            content: Content to place
            hint: Optional path hint from user

        Returns:
            Target category path
        """
        ...
