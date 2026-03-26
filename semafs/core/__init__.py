"""Domain layer - Pure business logic with zero infrastructure dependencies."""

from .node import Node, NodePath, NodeType, NodeStage
from .capacity import Budget, Zone
from .events import Merged, Grouped, Moved, Persisted, Placed
from .plan.ops import Plan, MergeOp, GroupOp, MoveOp, RenameOp
from .plan.raw import RawPlan, RawMerge, RawGroup, RawMove, RawRename
from .snapshot import Snapshot
from .placement import (
    PlacementAction,
    PlacementDecision,
    PlacementStep,
    PlacementRoute,
)
from .exceptions import SemaFSError, NodeNotFoundError, InvalidPathError
from .rules import CATEGORY_UPDATED_NAME_RE, GENERIC_CATEGORY_NAMES
from .terminal import TerminalConfig, TerminalGroupMode
from .summary import (
    build_category_meta,
    normalize_category_meta,
    render_category_summary,
)
from .plan.pipeline import PlanIssue, PassTrace, PlanArtifact, CompileResult
from .timestamps import utc_now_rfc3339, normalize_rfc3339

__all__ = [
    "Node",
    "NodePath",
    "NodeType",
    "NodeStage",
    "Budget",
    "Zone",
    "Merged",
    "Grouped",
    "Moved",
    "Persisted",
    "Placed",
    "Plan",
    "MergeOp",
    "GroupOp",
    "MoveOp",
    "RenameOp",
    "RawPlan",
    "RawMerge",
    "RawGroup",
    "RawMove",
    "RawRename",
    "Snapshot",
    "PlacementAction",
    "PlacementDecision",
    "PlacementStep",
    "PlacementRoute",
    "CATEGORY_UPDATED_NAME_RE",
    "GENERIC_CATEGORY_NAMES",
    "TerminalConfig",
    "TerminalGroupMode",
    "build_category_meta",
    "normalize_category_meta",
    "render_category_summary",
    "PlanIssue",
    "PassTrace",
    "PlanArtifact",
    "CompileResult",
    "utc_now_rfc3339",
    "normalize_rfc3339",
    "SemaFSError",
    "NodeNotFoundError",
    "InvalidPathError",
]
