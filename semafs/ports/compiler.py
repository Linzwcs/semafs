"""Plan compiler port."""

from typing import Protocol, runtime_checkable

from ..core.plan.pipeline import CompileResult
from ..core.snapshot import Snapshot


@runtime_checkable
class PlanCompiler(Protocol):
    """Compile raw strategy output into executable plan."""

    async def compile(self, snapshot: Snapshot) -> CompileResult:
        """Compile one snapshot into final plan."""
        ...
