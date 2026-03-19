"""Placer - Routing strategy protocol."""

from typing import Protocol, runtime_checkable

from ..core.placement import PlacementRoute


@runtime_checkable
class Placer(Protocol):
    """Routing strategy interface."""

    async def place(
        self,
        content: str,
        start_path: str = "root",
    ) -> PlacementRoute:
        """Return recursive route trace for placement."""
        ...
