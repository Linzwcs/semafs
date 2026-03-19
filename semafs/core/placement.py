"""Placement decision models for recursive routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PlacementAction(Enum):
    """Single-step action returned by placement LLM."""

    STAY = "stay"
    DESCEND = "descend"


@dataclass(frozen=True)
class PlacementDecision:
    """One-level placement decision."""

    action: PlacementAction
    target_child: str | None = None
    reasoning: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class PlacementStep:
    """Recorded recursive step for observability."""

    depth: int
    current_path: str
    decision: PlacementDecision


@dataclass(frozen=True)
class PlacementRoute:
    """Final routing result with full decision trail."""

    target_path: str
    steps: tuple[PlacementStep, ...]
    reasoning: str = ""
