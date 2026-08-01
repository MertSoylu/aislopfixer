"""Write a derived system out as real code the project can use.

The output is one stylesheet containing the same tokens twice: once inside
``@theme``, which is what Tailwind v4 reads to generate ``bg-accent`` and
``py-band-open``, and once inside ``:root``, which is what a plain-CSS or
Tailwind-v3 project reads. Duplicating them is deliberate — it makes the file
correct everywhere without the tool having to be right about which stack it is
looking at, and an unknown at-rule is inert in a browser rather than an error.

Tailwind v3 needs the names registered in a JS config as well, so a matching
``theme.extend`` snippet is emitted next to it. Patching the user's own
``tailwind.config`` is deliberately *not* done: that file often carries plugins
and computed values, and a rewrite that breaks a build is worse than a line of
instructions.
"""

from __future__ import annotations

import os
from pathlib import Path

from .derive import DesignSystem

SYSTEM_DIR = ".aislopfixer"
SYSTEM_CSS = "system.css"
SYSTEM_JS = "system.theme.cjs"

_CONFIG_NAMES = ("tailwind.config.js", "tailwind.config.ts",
                 "tailwind.config.cjs", "tailwind.config.mjs")


def detect_tailwind(root: str) -> str:
    """``"v4"``, ``"v3"`` or ``"none"`` for the project at ``root``."""
    for name in _CONFIG_NAMES:
        if os.path.exists(os.path.join(root, name)):
            return "v3"
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d != "node_modules"]
        for name in filenames:
            if not name.endswith((".css", ".pcss", ".postcss")):
                continue
            try:
                head = Path(dirpath, name).read_text(encoding="utf-8-sig")[:4000]
            except (OSError, UnicodeDecodeError):
                continue
            if '@import "tailwindcss"' in head or "@import 'tailwindcss'" in head:
                return "v4"
            if "@tailwind base" in head:
                return "v3"
    return "none"


def token_pairs(system: DesignSystem) -> list[tuple[str, str, str]]:
    """``(group, custom property, value)`` for every token in the system.

    Names follow Tailwind v4's theme namespaces, so ``--color-accent`` becomes
    ``bg-accent``/``text-accent`` and ``--spacing-band-open`` becomes
    ``py-band-open`` with no extra configuration.
    """
    out: list[tuple[str, str, str]] = []
    for name, value in system.colors.items():
        out.append(("Renk", f"--color-{name}", value))
    for name, value in system.families.items():
        out.append(("Yazı ailesi", f"--font-{name}", value))
    for name, value in system.sizes.items():
        out.append(("Tip ölçeği", f"--text-{name}", value))
    for name, value in system.leading.items():
        out.append(("Satır yüksekliği", f"--leading-{name}", value))
    for name, value in system.tracking.items():
        out.append(("Harf aralığı", f"--tracking-{name}", value))
    for name, value in system.bands.items():
        out.append(("Bölüm ritmi", f"--spacing-band-{name}", value))
    for name, value in system.measures.items():
        out.append(("Ölçü", f"--container-{name}", value))
    for name, value in system.radii.items():
        out.append(("Yarıçap", f"--radius-{name}", value))
    for name, value in system.shadows.items():
        out.append(("Yükseklik", f"--shadow-{name}", value))
    for name, value in system.easings.items():
        out.append(("Yumuşatma", f"--ease-{name}", value))
    for name, value in system.durations.items():
        out.append(("Süre", f"--duration-{name}", value))
    return out


def token_css(system: DesignSystem) -> str:
    """The stylesheet text for a derived system."""
    pairs = token_pairs(system)
    lines: list[str] = [
        "/* aislopfixer — türetilmiş tasarım sistemi",
        f"   Arketip: {system.archetype.name} — {system.archetype.note}",
        f"   Aksan: {system.colors['accent']} ({system.accent_hue:.0f}°, "
        f"{'projeden alındı' if system.inherited_hue else 'türetildi'})",
        "",
    ]
    lines += [f"   · {rule}" for rule in system.doctrine]
    lines += [
        "",
        "   Bu dosya üretildi ve yeniden üretilebilir: aynı proje her zaman",
        "   aynı sistemi verir. Değerleri elle değiştirmek serbesttir. */",
        "",
        "@theme {",
    ]
    lines += _block(pairs, indent="  ")
    lines += ["}", "", "/* Tailwind kullanmayan (ya da v3) projeler için aynı",
              "   değerler düz özel özellik olarak. */", ":root {"]
    lines += _block(pairs, indent="  ")
    lines += ["}", ""]
    return "\n".join(lines)


