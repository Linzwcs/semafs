from __future__ import annotations


class SemaFSError(Exception):
    """所有 SemaFS 异常的基类。"""


class InvalidPathError(SemaFSError):

    def __init__(self, path: str, reason: str = "") -> None:
        msg = f"非法路径: '{path}'"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)
        self.path = path


class NodeNotFoundError(SemaFSError):

    def __init__(self, path: str) -> None:
        super().__init__(f"节点不存在: '{path}'")
        self.path = path


class NodeTypeMismatchError(SemaFSError):
    """对节点执行了不符合其类型的操作。"""

    def __init__(self, path: str, expected: str, actual: str) -> None:
        super().__init__(f"节点类型错误 '{path}': 期望 {expected}，实际 {actual}")
        self.path = path


class VersionConflictError(SemaFSError):
    """乐观锁冲突：节点在读取后被其他操作修改。"""

    def __init__(self, node_id: str, expected: int, actual: int) -> None:
        super().__init__(
            f"乐观锁冲突 node_id={node_id}: 期望版本 {expected}，实际版本 {actual}")
        self.node_id = node_id
        self.expected = expected
        self.actual = actual


class PlanExecutionError(SemaFSError):
    """
    计划执行失败。

    携带已完成和未完成的操作信息，供上层决定是否回滚。
    因为事务由 UoW 控制，此异常本身不触发任何回滚。
    """

    def __init__(self, reason: str, op_index: int = -1) -> None:
        super().__init__(f"计划执行失败 (op #{op_index}): {reason}")
        self.op_index = op_index


class LLMAdapterError(SemaFSError):
    """LLM 调用失败（网络、超时、解析错误）。"""


class LockAcquisitionError(SemaFSError):
    """目录锁获取失败，说明当前路径正在被另一个 maintain 处理。"""

    def __init__(self, path: str) -> None:
        super().__init__(f"路径 '{path}' 的整理锁已被占用，跳过本轮")
        self.path = path
