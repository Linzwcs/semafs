"""Planner port for raw plan drafting with retry feedback."""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..core.plan.raw import RawPlan
from ..core.snapshot import Snapshot


@dataclass(frozen=True)
class PlanDraftRequest:
    """Input for planner draft call."""

    snapshot: Snapshot
    attempt: int = 1
    retry_feedback: dict[str, Any] = field(default_factory=dict)
    frozen_ops: tuple[dict[str, Any], ...] = ()


@runtime_checkable
class Planner(Protocol):
    """Planner interface to generate candidate raw plans."""

    async def draft(self, request: PlanDraftRequest) -> RawPlan | None:
        """Draft one raw plan for snapshot."""
        ...
