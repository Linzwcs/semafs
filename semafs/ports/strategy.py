"""
Strategy protocol: Reorganization decision interface.

This module defines the Strategy interface that determines how to reorganize
a category's contents. Strategies analyze the current state and produce
a RebalancePlan that the Executor will apply.

Strategy Implementations:
- RuleOnlyStrategy: Never calls LLM, uses simple rules (for testing/mock)
- HybridStrategy: Calls LLM when needed, falls back to rules on failure

The Strategy pattern allows swapping reorganization algorithms without
changing the maintenance flow in SemaFS.

Usage:
    strategy = HybridStrategy(llm_adapter, max_children=10)
    plan = await strategy.create_plan(context, max_children=10)
    if plan:
        await executor.execute(plan, context, uow)
"""
from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable
from ..core.ops import RebalancePlan, UpdateContext


@runtime_checkable
class Strategy(Protocol):
    """
    Protocol for knowledge tree reorganization strategies.

    A Strategy receives the current state of a category (via UpdateContext)
    and decides how to reorganize its contents. The decision can involve:
    - Merging similar leaves
    - Grouping related leaves into new categories
    - Moving leaves to existing categories
    - Doing nothing (structure is already optimal)

    Implementation Guidelines:
        - create_plan is async to support LLM API calls
        - Returning None means "no reorganization needed"
        - create_fallback_plan MUST be synchronous for reliability
        - create_fallback_plan MUST NOT return None
    """

    async def create_plan(self, context: UpdateContext,
                          max_children: int) -> Optional[RebalancePlan]:
        """
        Generate a reorganization plan based on current state.

        This is the main decision-making method. Implementations can:
        1. Use pure rules (simple, fast, deterministic)
        2. Call an LLM for semantic understanding
        3. Use hybrid approach (rules for simple cases, LLM for complex)

        Args:
            context: Read-only snapshot of the category's current state.
            max_children: Maximum allowed children before reorganization.

        Returns:
            RebalancePlan with operations to execute, or None if no
            reorganization is needed.

        Raises:
            LLMAdapterError: If LLM call fails (hybrid strategies should
                fall back to create_fallback_plan internally).
        """
        ...

    def create_fallback_plan(self, context: UpdateContext,
                             max_children: int) -> RebalancePlan:
        """
        Generate a guaranteed fallback plan when LLM fails.

        This method MUST be synchronous and MUST NOT return None.
        It provides reliability when LLM is unavailable (timeout,
        rate limit, network error, etc.).

        The typical fallback behavior is to convert all PENDING_REVIEW
        fragments to ACTIVE leaves without semantic reorganization.

        Args:
            context: Read-only snapshot of the category's current state.
            max_children: Maximum allowed children (may be exceeded).

        Returns:
            A valid RebalancePlan (never None).
        """
        ...
