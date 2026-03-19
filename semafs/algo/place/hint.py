"""Hint-based placement algorithm."""

from ...core.placement import (
    PlacementAction,
    PlacementDecision,
    PlacementRoute,
    PlacementStep,
)


class HintPlacer:
    """Use hint path directly, fallback to 'root'."""

    async def place(self, content: str, hint: str | None) -> str:
        """Return hint if provided, otherwise 'root'."""
        return hint if hint else "root"

    async def place_recursive(
        self,
        content: str,
        start_path: str = "root",
    ) -> PlacementRoute:
        """Hint placer does not recurse; it stays at start path."""
        decision = PlacementDecision(
            action=PlacementAction.STAY,
            reasoning="Hint placer keeps current path.",
            confidence=1.0,
        )
        return PlacementRoute(
            target_path=start_path,
            steps=(
                PlacementStep(
                    depth=0,
                    current_path=start_path,
                    decision=decision,
                ),
            ),
            reasoning=decision.reasoning,
        )
