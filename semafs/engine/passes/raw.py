from __future__ import annotations

import re
from dataclasses import replace

from ...core.plan.raw import RawPlan, RawMerge, RawGroup
from ...core.rules import CATEGORY_UPDATED_NAME_RE
from .common import (
    ValidationCode,
    ValidationReport,
    log_reject,
    record_reject,
)

_SUMMARY_NOISE_TOKENS = (
    "op_type",
    "overall_reasoning",
    "updated_keywords",
    "\"ops\"",
)
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s*")
_KEYWORD_NOISE_RE = re.compile(r"^(leaf|rollup)_[0-9a-z_]+$|^\d{1,2}:\d{2}$")
_STOPWORDS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "from",
    "by",
    "is",
    "are",
    "be",
    "this",
    "that",
}


class RawValidationPass:
    """Validate and sanitize raw plan payload."""

    def run(self, raw_plan: RawPlan) -> tuple[RawPlan, ValidationReport]:
        accepted_ops = []
        rejects = []
        for op_index, op in enumerate(raw_plan.ops):
            if isinstance(op, RawMerge):
                evidence = tuple(e.strip() for e in op.evidence
                                 if isinstance(e, str) and e.strip())
                if not evidence:
                    record_reject(
                        rejects,
                        ValidationCode.RAW_MERGE_NO_EVIDENCE,
                        "Reject raw MERGE without evidence",
                        source_ids=op.source_ids,
                        op_index=op_index,
                    )
                    continue
                merged_content = (op.new_content or "").strip()
                if not merged_content:
                    record_reject(
                        rejects,
                        ValidationCode.RAW_MERGE_NO_CONTENT,
                        "Reject raw MERGE without content",
                        source_ids=op.source_ids,
                        op_index=op_index,
                    )
                    continue
                accepted_ops.append(
                    replace(
                        op,
                        evidence=evidence,
                        new_content=merged_content,
                    ))
                continue
            if isinstance(op, RawGroup):
                group_summary = self.sanitize_summary(op.category_summary)
                if not group_summary:
                    record_reject(
                        rejects,
                        ValidationCode.RAW_GROUP_NO_SUMMARY,
                        "Reject raw GROUP without category summary",
                        source_ids=op.source_ids,
                        op_index=op_index,
                    )
                    continue
                accepted_ops.append(
                    replace(
                        op,
                        category_summary=group_summary,
                        category_keywords=self.sanitize_keywords(
                            op.category_keywords),
                    ))
                continue
            accepted_ops.append(op)

        validated = replace(
            raw_plan,
            ops=tuple(accepted_ops),
            updated_name=self.sanitize_category_name(raw_plan.updated_name),
            updated_keywords=self.sanitize_keywords(raw_plan.updated_keywords),
            updated_summary=self.sanitize_summary(raw_plan.updated_summary),
        )
        return validated, ValidationReport(rejects=tuple(rejects))

    @staticmethod
    def sanitize_category_name(value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip().lower()
        if not candidate:
            return None
        if not CATEGORY_UPDATED_NAME_RE.fullmatch(candidate):
            log_reject(
                ValidationCode.INVALID_UPDATED_NAME,
                "Reject invalid updated_name",
                value=repr(value),
            )
            return None
        return candidate

    @staticmethod
    def sanitize_summary(value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        lowered = text.lower()
        if any(token in lowered for token in _SUMMARY_NOISE_TOKENS):
            log_reject(
                ValidationCode.SUSPICIOUS_SUMMARY,
                "Reject suspicious updated_summary payload",
            )
            return None
        if "{" in text and "}" in text:
            log_reject(
                ValidationCode.JSON_LIKE_SUMMARY,
                "Reject JSON-like updated_summary payload",
            )
            return None

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            lines = [_BULLET_PREFIX_RE.sub("", line) for line in lines]
            text = " ".join(line for line in lines if line)

        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return None
        return text[:500]

    @staticmethod
    def sanitize_keywords(value: tuple[str, ...]) -> tuple[str, ...]:
        out = []
        seen = set()
        for item in value:
            token = re.sub(r"\s+", " ", item.strip().lower())
            if not token or token in seen:
                continue
            if token in _STOPWORDS:
                continue
            if _KEYWORD_NOISE_RE.fullmatch(token):
                continue
            if any(ch in token for ch in (":", "/", "\\")):
                continue
            seen.add(token)
            out.append(token)
            if len(out) >= 6:
                break
        return tuple(out)
