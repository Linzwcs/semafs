from .executor import OpExecutor, apply_add_node
from .memory import MemoryNodeStore, MemoryTreeRepository
from .protocol import NodeStore

__all__ = [
    "MemoryNodeStore",
    "MemoryTreeRepository",
    "NodeStore",
    "OpExecutor",
    "SQLiteNodeStore",
    "SQLiteTreeRepository",
    "apply_add_node",
]


def __getattr__(name: str):
    if name in ("SQLiteNodeStore", "SQLiteTreeRepository"):
        from .sqlite import SQLiteNodeStore, SQLiteTreeRepository
        return SQLiteNodeStore if name == "SQLiteNodeStore" else SQLiteTreeRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
