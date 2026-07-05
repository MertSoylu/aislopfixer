"""Command-line entry point.

Two modes:

* **TUI** (default) — the interactive Textual app.
* **Headless** (``--check`` / ``--json`` / ``--sarif`` / ``--prompt`` /
  ``--fix``) — scan,
  print, exit with a CI-friendly status code. See :mod:`aislopfixer.headless`.
"""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aislopfixer",
        description="Find & fix AI-generated slop in local web projects.",
        epilog=(
            "exit codes (headless): 0 clean, 1 findings at/above --fail-on, "
            "2 usage error"
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to the web project folder to scan (asked interactively if omitted).",
    )
    parser.add_argument(
        "--version", action="version", version=f"aislopfixer {__version__}"
    )
    head = parser.add_argument_group("headless mode (CI / scripts / pre-commit)")
    head.add_argument(
        "--check",
        action="store_true",
        help="No TUI: scan, print findings, exit non-zero if slop is found.",
    )
    head.add_argument(
        "--json",
        action="store_true",
        help="Emit findings as JSON (implies --check).",
    )
    head.add_argument(
        "--sarif",
        action="store_true",
        help="Emit findings as SARIF 2.1.0 for GitHub code scanning "
        "(implies --check; wins over --json).",
    )
    head.add_argument(
        "--prompt",
        action="store_true",
        help="Emit a fix brief for an AI coding assistant instead of a "
        "report (implies --check; wins over --sarif/--json). Combine with "
        "--fix to auto-fix the safe findings and brief the agent on the rest.",
    )
    head.add_argument(
        "--fix",
        action="store_true",
        help="Apply safe automatic fixes before reporting (implies --check). "
        "Backups are written next to each file (.aislopfixer.bak).",
    )
    head.add_argument(
        "--fail-on",
        choices=["info", "warning", "error", "never"],
        default=None,
        help="Minimum severity that makes the exit code 1 "
        "(default: .aislopfixer.toml, else warning).",
    )
    head.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        metavar="0..1",
        help="Only report findings at or above this confidence "
        "(default: .aislopfixer.toml, else 0).",
    )
    head.add_argument(
        "--no-store",
        action="store_true",
        help="Ignore the project's .aislopfixer memory (allowlist/ledger).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check or args.json or args.sarif or args.prompt or args.fix:
        if not args.path:
            parser.error("headless mode needs a PATH")
        from .headless import run_check

        return run_check(
            args.path,
            as_json=args.json,
            as_sarif=args.sarif,
            as_prompt=args.prompt,
            fix=args.fix,
            fail_on=args.fail_on,
            min_confidence=args.min_confidence,
            use_store=not args.no_store,
        )

    from .app import AISlopFixerApp

    AISlopFixerApp(initial_path=args.path).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
