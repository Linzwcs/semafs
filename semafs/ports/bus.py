"""Bus - Event publishing protocol."""

from typing import Protocol, runtime_checkable, Callable, Awaitable

from ..core.events import TreeEvent


@runtime_checkable
class Bus(Protocol):
    """Event bus interface."""

    async def publish(self, event: TreeEvent) -> None:
        """Publish event to all subscribers."""
        ...

    def subscribe(self, event_type: type[TreeEvent],
                  handler: Callable[[TreeEvent], Awaitable[None]]) -> None:
        """Subscribe to event type with async handler."""
        ...


EventBus = Bus
