"""Importing this package registers every rule via decorator side effects."""

from . import (  # noqa: F401
    accessibility,
    ai_leaks,
    buzzwords,
    codegen,
    design_slop,
    duplicates,
    imports,
    markdown_tells,
    merge_conflicts,
    placeholders,
    prose_tells,
    secrets,
    security,
)
