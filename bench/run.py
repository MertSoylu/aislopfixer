"""CLI: ``python -m bench.run`` — print calibration metrics, exit non-zero on miss.

Run from the repo root (the package resolves ``aislopfixer`` from ``src`` via the
project's pytest/pythonpath config; for a bare run, ``pip install -e .`` first).
"""

from __future__ import annotations

import sys

from .corpus import CASES
from .harness import evaluate, format_report


def main() -> int:
    r = evaluate(CASES)
    print(format_report(r))
    ok = r["recall"] == 1.0 and r["clean_fp"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
