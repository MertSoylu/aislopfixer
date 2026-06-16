"""Command-line entry point."""

from __future__ import annotations

import argparse

from .app import AISlopFixerApp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="aislopfixer",
        description="Find & fix AI-generated slop in local web projects.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to the web project folder to scan (asked interactively if omitted).",
    )
    args = parser.parse_args(argv)
    AISlopFixerApp(initial_path=args.path).run()


if __name__ == "__main__":
    main()
