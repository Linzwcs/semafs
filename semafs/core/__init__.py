"""
Core domain model for SemaFS.

This package contains the fundamental building blocks of the SemaFS
domain model, following Domain-Driven Design principles.

Modules:
    - node: TreeNode entity and NodePath value object
    - ops: Operation commands (MergeOp, GroupOp, MoveOp, PersistOp)
    - enums: Type enumerations (NodeType, NodeStatus, OpType)
    - exceptions: Structured exception hierarchy
    - views: Read-only view objects for API responses

Key Classes:
    - TreeNode: Mutable entity representing a knowledge tree node
    - NodePath: Immutable value object for hierarchical paths
    - RebalancePlan: Collection of operations for tree reorganization
    - UpdateContext: Read-only snapshot for strategy decisions

Design Principles:
    1. Rich domain model with behavior methods
    2. Immutable operations (frozen dataclasses)
    3. Clear separation between entities and value objects
    4. Views are data containers, not TreeNodes
"""
from .node import TreeNode, NodePath
from .ops import (
    MergeOp,
    GroupOp,
    MoveOp,
    PersistOp,
    RebalancePlan,
    UpdateContext,
    AnyOp,
)
from .enums import NodeType, NodeStatus, OpType
from .exceptions import (
    SemaFSError,
    InvalidPathError,
    NodeNotFoundError,
    NodeTypeMismatchError,
    VersionConflictError,
    PlanExecutionError,
    LLMAdapterError,
    LockAcquisitionError,
)
from .views import NodeView, TreeView, RelatedNodes, StatsView

__all__ = [
    # Node entities
    "TreeNode",
    "NodePath",
    # Operations
    "MergeOp",
    "GroupOp",
    "MoveOp",
    "PersistOp",
    "RebalancePlan",
    "UpdateContext",
    "AnyOp",
    # Enums
    "NodeType",
    "NodeStatus",
    "OpType",
    # Exceptions
    "SemaFSError",
    "InvalidPathError",
    "NodeNotFoundError",
    "NodeTypeMismatchError",
    "VersionConflictError",
    "PlanExecutionError",
    "LLMAdapterError",
    "LockAcquisitionError",
    # Views
    "NodeView",
    "TreeView",
    "RelatedNodes",
    "StatsView",
]
