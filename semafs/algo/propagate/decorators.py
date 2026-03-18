"""Policy decorators - Composable propagation policy extensions."""

from dataclasses import dataclass

from ...core.events import TreeEvent
from ...ports.propagation import Policy, Signal, Context, Step


@dataclass
class ZoneAwarePolicy:
    """
    Decorator that boosts signal in overflow zones.

    Wraps a base Policy and amplifies propagation when the
    snapshot indicates an overflow zone, ensuring structural
    pressure propagates further up the tree.
    """

    _base: Policy

    def seed(self, event: TreeEvent, target_path: str) -> Signal:
        return self._base.seed(event, target_path)

    def step(self, ctx: Context) -> Step:
        base = self._base.step(ctx)
        if not base.should_continue:
            return base
        if ctx.snapshot and ctx.snapshot.zone.value == "overflow":
            boosted = min(base.signal.value * 1.1, 1.0)
            new_signal = Signal(
                value=boosted,
                origin=base.signal.origin,
                event_type=base.signal.event_type,
                depth=base.signal.depth,
                payload=base.signal.payload,
            )
            return Step(new_signal, True, "zone_overflow_boost")
        return base


@dataclass
class DepthAwarePolicy:
    """
    Decorator that raises threshold with depth.

    Deeper nodes need stronger signals to propagate further,
    preventing shallow structural changes from rippling too far.
    """

    _base: Policy
    depth_penalty: float = 0.05

    def seed(self, event: TreeEvent, target_path: str) -> Signal:
        return self._base.seed(event, target_path)

    def step(self, ctx: Context) -> Step:
        base = self._base.step(ctx)
        if not base.should_continue:
            return base
        effective_threshold = 0.3 + ctx.signal.depth * self.depth_penalty
        if base.signal.value < effective_threshold:
            return Step(base.signal, False, "depth_cutoff")
        return base

