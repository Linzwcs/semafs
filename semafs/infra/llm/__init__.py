"""
LLM API adapters for SemaFS.

This package provides adapters for various LLM providers, all implementing
the BaseLLMAdapter interface from semafs.ports.llm.

Available Adapters:
    - OpenAIAdapter: For OpenAI's GPT models (gpt-4o, gpt-4o-mini, etc.)
    - AnthropicAdapter: For Anthropic's Claude models (claude-haiku-4-5-20251001, etc.)

Requirements:
    - OpenAI: `pip install openai` + OPENAI_API_KEY env var
    - Anthropic: `pip install anthropic` + ANTHROPIC_API_KEY env var

Usage:
    from openai import AsyncOpenAI
    from semafs.infra.llm.openai import OpenAIAdapter

    client = AsyncOpenAI()
    adapter = OpenAIAdapter(client, model="gpt-4o")

    # Use with HybridStrategy
    from semafs.strategies.hybrid import HybridStrategy
    strategy = HybridStrategy(adapter, max_children=10)
"""
from .openai import OpenAIAdapter
from .anthropic import AnthropicAdapter

__all__ = [
    "OpenAIAdapter",
    "AnthropicAdapter",
]
