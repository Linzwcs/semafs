"""Propagation Policy - Unified signal propagation protocol."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core.events import TreeEvent
from ..core.snapshot import Snapshot


@dataclass(frozen=True)
class Signal:
    """Immutable propagation signal carried through the tree."""

    value: float
    origin: str              # Path that originally triggered propagation
    event_type: str          # Name of the triggering event class
    depth: int = 0           # Current propagation depth
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Context:
    """Immutable context for a single propagation hop."""

    event: TreeEvent | None
    from_path: str
    to_path: str
    signal: Signal
    snapshot: Snapshot | None = None


@dataclass(frozen=True)
class Step:
    """Result of a single propagation decision."""

    signal: Signal
    should_continue: bool
    reason: str


class Policy(Protocol):
    """Unified propagation strategy interface."""

    def seed(self, event: TreeEvent, target_path: str) -> Signal:
        """Event -> initial Signal."""
        ...

    def step(self, ctx: Context) -> Step:
        """Single-hop propagation decision (decay + cutoff + explanation)."""
        ...
