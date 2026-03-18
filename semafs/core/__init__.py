"""Domain layer - Pure business logic with zero infrastructure dependencies."""

from .node import Node, NodePath, NodeType, NodeStage
from .capacity import Budget, Zone
from .events import Merged, Grouped, Moved, Persisted, Placed
from .ops import Plan, MergeOp, GroupOp, MoveOp, RenameOp
from .raw import RawPlan, RawMerge, RawGroup, RawMove, RawRename
from .snapshot import Snapshot
from .exceptions import SemaFSError, NodeNotFoundError, InvalidPathError
from .rules import CATEGORY_UPDATED_NAME_RE, GENERIC_CATEGORY_NAMES
from .retrieval import RetrievalWeights, score_category_text
from .terminal import TerminalConfig, TerminalGroupMode
from .summary import (
    build_category_meta,
    normalize_category_meta,
    render_category_summary,
)

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
    "CATEGORY_UPDATED_NAME_RE",
    "GENERIC_CATEGORY_NAMES",
    "RetrievalWeights",
    "score_category_text",
    "TerminalConfig",
    "TerminalGroupMode",
    "build_category_meta",
    "normalize_category_meta",
    "render_category_summary",
    "SemaFSError",
    "NodeNotFoundError",
    "InvalidPathError",
]
