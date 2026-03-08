from __future__ import annotations
from enum import Enum


class NodeType(str, Enum):
    CATEGORY = "CATEGORY"
    LEAF = "LEAF"


class NodeStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    PENDING_REVIEW = "PENDING_REVIEW"
    PROCESSING = "PROCESSING"


class OpType(str, Enum):
    MOVE = "MOVE"
    MERGE = "MERGE"
    SPLIT = "SPLIT"
    PERSIST = "PERSIST"
