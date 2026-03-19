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


@dataclass(frozen=True)
class TerminalPolicy:
    """
    Terminal category decision logic.

    Encapsulates all terminal-related decisions, extracted from Keeper
    to enable independent evolution and testing.
    """

    config: TerminalConfig

    def is_terminal(self, depth: int) -> bool:
        """Check if depth qualifies as terminal category."""
        return depth >= self.config.terminal_depth

    def allow_group(self, depth: int) -> bool:
        """Check if grouping is allowed at this depth."""
        if self.config.group_mode == TerminalGroupMode.DISABLED:
            return False
        return depth >= self.config.terminal_depth

    def should_rollup(self, active_leaf_count: int) -> bool:
        """Check if rollup should be triggered."""
        return active_leaf_count >= self.config.rollup_trigger_count

    def can_rollup_batch(self, batch_size: int) -> bool:
        """Check if batch size meets minimum for rollup."""
        return batch_size >= self.config.min_rollup_batch
