# Strategy API

Protocols for maintenance strategy implementation.

## Strategy Protocol

```python
from typing import Protocol, Optional
from semafs.core.ops import RebalancePlan, UpdateContext

class Strategy(Protocol):
    async def create_plan(
        self,
        context: UpdateContext,
        max_children: int
    ) -> Optional[RebalancePlan]:
        """
        Create a reorganization plan for the category.

        Args:
            context: Snapshot of category state
            max_children: Threshold for triggering reorganization

        Returns:
            RebalancePlan if reorganization needed, None to skip

        Notes:
            - May call LLM (can be slow)
            - Should handle failures gracefully
            - Can return None to skip maintenance
        """
        ...

    def create_fallback_plan(
        self,
        context: UpdateContext,
        max_children: int
    ) -> RebalancePlan:
        """
        Create a guaranteed fallback plan.

        Args:
            context: Snapshot of category state
            max_children: Threshold for grouping

        Returns:
            RebalancePlan (must never be None)

        Notes:
            - Must be synchronous (no async)
            - Must always succeed
            - Used when LLM fails
        """
        ...
```

## Built-in Strategies

### RuleOnlyStrategy

Deterministic rules, no LLM.

```python
from semafs.strategies.rule import RuleOnlyStrategy

strategy = RuleOnlyStrategy()
```

**Behavior**:
1. Persist all pending fragments
2. Auto-group if over capacity
3. Append content to parent summary

### HybridStrategy

LLM-powered with rule fallback.

```python
from semafs.strategies.hybrid import HybridStrategy

strategy = HybridStrategy(
    llm_adapter=adapter,      # Required
    max_nodes=8,              # Optional, default 8
    rule_fallback=None        # Optional, auto-creates RuleOnlyStrategy
)
```

**Decision Logic**:
- `force_llm` flag → Use LLM
- No pending + under threshold → Skip (None)
- Has pending + under threshold → Use rules
- Over threshold → Use LLM
- LLM failure → Use fallback

## LLM Adapter Protocol

```python
from typing import Protocol
from semafs.core.ops import RebalancePlan, UpdateContext

class BaseLLMAdapter(Protocol):
    async def call(
        self,
        context: UpdateContext,
        max_children: int
    ) -> RebalancePlan:
        """
        Call LLM to create reorganization plan.

        Args:
            context: Category state snapshot
            max_children: Target max children

        Returns:
            RebalancePlan with operations

        Raises:
            LLMAdapterError: On API failure
        """
        ...
```

## Built-in Adapters

### OpenAIAdapter

```python
from openai import AsyncOpenAI
from semafs.infra.llm.openai import OpenAIAdapter

client = AsyncOpenAI()
adapter = OpenAIAdapter(
    client=client,
    model="gpt-4o-mini",
    temperature=0.7
)
```

### AnthropicAdapter

```python
from anthropic import AsyncAnthropic
from semafs.infra.llm.anthropic import AnthropicAdapter

client = AsyncAnthropic()
adapter = AnthropicAdapter(
    client=client,
    model="claude-3-haiku-20240307"
)
```

## Custom Strategy

```python
from semafs.ports.strategy import Strategy
from semafs.core.ops import RebalancePlan, PersistOp, MergeOp

class MyStrategy(Strategy):
    def __init__(self, merge_threshold: int = 3):
        self.merge_threshold = merge_threshold

    async def create_plan(
        self,
        context: UpdateContext,
        max_children: int
    ) -> Optional[RebalancePlan]:
        if not context.pending_nodes:
            return None

        ops = []

        # Group similar content by keyword
        keyword_groups = self._group_by_keywords(context.pending_nodes)

        for keyword, nodes in keyword_groups.items():
            if len(nodes) >= self.merge_threshold:
                ops.append(MergeOp(
                    ids=frozenset(n.id for n in nodes),
                    content=self._merge_content(nodes),
                    reasoning=f"All contain '{keyword}'"
                ))
            else:
                for node in nodes:
                    ops.append(PersistOp(id=node.id, reasoning="No merge candidates"))

        return RebalancePlan(
            ops=tuple(ops),
            updated_content=self._summarize(context),
            is_llm_plan=False
        )

    def create_fallback_plan(
        self,
        context: UpdateContext,
        max_children: int
    ) -> RebalancePlan:
        # Simple persist-all fallback
        ops = tuple(
            PersistOp(id=n.id, reasoning="Fallback")
            for n in context.pending_nodes
        )
        return RebalancePlan(
            ops=ops,
            updated_content=context.parent.content,
            is_llm_plan=False
        )

    def _group_by_keywords(self, nodes):
        # Implementation...
        pass

    def _merge_content(self, nodes):
        # Implementation...
        pass

    def _summarize(self, context):
        # Implementation...
        pass
```

## Custom LLM Adapter

```python
from semafs.ports.llm import BaseLLMAdapter
from semafs.core.ops import RebalancePlan, UpdateContext
from semafs.core.exceptions import LLMAdapterError

class MyLLMAdapter(BaseLLMAdapter):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def call(
        self,
        context: UpdateContext,
        max_children: int
    ) -> RebalancePlan:
        # Build prompt
        prompt = self._build_prompt(context, max_children)

        try:
            # Call your LLM
            response = await self._call_api(prompt)

            # Parse response
            return self._parse_response(response)

        except Exception as e:
            raise LLMAdapterError(f"API call failed: {e}")

    def _build_prompt(self, context, max_children):
        # Format context for LLM
        return f"""
        Category: {context.parent.path}

        Active nodes:
        {self._format_nodes(context.active_nodes)}

        Pending fragments:
        {self._format_nodes(context.pending_nodes)}

        Instructions: Organize these nodes...
        """

    async def _call_api(self, prompt):
        # Your API implementation
        pass

    def _parse_response(self, response) -> RebalancePlan:
        # Parse JSON into RebalancePlan
        pass
```

## Strategy Testing

```python
import pytest
from unittest.mock import AsyncMock
from semafs.core.ops import RebalancePlan, PersistOp, UpdateContext
from semafs.core.node import TreeNode

@pytest.fixture
def mock_context():
    parent = TreeNode.new_category("root", "test", "Test category")
    pending = (
        TreeNode.new_fragment("root.test", "Fragment 1"),
        TreeNode.new_fragment("root.test", "Fragment 2"),
    )
    return UpdateContext(
        parent=parent,
        active_nodes=(),
        pending_nodes=pending,
        sibling_categories=(),
        ancestor_categories=()
    )

@pytest.mark.asyncio
async def test_custom_strategy(mock_context):
    strategy = MyStrategy(merge_threshold=2)

    plan = await strategy.create_plan(mock_context, max_children=10)

    assert plan is not None
    assert len(plan.ops) > 0

def test_fallback_always_works(mock_context):
    strategy = MyStrategy()

    plan = strategy.create_fallback_plan(mock_context, max_children=10)

    assert plan is not None
    assert not plan.is_llm_plan
```

## See Also

- [Strategies Guide](/guide/strategies) - Configuration details
- [LLM Integration](/guide/llm-integration) - Provider setup
- [Operations](/api/operations) - Operation types
