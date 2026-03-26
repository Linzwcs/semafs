"""Resolved plan-level metadata sanitation pass."""

from __future__ import annotations

from dataclasses import replace

from ...core.plan.ops import Plan
from .common import ValidationReport
from .raw import RawValidationPass


class MetaValidationPass:
    """Sanitize resolved plan metadata fields."""

    def run(self, plan: Plan) -> tuple[Plan, ValidationReport]:
        validated = replace(
            plan,
            updated_name=RawValidationPass.sanitize_category_name(
                plan.updated_name
            ),
            updated_keywords=RawValidationPass.sanitize_keywords(
                plan.updated_keywords
            ),
            updated_summary=RawValidationPass.sanitize_summary(
                plan.updated_summary
            ),
        )
        return validated, ValidationReport()
