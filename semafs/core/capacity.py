"""Capacity model - Budget and Zone definitions."""

from dataclasses import dataclass
from enum import Enum


class Zone(Enum):
    """Capacity zones for maintenance decisions."""
    HEALTHY = "healthy"  # Below soft limit, no action needed
    PRESSURED = "pressured"  # Between soft and hard, LLM reorganization
    OVERFLOW = "overflow"  # Above hard limit, forced action


@dataclass(frozen=True)
class Budget:
    """
    Capacity budget for a category.

    Defines soft and hard limits for child nodes:
    - soft: Threshold for triggering LLM reorganization
    - hard: Maximum capacity before forced action
    """

    soft: int = 8
    hard: int = 12

    def __post_init__(self):
        """Validate budget invariants."""
        if self.soft <= 0:
            raise ValueError("Soft limit must be positive")
        if self.hard <= self.soft:
            raise ValueError("Hard limit must be greater than soft limit")

    def zone(self, count: int) -> Zone:
        """Determine capacity zone based on node count."""
        if count <= self.soft:
            return Zone.HEALTHY
        elif count <= self.hard:
            return Zone.PRESSURED
        else:
            return Zone.OVERFLOW

    def is_healthy(self, count: int) -> bool:
        """Check if count is in healthy zone."""
        return count <= self.soft

    def is_pressured(self, count: int) -> bool:
        """Check if count is in pressured zone."""
        return self.soft < count <= self.hard

    def is_overflow(self, count: int) -> bool:
        """Check if count is in overflow zone."""
        return count > self.hard
