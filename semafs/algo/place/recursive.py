"""LLM recursive placement algorithm."""

from __future__ import annotations

from dataclasses import dataclass

from ...core.node import Node, NodeType
from ...core.placement import (
    PlacementAction,
    PlacementDecision,
    PlacementRoute,
    PlacementStep,
)
from ...ports.llm import LLMAdapter
from ...ports.store import NodeStore


@dataclass(frozen=True)
class PlacementConfig:
    """Config for recursive placement."""

    max_depth: int = 4
    min_confidence: float = 0.55


class LLMRecursivePlacer:
    """Top-down recursive path routing driven by LLM."""

    def __init__(
        self,
        store: NodeStore,
        adapter: LLMAdapter,
        config: PlacementConfig = PlacementConfig(),
    ):
        self._store = store
        self._adapter = adapter
        self._config = config

    async def place(
        self,
        content: str,
        start_path: str = "root",
    ) -> PlacementRoute:
        """Generate recursive placement route and final target path."""
        current_path = start_path
        steps: list[PlacementStep] = []
        final_reasoning = "No decision generated."

        for depth in range(self._config.max_depth):
            current = await self._store.get_by_path(current_path)
            if not current:
                break
            children = await self._category_children(current)
            if not children:
                final_reasoning = "No subcategories; stay at current path."
                steps.append(
                    self._step(
                        depth,
                        current_path,
                        PlacementDecision(
                            action=PlacementAction.STAY,
                            reasoning=final_reasoning,
                            confidence=1.0,
                        ),
                    )
                )
                break

            payload = await self._adapter.call_placement(
                content=content,
                current_path=current.path.value,
                current_summary=current.summary or "",
                children=tuple(
                    {
                        "name": child.name,
                        "path": child.path.value,
                        "summary": child.summary or "",
                    } for child in children
                ),
            )
            decision = self._parse_decision(payload)
            steps.append(self._step(depth, current.path.value, decision))
            final_reasoning = decision.reasoning or final_reasoning

            if decision.action != PlacementAction.DESCEND:
                break
            if decision.confidence < self._config.min_confidence:
                final_reasoning = (
                    "Confidence below threshold; keep current path."
                )
                break

            target = self._resolve_target_child(
                decision.target_child,
                children,
            )
            if not target:
                final_reasoning = "Target child invalid; keep current path."
                break
            current_path = target.path.value

        return PlacementRoute(
            target_path=current_path,
            steps=tuple(steps),
            reasoning=final_reasoning,
        )

    async def _category_children(self, node: Node) -> list[Node]:
        if node.node_type != NodeType.CATEGORY:
            return []
        children = await self._store.list_children(node.id)
        return [
            child for child in children
            if child.node_type == NodeType.CATEGORY
        ]

    @staticmethod
    def _resolve_target_child(
        target: str | None,
        children: list[Node],
    ) -> Node | None:
        if not target:
            return None
        target_lower = target.strip().lower()
        by_name = {child.name.lower(): child for child in children}
        if target_lower in by_name:
            return by_name[target_lower]
        by_path = {child.path.value.lower(): child for child in children}
        return by_path.get(target_lower)

    @staticmethod
    def _parse_decision(payload: dict) -> PlacementDecision:
        raw_action = str(payload.get("action", "stay")).strip().lower()
        if raw_action == PlacementAction.DESCEND.value:
            action = PlacementAction.DESCEND
        else:
            action = PlacementAction.STAY
        target_child = str(payload.get("target_child", "")).strip() or None
        reasoning = str(payload.get("reasoning", "")).strip()
        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = min(1.0, max(0.0, confidence))
        return PlacementDecision(
            action=action,
            target_child=target_child,
            reasoning=reasoning,
            confidence=confidence,
        )

    @staticmethod
    def _step(
        depth: int,
        current_path: str,
        decision: PlacementDecision,
    ) -> PlacementStep:
        return PlacementStep(
            depth=depth,
            current_path=current_path,
            decision=decision,
        )
