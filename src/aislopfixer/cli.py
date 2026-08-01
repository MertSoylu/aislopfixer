"""Command-line entry point.

One mode: the interactive TUI. The headless/CI surface (``--check``, JSON,
SARIF, exit codes) is deliberately gone — this tool measures a design and
proposes a replacement, and neither of those is a pass/fail gate a build should
hang on. What a coding agent needs is exported from the report screen as a
brief (``x``), which lands in ``.aislopfixer/brief.md`` and on the clipboard.
"""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aislopfixer",
        description="Ölç ve düzelt: bir web projesinin tasarımı ne kadar şablon?",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Taranacak proje klasörü (verilmezse arayüzde sorulur).",
    )
    parser.add_argument(
        "--pages",
        action="append",
        metavar="YOL",
        default=None,
        help=(
            "Depo içinde ölçülecek sitenin yolu, ör. `app/(marketing)`. "
            "Ağacın tamamı yine okunur — bileşenler nerede dururlarsa dursunlar "
            "çözülür — süzülen şey ölçümün neyi anlattığıdır. Birden çok kez "
            "verilebilir; `.aislopfixer.toml` içindeki `pages` ile aynı iş."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"aislopfixer {__version__}"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from .app import AISlopFixerApp

    AISlopFixerApp(initial_path=args.path, pages=args.pages).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
