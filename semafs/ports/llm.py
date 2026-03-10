"""
LLM adapter base class and prompt building utilities.

This module provides:
- BaseLLMAdapter: Abstract base class for LLM API integrations
- Prompt construction utilities for the tree reorganization task
- Tool schema definition for LLM function calling

The LLM adapter abstracts away the differences between LLM providers
(OpenAI, Anthropic, etc.) while providing a consistent interface for
the Strategy layer.

Prompt Structure:
    - System prompt: Role definition, operation guidelines, formatting rules
    - User prompt: Current directory state, available operations, constraints

Implementations:
- OpenAIAdapter: Uses OpenAI's chat completions with function calling
- AnthropicAdapter: Uses Anthropic's messages API with tool use

Usage:
    adapter = OpenAIAdapter(client, model="gpt-4o")
    result = await adapter.call(context, max_children=10)
    # result contains parsed ops, reasoning, updated_content, etc.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Tuple
from ..core.ops import UpdateContext
from ..core.exceptions import LLMAdapterError
from ..core.enums import NodeType

# Tool schema for LLM function calling (Anthropic format)
# OpenAI adapter converts this to OpenAI's function schema format
_TREE_OPS_SCHEMA = {
    "name": "tree_ops",
    "description": "Decide how to reorganize memory fragments in a directory. "
    "Maintain directory cleanliness through merge/group/move operations.",
    "input_schema": {
        "type":
        "object",
        "required":
        ["ops", "overall_reasoning", "updated_content", "should_dirty_parent"],
        "properties": {
            "ops": {
                "type": "array",
                "description":
                "List of operations. Return empty array [] if structure is healthy.",
                "items": {
                    "type": "object",
                    "required": ["op_type", "ids", "reasoning", "name"],
                    "properties": {
                        "op_type": {
                            "type": "string",
                            "enum": ["MERGE", "GROUP", "MOVE"],
                            "description": "Type of operation to perform"
                        },
                        "ids": {
                            "type":
                            "array",
                            "items": {
                                "type": "string"
                            },
                            "description":
                            "MERGE: 2+ LEAF IDs; GROUP: 2+ LEAF IDs; MOVE: exactly 1 LEAF ID. "
                            "IDs come from [id: xxx] in the node list."
                        },
                        "reasoning": {
                            "type": "string",
                            "description":
                            "Brief explanation for this operation"
                        },
                        "name": {
                            "type":
                            "string",
                            "description":
                            "System name for the resulting node. Must be lowercase English, "
                            "words separated by underscores (e.g., java_backend_specs). "
                            "No Chinese or special characters allowed!"
                        },
                        "content": {
                            "type":
                            "string",
                            "description":
                            "Only for MERGE and GROUP. MERGE: lossless synthesis of original "
                            "content (preserve all specifics); GROUP: topic summary."
                        },
                        "path_to_move": {
                            "type":
                            "string",
                            "description":
                            "Only for MOVE. Target category's full path "
                            "(must copy exactly from available_move_targets)."
                        },
                    },
                },
            },
            "overall_reasoning": {
                "type": "string",
                "description": "Describe the overall reorganization strategy"
            },
            "updated_content": {
                "type":
                "string",
                "description":
                "Updated summary for this directory after executing all ops. "
                "Will be read by parent directory."
            },
            "updated_name": {
                "type":
                "string",
                "description":
                "New display name for this directory (optional). "
                "Only update if current name no longer fits the content."
            },
            "should_dirty_parent": {
                "type":
                "boolean",
                "description":
                "Set to true if this reorganization produced major new insights "
                "that should propagate to parent directory."
            }
        },
    },
}


def _format_node_list(nodes: list) -> str:
    """
    Format a list of nodes for inclusion in the LLM prompt.

    Each node is formatted with its short ID, type, name, and content preview.

    Args:
        nodes: List of TreeNode objects.

    Returns:
        Formatted string with one node per line, or "(empty)" if no nodes.
    """
    if not nodes:
        return "  (empty)"
    lines = []
    for n in nodes:
        lines.append(f"  - [id: {n.id[:8]}] node_type: {n.node_type.value} | "
                     f"name: {n.name}(not id) | content: {n.content}...")
    return "\n".join(
        lines
    ) + "\n\n" + "Note: the id is used to identify the node, do not use the name to identify the node."


def _build_prompt(
    context: UpdateContext,
    max_children: int,
) -> Tuple[str, str]:
    """
    Build system and user prompts for the LLM reorganization task.

    Constructs a rich context including:
    - Current directory state and capacity
    - Active and pending nodes
    - Available move targets (existing subcategories)
    - Sibling categories (for naming conflict avoidance)
    - Ancestor hierarchy (for semantic context)

    Args:
        context: The UpdateContext snapshot.
        max_children: Maximum allowed children in a category.

    Returns:
        Tuple of (system_prompt, user_prompt) strings.
    """
    all_nodes = list(context.active_nodes) + list(context.pending_nodes)
    total_count = len(all_nodes)

    # Find available move targets (existing subcategories)
    sub_cats = [
        n for n in context.active_nodes if n.node_type == NodeType.CATEGORY
    ]
    available_paths = "\n".join([f"  * {c.path}"
                                 for c in sub_cats]) or "  (no subcategories)"

    # Build sibling info for naming conflict avoidance
    sibling_info = ""
    if context.sibling_categories:
        sibling_names = [f"'{s.name}'" for s in context.sibling_categories]
        sibling_info = f"""
<sibling_categories>
Sibling category names at the same level (avoid conflicts when updating updated_name):
  {', '.join(sibling_names)}
