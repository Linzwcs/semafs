from typing import Callable, Awaitable

from ..core.events import TreeEvent


class InMemoryBus:
    """Simple dict-based event bus for in-process pub/sub."""

    def __init__(self):
        self._handlers: dict[type, list[Callable[[TreeEvent],
                                                 Awaitable[None]]]] = {}

    async def publish(self, event: TreeEvent) -> None:
        """Publish event to all subscribers of its type."""
        handlers = tuple(self._handlers.get(type(event), ()))
        for handler in handlers:
            await handler(event)

    def subscribe(
        self,
        event_type: type[TreeEvent],
        handler: Callable[[TreeEvent], Awaitable[None]],
    ) -> None:
        """Register handler for event type."""
        self._handlers.setdefault(event_type, []).append(handler)
