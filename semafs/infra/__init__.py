"""
Infrastructure adapters for external services.

This package contains adapters that implement port interfaces for
external services like LLM providers.

Subpackages:
    - llm/: LLM API adapters (OpenAI, Anthropic)

Design Principle:
    Infrastructure code should be isolated from domain logic.
    All adapters implement protocols defined in semafs.ports.
"""
