from __future__ import annotations


class SemaFSError(Exception):
    """SemaFS 异常基类。"""


class NodeNotFoundError(SemaFSError):

    def __init__(self, path: str) -> None:
        super().__init__(f"节点不存在: '{path}'")
        self.path = path


class InvalidPathError(SemaFSError):

    def __init__(self, path: str) -> None:
        super().__init__(f"非法 ltree 路径: '{path}'")
        self.path = path


class VersionConflictError(SemaFSError):

    def __init__(self, node_id: str, expected: int, actual: int) -> None:
        super().__init__(f"乐观锁冲突 node_id={node_id}: 期望 {expected}，实际 {actual}")
        self.node_id = node_id
        self.expected = expected
        self.actual = actual


class NodeUpdateLockError(SemaFSError):

    def __init__(self, path: str) -> None:
        super().__init__(f"路径 '{path}' 的 Rebalance 正在执行中")
        self.path = path


class LLMDecisionError(SemaFSError):
    """LLM 决策失败（超时、解析错误等）。"""
