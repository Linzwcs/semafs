"""
Port interfaces for SemaFS (Hexagonal Architecture).

This package defines the interface protocols that separate the core
domain from external concerns (storage, LLM providers, rendering).
Implementations of these protocols are called "adapters".

Modules:
    - repo: NodeRepository protocol for storage abstraction
    - strategy: Strategy protocol for reorganization decisions
    - llm: BaseLLMAdapter base class for LLM integrations
    - factory: UoWFactory and IUnitOfWork for transaction management
    - renderer: Renderer protocol for view formatting

Design Principles:
    1. Protocols define interfaces, not implementations
    2. Core domain depends only on ports, never on adapters
    3. Adapters can be swapped without changing domain code
    4. All protocols use async/await for IO operations

Usage:
    # Import protocols for type hints
    from semafs.ports import NodeRepository, Strategy

    # Import implementations from their respective packages
    from semafs.storage.sqlite import SQLiteUoWFactory
    from semafs.strategies.hybrid import HybridStrategy
"""
from .repo import NodeRepository
from .strategy import Strategy
from .llm import BaseLLMAdapter
from .factory import UoWFactory, IUnitOfWork
from .renderer import Renderer

__all__ = [
    "NodeRepository",
    "Strategy",
    "BaseLLMAdapter",
    "UoWFactory",
    "IUnitOfWork",
    "Renderer",
]
