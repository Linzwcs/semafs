"""Terminal category policy configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TerminalGroupMode(Enum):
    """Terminal-category grouping policy."""

    DISABLED = "disabled"
    HIGH_GAIN = "high_gain"


@dataclass(frozen=True)
class TerminalConfig:
    """
    Terminal policy configuration.

    Parameters are intentionally simple and globally configurable.
    """

    terminal_depth: int = 5
    rollup_window: str = "weekly"
    active_raw_limit: int = 30
    group_mode: TerminalGroupMode = TerminalGroupMode.DISABLED

    # Rollup lifecycle parameters
    rollup_trigger_count: int = 20   # Active leaves exceeding this triggers rollup
    min_rollup_batch: int = 10       # Minimum batch size for rollup
    cold_retention_windows: int = 4  # Number of windows to retain COLD nodes

    def __post_init__(self) -> None:
        if self.terminal_depth <= 0:
            raise ValueError("terminal_depth must be positive")
        if self.active_raw_limit <= 0:
            raise ValueError("active_raw_limit must be positive")
        if self.rollup_window not in {"weekly", "monthly", "quarterly"}:
            raise ValueError(
                "rollup_window must be one of: weekly/monthly/quarterly"
            )
        if self.rollup_trigger_count <= 0:
            raise ValueError("rollup_trigger_count must be positive")
        if self.min_rollup_batch <= 0:
            raise ValueError("min_rollup_batch must be positive")
        if self.cold_retention_windows < 0:
            raise ValueError("cold_retention_windows must be non-negative")
