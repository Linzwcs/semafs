"""Clock port for deterministic timestamp generation."""

from typing import Protocol, runtime_checkable
from datetime import datetime


@runtime_checkable
class Clock(Protocol):
    """Time source abstraction."""

    def now_utc(self) -> datetime:
        """Return current UTC datetime."""
        ...
