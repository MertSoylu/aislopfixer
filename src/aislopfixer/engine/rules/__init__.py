"""Importing this package registers every rule via decorator side effects."""

from . import (  # noqa: F401
    accessibility,
    ai_leaks,
    buzzwords,
    codegen,
    duplicates,
    markdown_tells,
    placeholders,
    prose_tells,
)