def _block(pairs: list[tuple[str, str, str]], indent: str) -> list[str]:
    out: list[str] = []
    group = ""
    for name, prop, value in pairs:
        if name != group:
            out.append(f"{indent}/* {name} */" if not out else "")
            if out[-1] == "":
                out.append(f"{indent}/* {name} */")
            group = name
        out.append(f"{indent}{prop}: {value};")
    return out


def theme_js(system: DesignSystem) -> str:
    """Tailwind v3 ``theme.extend`` snippet mirroring the token file."""
    def obj(entries: dict[str, str], wrap: str = "var") -> str:
        rows = [
            f"      {_key(k)}: 'var(--{wrap}-{k})',"
            for k in entries
        ]
        return "\n".join(rows)

    return (
        "// aislopfixer — Tailwind v3 için tema uzantısı.\n"
        "// tailwind.config.js içinde:  theme: { extend: require('./"
        f"{SYSTEM_DIR}/{SYSTEM_JS}') }}\n"
        "// Değerler .aislopfixer/system.css içindeki özel özelliklerden okunur,\n"
        "// böylece iki dosya asla birbirinden ayrı düşmez.\n"
        "module.exports = {\n"
        "  colors: {\n" + obj(system.colors, "color") + "\n  },\n"
        "  fontFamily: {\n" + obj(system.families, "font") + "\n  },\n"
        "  fontSize: {\n" + obj(system.sizes, "text") + "\n  },\n"
        "  lineHeight: {\n" + obj(system.leading, "leading") + "\n  },\n"
        "  letterSpacing: {\n" + obj(system.tracking, "tracking") + "\n  },\n"
        "  spacing: {\n" + "\n".join(
            f"      {_key('band-' + k)}: 'var(--spacing-band-{k})',"
            for k in system.bands) + "\n  },\n"
        "  maxWidth: {\n" + obj(system.measures, "container") + "\n  },\n"
        "  borderRadius: {\n" + obj(system.radii, "radius") + "\n  },\n"
        "  boxShadow: {\n" + obj(system.shadows, "shadow") + "\n  },\n"
        "  transitionTimingFunction: {\n" + obj(system.easings, "ease") + "\n  },\n"
        "  transitionDuration: {\n" + obj(system.durations, "duration") + "\n  },\n"
        "};\n"
    )


def _key(name: str) -> str:
    return f"'{name}'" if "-" in name else name


def write_system(root: str, system: DesignSystem) -> list[str]:
    """Write the system files under ``<root>/.aislopfixer/``; returns paths."""
    out_dir = Path(root) / SYSTEM_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    css_path = out_dir / SYSTEM_CSS
    css_path.write_text(token_css(system), encoding="utf-8", newline="\n")
    written.append(str(css_path))

    if detect_tailwind(root) == "v3":
        js_path = out_dir / SYSTEM_JS
        js_path.write_text(theme_js(system), encoding="utf-8", newline="\n")
        written.append(str(js_path))
    return written


def wiring_hint(root: str) -> str:
    """The one line the user has to add for the tokens to take effect."""
    flavor = detect_tailwind(root)
    if flavor == "v4":
        return (f'Ana CSS dosyanın başına ekle:  @import "./{SYSTEM_DIR}/'
                f'{SYSTEM_CSS}";')
    if flavor == "v3":
        return (f"tailwind.config içinde:  theme: {{ extend: require('./"
                f"{SYSTEM_DIR}/{SYSTEM_JS}') }}  ·  ve HTML'e "
                f"{SYSTEM_DIR}/{SYSTEM_CSS} bağla")
    return f'HTML <head> içine ekle:  <link rel="stylesheet" href="{SYSTEM_DIR}/{SYSTEM_CSS}">'
