from __future__ import annotations
from typing import Optional
from ...models.enums import NodeStatus
from ...models.ops import NodeUpdateContext, NodeUpdateOp, PersistenceOp
from ...interface import NodeUpdateStrategy


class RuleBasedStrategy(NodeUpdateStrategy):
    """
    纯规则策略：归档 inbox 叶子为持久化节点。
    - 有 inbox：为每个 PENDING_REVIEW 叶子创建 PersistenceOp，归档并创建新 ACTIVE 节点。
    - 无 inbox：返回 None（由调用方处理）。
    不考虑 MOVE、SPLIT、叶子数上限等其他操作。
    """

    def __init__(self, max_leaf_nodes: int = 3, **kwargs):
        self.max_leaf_nodes = max_leaf_nodes

    async def create_update_op(
            self, context: NodeUpdateContext) -> Optional[NodeUpdateOp]:

        inbox = context.inbox
        if not inbox:
            return None

        parent = context.parent
        content = parent.content or ""
        inbox_content = []
        ops = []
        for node in inbox:

            assert node.status == NodeStatus.PENDING_REVIEW
            payload = node.payload
            payload.pop("_virtual_node", None)
            ops.append(
                PersistenceOp(
                    ids=(node.id, ),
                    reasoning="归档 inbox 叶子",
                    content=node.content or "",
                    name="_frag_" + node.id[:8],
                    payload=payload,
                ))
            inbox_content.append(node.content or "")

        updated_content = (content + "\n\n[inbox]\n\n" +
                           "\n\n".join(inbox_content))

        return NodeUpdateOp(
            ops=ops,
            updated_content=updated_content,
            is_macro_change=False,
            overall_reasoning="规则：归档 inbox 叶子",
        )

    def create_fallback_op(self, context: NodeUpdateContext) -> NodeUpdateOp:
        return self.create_update_op(context)
