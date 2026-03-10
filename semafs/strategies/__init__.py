"""
Strategy implementations for knowledge tree reorganization.

This package provides concrete implementations of the Strategy protocol,
which determines how to reorganize a category's contents.

Available Strategies:
    - RuleOnlyStrategy: Deterministic, no LLM calls (for testing/mock)
    - HybridStrategy: LLM-powered with rule-based fallback (production)

Strategy Selection Guide:
    - Development/Testing: Use RuleOnlyStrategy for fast, predictable behavior
    - Production: Use HybridStrategy with an LLM adapter for semantic organization
    - Offline/Cost-sensitive: Use RuleOnlyStrategy or HybridStrategy with
      high threshold to minimize LLM calls

Usage:
    from semafs.strategies.rule import RuleOnlyStrategy
    from semafs.strategies.hybrid import HybridStrategy
    from semafs.infra.llm.openai import OpenAIAdapter

    # For testing/development
    strategy = RuleOnlyStrategy()

    # For production with LLM
    adapter = OpenAIAdapter(client, model="gpt-4o")
    strategy = HybridStrategy(adapter, max_children=10)
"""
from .rule import RuleOnlyStrategy
from .hybrid import HybridStrategy

__all__ = [
    "RuleOnlyStrategy",
    "HybridStrategy",
]
