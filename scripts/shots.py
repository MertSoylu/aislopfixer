"""Regenerate the README screenshots (shots/*.svg) from a live TUI run.

Drives the real app over a small demo project with Textual's pilot driver and
saves an SVG per screen. Run whenever a screen changes visibly:

    PYTHONPATH=src python scripts/shots.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from aislopfixer.app import AISlopFixerApp

SHOTS = Path(__file__).resolve().parent.parent / "shots"
SIZE = (110, 32)

# Representative slop — one demo file per major category family.
DEMO = {
    "index.html": (
        "<!doctype html>\n"
        "<html>\n"
        "<head><title>LaunchKit</title></head>\n"
        "<body>\n"
        '  <section class="hero bg-gradient-to-r from-purple-500 '
        'via-fuchsia-500 to-pink-500">\n'
        "    <h1>Unlock seamless solutions like never before</h1>\n"
        "    <p>Trusted by 10,000+ developers worldwide.</p>\n"
        "    <p>As an AI language model, I cannot browse the internet.</p>\n"
        '    <a href="#">Get started</a>\n'
        '    <img src="hero.png" alt="image">\n'
        "  </section>\n"
        "</body>\n"
        "</html>\n"
    ),
    "app.js": (
        "const q = `SELECT * FROM users WHERE id = ${userId}`;\n"
        "try { start(); } catch (e) {}\n"
        "// ... rest of the code ...\n"
    ),
    "styles.css": (
        ".hero { background: linear-gradient(135deg, #8b5cf6 0%, "
        "#ec4899 100%); }\n"
    ),
}


async def main() -> None:
    SHOTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        for name, text in DEMO.items():
            (Path(td) / name).write_text(text, encoding="utf-8")

        app = AISlopFixerApp(initial_path=td)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause(0.6)
            app.save_screenshot(filename="1-splash.svg", path=str(SHOTS))
            await pilot.press("enter")          # splash -> path
            await pilot.pause(0.3)
            await pilot.press("enter")          # path -> scan
            await pilot.pause(0.5)
            app.save_screenshot(filename="2-scan.svg", path=str(SHOTS))
            await pilot.pause(2.5)              # scan -> results
            app.save_screenshot(filename="3-results.svg", path=str(SHOTS))
            await pilot.press("x")              # export picker
            await pilot.pause(0.4)
            app.save_screenshot(filename="5-export.svg", path=str(SHOTS))
            await pilot.press("escape")
            await pilot.pause(0.2)
            await pilot.press("q")              # results -> summary
            await pilot.pause(1.2)
            app.save_screenshot(filename="4-summary.svg", path=str(SHOTS))
    print(f"wrote 5 screenshots to {SHOTS}")


if __name__ == "__main__":
    asyncio.run(main())
