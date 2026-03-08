from typing import Dict, Optional
import re
from .models.nodes import TreeNode
from .models.enums import NodeType


def ensure_root(nodes_by_id: Dict[str, TreeNode]) -> None:
    for n in nodes_by_id.values():
        if n.parent_path == "" and n.name == "root" and n.node_type == NodeType.CATEGORY:
            return
    root = TreeNode(
        parent_path="",
        name="root",
        node_type=NodeType.CATEGORY,
        content="",
        name_editable=False,
    )
    nodes_by_id[root.id] = root


def path_to_parent_and_segment(full_path: str) -> tuple[str, str]:
    """将完整路径拆为 (parent_path, segment_name)。root 为 ('', 'root')。"""
    if not full_path or full_path == "root":
        return ("", "root")
    parts = full_path.rsplit(".", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", parts[0])


def path_from_parent_and_segment(parent_path: str, segment_name: str) -> str:
    """从 (parent_path, segment_name) 推导 path。root 为 path='root'，非 root.root。"""
    if parent_path == "" and segment_name == "root":
        return "root"
    return f"{parent_path}.{segment_name}" if parent_path else segment_name


def is_direct_child(child_path: str, parent_path: str) -> bool:
    """判断 child_path 是否为 parent_path 的直接子节点。"""
    if not child_path.startswith(parent_path + "."):
        return False
    suffix = child_path[len(parent_path) + 1:]
    return "." not in suffix


#def slug_from_content(content: str, max_len: int = 32) -> str:
#    """从 content 生成路径安全片段。"""
#    slug = re.sub(r"[^a-z0-9]+", "_", content.lower())[:max_len].strip("_")
#    return slug or "item"


def slug_from_uuid(uuid: str, max_len: int = 4) -> str:
    slug = "item_" + uuid[:max_len]
    return slug


def slug_for_path_segment(s: str) -> str:
    """路径安全片段：空格→_，仅保留 [a-z0-9_]，否则用 slug_from_uuid。
    约束：英文、简洁、空格用 _ 代替。"""
    from uuid import uuid4
    raw = (s or "").strip().replace(" ", "_")
    clean = re.sub(r"[^a-z0-9_]", "", raw.lower()).strip("_")
    return clean if clean else slug_from_uuid(str(uuid4())[:8])


def sanitize_llm_name(s: str, max_len: int = 32) -> Optional[str]:
    """LLM 生成的 name 规范化：1) 仅英文 2) 有语义（由 prompt 约束）3) 简洁 4) 空格用 _ 代替。
    若含非 ASCII（如中文）或规范化后为空，返回 None，调用方应使用 fallback。"""
    if not s or not (raw := s.strip()):
        return None
    # 含非 ASCII 视为非英文，拒绝
    if not raw.isascii():
        return None
    normalized = raw.replace(" ", "_").lower()
    clean = re.sub(r"[^a-z0-9_]", "", normalized).strip("_")
    if not clean:
        return None
    return clean[:max_len] if max_len > 0 else clean


def sanitize_path(path: str) -> str:
    """对完整路径（如 root.work.personal）逐段 sanitize：空格→_，仅保留 [a-z0-9_]。"""
    if not path or not path.strip():
        return "root"
    parts = path.strip().split(".")
    sanitized = []
    for seg in parts:
        seg = seg.strip().replace(" ", "_")
        seg = re.sub(r"[^a-z0-9_]", "", seg.lower()).strip("_")
        if seg:
            sanitized.append(seg)
    return ".".join(sanitized) if sanitized else "root"


def derive_category_content_from_children(children: list,
                                          max_len: int = 500) -> str:
    """从子节点内容推导 category 摘要，仅包含子节点已有的信息。"""
    parts = []
    for c in children:
        if getattr(c, "content", None):
            parts.append(c.content[:80].strip())
    summary = " | ".join(parts[:8]) or ""
    if len(parts) > 8:
        summary += " ..."
    return summary[:max_len]
