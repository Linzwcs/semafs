"""Pulse - Event-driven signal propagation engine."""

from ..core.events import TreeEvent, Moved, Persisted, Placed
from ..ports.bus import Bus
from ..ports.propagation import Policy


class Pulse:
    """
    Event entry point.

    Responsibilities (v2.1.1):
    1. Receive TreeEvent
    2. Resolve target path (parent_path)
    3. signal = policy.seed(event, path)
    4. Call keeper.reconcile(path, signal, cause=event)

    No decay constants, no threshold logic — that's Policy's job.

    Event subscription policy:
    - Placed: New content placed -> parent needs reconcile
    - Persisted: Pending promoted -> parent may need rebalance
    - Moved: Content moved -> target category needs reconcile
    - Merged/Grouped: NOT subscribed - these are rebalance outputs,
      parent is already reconciling when these fire
    """

    def __init__(self, bus: Bus, policy: Policy, keeper):
        self._bus = bus
        self._policy = policy
        self._keeper = keeper

    def subscribe(self):
        """Subscribe to events that require reconcile."""
        # Only subscribe to events that indicate NEW work for a node
        # Merged/Grouped are outputs of rebalance, not inputs
        self._bus.subscribe(Moved, self._on_event)
        self._bus.subscribe(Persisted, self._on_event)
        self._bus.subscribe(Placed, self._on_event)

    async def _on_event(self, event: TreeEvent):
        """Handle domain event: seed Signal and hand off to Keeper."""
        target = self._resolve_target(event)
        if not target:
            return

        node_id, path = target
        signal = self._policy.seed(event, path)
        await self._keeper.reconcile(node_id, signal, cause=event)

    @staticmethod
    def _resolve_target(event: TreeEvent) -> tuple[str, str] | None:
        """Extract target (node_id, path_snapshot) from event."""
        if isinstance(event, (Persisted, Placed)):
            return event.parent_id, event.parent_path
        if isinstance(event, Moved):
            return event.target_category_id, event.target_category
        return None
