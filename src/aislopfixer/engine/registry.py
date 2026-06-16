"""Self-registering rule registry.

Rules register themselves at import time via the ``@file_rule`` / ``@cross_rule``
decorators. ``FILE_RULES`` run once per file; ``CROSS_RULES`` run once over the
whole file set (e.g. duplicate detection).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Finding, SourceFile


@runtime_checkable
class FileRule(Protocol):
    category: object

    def scan(self, sf: SourceFile) -> list[Finding]: ...


@runtime_checkable
class CrossRule(Protocol):
    category: object

    def scan_all(self, files: list[SourceFile]) -> list[Finding]: ...


FILE_RULES: list[FileRule] = []
CROSS_RULES: list[CrossRule] = []


def file_rule(cls):
    """Register a per-file rule class (instantiated with no args)."""
    FILE_RULES.append(cls())
    return cls


def cross_rule(cls):
    """Register a cross-file rule class (instantiated with no args)."""
    CROSS_RULES.append(cls())
    return cls


def reset() -> None:
    """Clear all registered rules (used by tests)."""
    FILE_RULES.clear()
    CROSS_RULES.clear()
