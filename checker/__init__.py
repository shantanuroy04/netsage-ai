"""checker — deterministic Python rule checker (runs before every AI call)."""
from .runner import (
    EVIDENCE_COMMAND,
    SEVERITY_BY_STATUS,
    analyze,
    build_report,
    conflict_summary,
    failed_rules,
    has_conflict,
    run_all_checks,
)

__all__ = [
    "run_all_checks",
    "build_report",
    "analyze",
    "has_conflict",
    "conflict_summary",
    "failed_rules",
    "SEVERITY_BY_STATUS",
    "EVIDENCE_COMMAND",
]