</sibling_categories>"""

    # Build ancestor hierarchy for semantic context
    ancestor_info = ""
    if context.ancestor_categories:
        ancestor_chain = []
        for i, anc in enumerate(reversed(context.ancestor_categories)):
            indent = "  " * i
            summary = anc.content[:50] + "..." if len(
                anc.content) > 50 else anc.content
            ancestor_chain.append(f"{indent}└─ {anc.path}: {summary}")
        ancestor_info = f"""
<hierarchical_context>
Position in the knowledge tree (from root to current):
{''.join(ancestor_chain)}
  {"  " * len(context.ancestor_categories)}└─ {context.parent.path} (current directory)

Understanding this hierarchy helps you:
1. Determine semantic boundaries (avoid creating categories that duplicate parent)
2. Decide whether should_dirty_parent=true (propagate major changes upward)
3. Choose appropriate abstraction level for new GROUP categories
</hierarchical_context>"""

    # System prompt with operation guidelines
    system_prompt = f"""You are a knowledge graph scheduling engine running inside SemaFS (Semantic File System).
Your core responsibility: Semantically cluster and reduce information while keeping node count under {max_children}.

【Operation Decision Guide】
Choose operations based on these scenarios:
1. 🟩 MERGE (combine leaves): When nodes describe DIFFERENT ASPECTS OF THE SAME THING
   (e.g., "likes Americano" and "drinks coffee without sugar").
   - ⚠️ CRITICAL: MERGE content must be a SUPERSET of all original details.
     Never lose specific values, dates, or proper nouns! You may concatenate with sections.
2. 🗂️ GROUP (create category): When nodes belong to the SAME BROAD TOPIC but are independent entities
   (e.g., "frontend framework specs" and "backend DB specs").
   - Move them into a newly created CATEGORY. The content is a concise topic summary.
   - When creating GROUP, check hierarchical context to ensure appropriate abstraction level.
3. ➡️ MOVE (to existing): When a node perfectly fits an available subcategory below.
   - ⚠️ CRITICAL: path_to_move must be copied EXACTLY from the available list!

【Naming and Formatting Rules】
- `name` field: Must be a valid path segment. Prefer single words; use underscores for multiple words.
  Only lowercase letters, numbers, underscores (a-z, 0-9, _). Max 32 chars.
  Example: coffee_prefs, morning_routine. NO Chinese, uppercase, or spaces.
- `updated_name` field: Ensure no conflict with sibling category names (see sibling_categories).

【Directory State Refresh】
- `updated_content`: Rewrite the directory's complete summary based on remaining + new nodes.
- `should_dirty_parent`: Set true if this reorganization extracted new major themes or changed core nature."""

    # Build status warning based on capacity
    status_warning = ""
    if total_count > max_children:
        status_warning = (
            f"🔴 CRITICAL: Node count ({total_count}) exceeds limit ({max_children}). "
            f"You MUST perform MERGE or GROUP to reduce parallel nodes!")
    elif context.pending_nodes:
        status_warning = (
            f"🟡 NOTE: New fragments arrived. Consider proactive organization "
            f"if approaching capacity.")

    # User prompt with full context
    user_content = f"""<directory_status>
- current_path: "{context.parent.path}"
- current_name: "{context.parent.display_name or context.parent.name}"
- capacity: {total_count}/{max_children}
- alert: {status_warning}
</directory_status>

<current_directory_summary>
{context.parent.content or '(empty)'}
</current_directory_summary>
{sibling_info}
{ancestor_info}
<available_move_targets>
{available_paths}
</available_move_targets>

<existing_active_nodes>
{_format_node_list(list(context.active_nodes))}
</existing_active_nodes>

<new_pending_fragments>
{_format_node_list(list(context.pending_nodes))}
</new_pending_fragments>

Please call `tree_ops` with your reorganization plan. If structure is healthy and under capacity, return empty ops array but always update updated_content."""

    return (system_prompt, user_content)


class BaseLLMAdapter(ABC):
    """
    Abstract base class for LLM API adapters.

    BaseLLMAdapter handles prompt construction and error wrapping,
    while subclasses implement the actual API calls. This enables
    consistent behavior across different LLM providers.

    Subclass Requirements:
        - Implement _call_api() to make the actual LLM API call
        - Parse the response and return the tree_ops tool input dict
        - Handle provider-specific response formats

    Error Handling:
        All exceptions from _call_api are wrapped in LLMAdapterError
        by the call() method for consistent error handling in Strategy.
    """

    @abstractmethod
    async def _call_api(self, system: str, user: str) -> Dict:
        """
        Make the actual LLM API call.

        Subclasses implement this to call their specific LLM provider.
        The response should be the parsed tree_ops tool input dict.

        Args:
            system: The system prompt string.
            user: The user prompt string.

        Returns:
            Dict containing ops, overall_reasoning, updated_content, etc.

        Raises:
            LLMAdapterError: If the API call fails or response is invalid.
        """
        ...

    async def call(self, context: UpdateContext, max_children: int) -> Dict:
        """
        Generate a reorganization plan using the LLM.

        Builds prompts from context and calls the LLM API. All exceptions
        are wrapped in LLMAdapterError for consistent error handling.

        Args:
            context: The UpdateContext snapshot for the category.
            max_children: Maximum allowed children in a category.

        Returns:
            Dict containing the LLM's reorganization decision:
            - ops: List of operation dicts
            - overall_reasoning: Explanation string
            - updated_content: New category summary
            - updated_name: Optional new display name
            - should_dirty_parent: Boolean flag

        Raises:
            LLMAdapterError: If the LLM call fails for any reason.
        """
        system, user = _build_prompt(context, max_children)
        try:
            return await self._call_api(system, user)
        except Exception as e:
            raise LLMAdapterError(f"LLM API call failed: {e}") from e
