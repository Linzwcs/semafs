"""
SemaFS: Semantic File System for LLM-powered knowledge organization.

SemaFS is a semantic filesystem that uses LLM-powered strategies to
automatically organize and maintain a hierarchical tree of knowledge
fragments. It implements a clean architecture with ports & adapters
pattern, supporting multiple storage backends and organization strategies.

Core Concept:
    Users write memory fragments to categories, and SemaFS automatically
    reorganizes them using either rule-based or LLM-based strategies
    (merge, group, move operations) to keep the knowledge tree
    well-structured and semantically coherent.

Quick Start:
    >>> from semafs import SemaFS
    >>> from semafs.storage.sqlite import SQLiteUoWFactory
    >>> from semafs.strategies.rule import RuleOnlyStrategy
    >>>
    >>> # Initialize
    >>> factory = SQLiteUoWFactory("knowledge.db")
    >>> await factory.init()
    >>> semafs = SemaFS(factory, RuleOnlyStrategy())
    >>>
    >>> # Write a fragment
    >>> frag_id = await semafs.write("root.work", "Meeting notes...", {})
    >>>
    >>> # Process and organize
    >>> await semafs.maintain()
    >>>
    >>> # Read back
    >>> view = await semafs.read("root.work")

Architecture:
    - core/: Domain model (Node, Ops, Enums, Exceptions, Views)
    - ports/: Interface protocols (Repository, Strategy, LLM, Factory)
    - strategies/: Strategy implementations (RuleOnly, Hybrid)
    - infra/: Infrastructure adapters (OpenAI, Anthropic)
    - storage/: Storage implementations (SQLite)
    - executor.py: Plan execution engine
    - uow.py: Unit of Work transaction management
    - semafs.py: Main facade API
    - renderer.py: View rendering utilities

License:
    MIT License - See LICENSE file for details.
"""
from .semafs import SemaFS

__version__ = "0.2.0"
__all__ = ["SemaFS", "__version__"]
