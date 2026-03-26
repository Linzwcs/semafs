"""Shared validation primitives for compiler passes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ValidationCode(str, Enum):
    RAW_MERGE_NO_EVIDENCE = "RAW_MERGE_NO_EVIDENCE"
    RAW_MERGE_NO_CONTENT = "RAW_MERGE_NO_CONTENT"
    RAW_GROUP_NO_SUMMARY = "RAW_GROUP_NO_SUMMARY"
    INVALID_GROUP_PATH = "INVALID_GROUP_PATH"
    DUPLICATE_GROUP_SEGMENTS = "DUPLICATE_GROUP_SEGMENTS"
    REDUNDANT_GROUP_SEGMENT = "REDUNDANT_GROUP_SEGMENT"
    SEMANTIC_GROUP_OVERLAP = "SEMANTIC_GROUP_OVERLAP"
    GENERIC_GROUP_PATH = "GENERIC_GROUP_PATH"
    INVALID_GROUP_SOURCE_TYPE = "INVALID_GROUP_SOURCE_TYPE"
    INVALID_MERGE_SOURCE_TYPE = "INVALID_MERGE_SOURCE_TYPE"
    INVALID_MOVE_SOURCE_TYPE = "INVALID_MOVE_SOURCE_TYPE"
    GENERIC_MOVE_TARGET = "GENERIC_MOVE_TARGET"
    INVALID_RENAME_NAME = "INVALID_RENAME_NAME"
    REDUNDANT_UPDATED_NAME = "REDUNDANT_UPDATED_NAME"
    GENERIC_RENAME_NAME = "GENERIC_RENAME_NAME"
    LEAF_RENAME_BLOCKED = "LEAF_RENAME_BLOCKED"
    SKELETON_RENAME_BLOCKED = "SKELETON_RENAME_BLOCKED"
    INVALID_UPDATED_NAME = "INVALID_UPDATED_NAME"
    SUSPICIOUS_SUMMARY = "SUSPICIOUS_SUMMARY"
    JSON_LIKE_SUMMARY = "JSON_LIKE_SUMMARY"


@dataclass(frozen=True)
class ValidationReject:
    """Structured record for one validation rejection."""

    code: ValidationCode
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate report for one validation pass."""

    rejects: tuple[ValidationReject, ...] = ()

    @property
    def total_rejects(self) -> int:
        return len(self.rejects)

    def counts_by_code(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.rejects:
            key = item.code.value
            counts[key] = counts.get(key, 0) + 1
        return counts


def record_reject(
    rejects: list[ValidationReject],
    code: ValidationCode,
    message: str,
    **detail: Any,
) -> None:
    log_reject(code, message, **detail)
    rejects.append(ValidationReject(code=code, message=message, detail=detail))


def log_reject(
    code: ValidationCode,
    message: str,
    **detail: Any,
) -> None:
    detail_text = " ".join(f"{k}={v!r}" for k, v in detail.items())
    if detail_text:
        logger.warning(
            "plan_validate_reject code=%s message=%s %s",
            code.value,
            message,
            detail_text,
        )
        return
    logger.warning(
        "plan_validate_reject code=%s message=%s",
        code.value,
        message,
    )
