"""DefaultPolicy - Baseline linear-decay propagation policy."""

from dataclasses import dataclass, field

from ..core.events import TreeEvent, Grouped, Merged, Moved, Persisted, Placed
from ..ports.propagation import Policy, Signal, Context, Step

# Default event weights
_DEFAULT_WEIGHTS: dict[type[TreeEvent], float] = {
    Grouped: 1.0,
    Merged: 0.8,
    Moved: 0.6,
    Persisted: 0.5,
    Placed: 0.4,
}


@dataclass(frozen=True)
class DefaultPolicy:
    """
    Baseline propagation policy with linear decay.

    Rules:
    1. Initial signal from event_weights lookup (default 0.4).
    2. Linear decay: next = incoming * decay.
    3. Cutoff when next < threshold.
    4. Root node always stops propagation.
    """

    event_weights: dict[type[TreeEvent], float] = field(
        default_factory=lambda: dict(_DEFAULT_WEIGHTS)
    )
    decay: float = 0.7
    threshold: float = 0.3

    def __post_init__(self):
        if not (0 < self.decay <= 1):
            raise ValueError(f"decay must be in (0, 1], got {self.decay}")
        if not (0 <= self.threshold <= 1):
            raise ValueError(f"threshold must be in [0, 1], got {self.threshold}")
        for evt_type, weight in self.event_weights.items():
            if weight < 0:
                raise ValueError(f"weight for {evt_type.__name__} must be non-negative, got {weight}")

    def seed(self, event: TreeEvent, target_path: str) -> Signal:
        """Event -> initial Signal."""
        value = self.event_weights.get(type(event), 0.4)
        return Signal(
            value=value,
            origin=target_path,
            event_type=type(event).__name__,
        )

    def step(self, ctx: Context) -> Step:
        """Single-hop propagation decision."""
        incoming = ctx.signal
        next_value = incoming.value * self.decay
        next_signal = Signal(
            value=next_value,
            origin=incoming.origin,
            event_type=incoming.event_type,
            depth=incoming.depth + 1,
            payload=incoming.payload,
        )

        if ctx.to_path == "root":
            return Step(next_signal, False, "reached_root")

        if next_value < self.threshold:
            return Step(next_signal, False, "below_threshold")

        return Step(next_signal, True, "propagate")
