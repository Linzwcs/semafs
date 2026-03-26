"""Plan pipeline core models for compiler-style orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .ops import Plan
from .raw import RawPlan
from ..snapshot import Snapshot

IssueSeverity = Literal["warn", "drop", "retry", "fatal"]


@dataclass(frozen=True)
class PlanIssue:
    """Structured issue emitted by compiler passes."""

    code: str
    stage: str
    severity: IssueSeverity
    message: str
    op_index: int | None = None
    hint: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PassTrace:
    """One pass execution trace row."""

    pass_name: str
    status: str
    issue_count: int
    elapsed_ms: int


@dataclass
class PlanArtifact:
    """Mutable artifact flowing through compiler pipeline."""

    snapshot: Snapshot
    raw_plan: RawPlan | None = None
    plan: Plan | None = None
    attempt: int = 1
    frozen_ops: tuple[int, ...] = ()
    trace: list[PassTrace] = field(default_factory=list)


@dataclass(frozen=True)
class CompileResult:
    """Compiler output for one reconcile round."""

    plan: Plan
    issues: tuple[PlanIssue, ...] = ()
    attempts: int = 1
    trace: tuple[PassTrace, ...] = ()
