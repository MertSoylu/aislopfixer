"""Curated design-system archetypes — the shapes a derived system can take.

The tool has to replace a default with something, and "something" cannot itself
be a default, or it would just move every project onto a new template. So the
archetypes are hand-written and deliberately opinionated: each one takes a
position on type, rhythm, edges, depth and alignment that the others do not.
There are six, they disagree with each other, and a project gets one.

Every archetype specifies *relationships*, not just values — a scale ratio
rather than a list of sizes, a band set keyed by section role rather than one
number, an alignment doctrine the transformer can act on. That is what makes
the output a system instead of a re-skin.

Hues stay abstract here (``accent_hue`` is a starting angle). ``derive`` moves
them onto the project's own colour when the project has one.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Archetype:
    key: str
    name: str
    note: str                       # one line, shown in the TUI picker
    display_family: str
    body_family: str
    mono_family: str
    base_size: float                # rem, body text
    ratio: float                    # type scale ratio
    display_leading: float
    body_leading: float
    display_tracking: str
    body_tracking: str
    accent_hue: float
    accent_chroma: float
    support_offset: float           # degrees from accent for the second hue
    # Absolute, *not* an offset from the accent. The accent hue is rotated per
    # project (and can be inherited from the project's own brand colour), and a
    # relative neutral followed it around the wheel — the Terminal archetype's
    # cool slate paper came out pink once its green accent moved. Warm paper
    # must stay warm whatever the accent does.
    neutral_hue: float
    neutral_tint: float             # 0..0.14 — how far the neutrals are pulled
    bands: dict[str, str]           # section role → vertical rhythm
    measures: dict[str, str]        # role → max width
    radii: dict[str, str]
    shadows: dict[str, str]
    durations: dict[str, str]
    easings: dict[str, str]
    align: str                      # "left" | "mixed" | "center-hero"
    grid: str                       # doctrine string acted on by the transform
    gap: tuple[str, str]            # (column gap, row gap)
    doctrine: list[str] = field(default_factory=list)


def _bands(open_: str, narrative: str, dense: str, close: str) -> dict[str, str]:
    return {"open": open_, "narrative": narrative, "dense": dense, "close": close}


ARCHETYPES: tuple[Archetype, ...] = (
    Archetype(
        key="editorial",
        name="Editorial",
        note="Serif display, warm paper, hairline rules, generous measure",
        display_family='"Signifier", "Spectral", Georgia, serif',
        body_family='"Söhne", "Inter", ui-sans-serif, system-ui, sans-serif',
        mono_family='"Berkeley Mono", ui-monospace, SFMono-Regular, monospace',
        base_size=1.0625, ratio=1.28,
        display_leading=0.98, body_leading=1.7,
        display_tracking="-0.032em", body_tracking="0",
        accent_hue=14, accent_chroma=0.85, support_offset=196,
        neutral_hue=32, neutral_tint=0.075,
        bands=_bands("7.5rem", "6rem", "3.5rem", "2.5rem"),
        measures={"read": "46ch", "narrow": "62rem", "content": "74rem", "wide": "94rem"},
        radii={"panel": "2px", "control": "6px", "pill": "999px"},
        shadows={"lift": "0 1px 2px rgb(28 25 23 / 0.06)",
                 "float": "0 12px 32px -12px rgb(28 25 23 / 0.28)"},
        durations={"tint": "150ms", "move": "280ms"},
        easings={"enter": "cubic-bezier(0.33, 1, 0.68, 1)",
                 "exit": "cubic-bezier(0.32, 0, 0.67, 0)"},
        align="left", grid="asymmetric-12", gap=("2.5rem", "3.5rem"),
        doctrine=[
            "Bölüm başlıkları sola hizalı; yalnızca hero ortalanabilir.",
            "Kartlar yerine üstten çizgi (border-t) ile ayrılmış bloklar.",
            "Ana ızgara 12 sütun; içerik ağırlığına göre 7/5 ve 5/6 bölünür.",
        ],
    ),
    Archetype(
        key="swiss",
        name="Swiss",
        note="Grotesk, achromatic, no radius, no shadow, strict grid",
        display_family='"Helvetica Now Display", "Inter Tight", Arial, sans-serif',
        body_family='"Helvetica Now Text", "Inter", Arial, sans-serif',
        mono_family='ui-monospace, SFMono-Regular, monospace',
        base_size=1.0, ratio=1.5,
        display_leading=0.92, body_leading=1.5,
        display_tracking="-0.04em", body_tracking="-0.006em",
        accent_hue=6, accent_chroma=1.0, support_offset=210,
        neutral_hue=0, neutral_tint=0.0,
        bands=_bands("6rem", "4.5rem", "3rem", "1.5rem"),
        measures={"read": "38ch", "narrow": "56rem", "content": "72rem", "wide": "100%"},
        radii={"panel": "0", "control": "0", "pill": "0"},
        shadows={"lift": "none", "float": "none"},
        durations={"tint": "120ms", "move": "200ms"},
        easings={"enter": "cubic-bezier(0.2, 0, 0, 1)",
                 "exit": "cubic-bezier(0.4, 0, 1, 1)"},
        align="left", grid="strict-12", gap=("1.5rem", "1.5rem"),
        doctrine=[
            "Hiyerarşi renk veya gölge ile değil, ağırlık ve ölçü ile kurulur.",
            "Yüzeyler kenarlıksız; ayrım yalnızca boşluk ve çizgi ile.",
            "Her şey 12 sütunlu ızgaraya oturur, taşma yok.",
        ],
    ),
    Archetype(
        key="terminal",
        name="Terminal",
        note="Mono display, deep ink, dense rhythm, rules instead of cards",
        display_family='"Berkeley Mono", "JetBrains Mono", ui-monospace, monospace',
        body_family='"Inter", ui-sans-serif, system-ui, sans-serif',
        mono_family='"Berkeley Mono", ui-monospace, SFMono-Regular, monospace',
        base_size=0.9375, ratio=1.2,
        display_leading=1.1, body_leading=1.6,
        display_tracking="-0.01em", body_tracking="0.002em",
        accent_hue=152, accent_chroma=0.9, support_offset=42,
        neutral_hue=194, neutral_tint=0.09,
        bands=_bands("4.5rem", "3.5rem", "2rem", "1.25rem"),
        measures={"read": "72ch", "narrow": "50rem", "content": "68rem", "wide": "88rem"},
        radii={"panel": "3px", "control": "3px", "pill": "3px"},
        shadows={"lift": "none",
                 "float": "0 0 0 1px rgb(16 24 22 / 0.9), 0 8px 24px -8px rgb(0 0 0 / 0.6)"},
        durations={"tint": "90ms", "move": "160ms"},
        easings={"enter": "steps(4, end)", "exit": "linear"},
        align="left", grid="strict-12", gap=("1.25rem", "1.75rem"),
        doctrine=[
            "Kutular yerine yatay çizgiler; bilgi tablo gibi hizalanır.",
            "Sayılar tabular; hizalama sütun başına sabit.",
            "Hareket kısa ve kademeli, yumuşak değil.",
        ],
    ),
    Archetype(
        key="warmcraft",
        name="Warm Craft",
        note="Humanist sans, sand neutrals, layered depth, medium radius",
        display_family='"Fraunces", "Recoleta", Georgia, serif',
        body_family='"Inter", ui-sans-serif, system-ui, sans-serif',
        mono_family='ui-monospace, SFMono-Regular, monospace',
        base_size=1.0625, ratio=1.25,
        display_leading=1.05, body_leading=1.72,
        display_tracking="-0.018em", body_tracking="0",
        accent_hue=32, accent_chroma=0.8, support_offset=142,
        neutral_hue=38, neutral_tint=0.11,
        bands=_bands("6.5rem", "5rem", "3rem", "2rem"),
        measures={"read": "42ch", "narrow": "58rem", "content": "70rem", "wide": "90rem"},
        radii={"panel": "14px", "control": "10px", "pill": "999px"},
        shadows={"lift": "0 1px 2px rgb(61 45 30 / 0.07), 0 2px 6px -2px rgb(61 45 30 / 0.05)",
                 "float": "0 18px 40px -18px rgb(61 45 30 / 0.35)"},
        durations={"tint": "160ms", "move": "300ms"},
        easings={"enter": "cubic-bezier(0.22, 1, 0.36, 1)",
                 "exit": "cubic-bezier(0.55, 0, 1, 0.45)"},
        align="mixed", grid="asymmetric-12", gap=("2rem", "3rem"),
        doctrine=[
            "Derinlik iki katmanlı: taşıyıcı yüzey düz, yalnızca öne çıkan kalkık.",
            "Bölüm başlıkları dönüşümlü — anlatı bölümleri sola, özet bölümler ortaya.",
            "Yumuşak yarıçap yalnızca kontrollerde; büyük yüzeyler daha keskin.",
        ],
    ),
    Archetype(
        key="contrast",
        name="High Contrast",
        note="Heavy display, near-black surfaces, one vivid accent",
        display_family='"Inter Tight", "Archivo", ui-sans-serif, sans-serif',
        body_family='"Inter", ui-sans-serif, system-ui, sans-serif',
        mono_family='ui-monospace, SFMono-Regular, monospace',
        base_size=1.0, ratio=1.42,
        display_leading=0.9, body_leading=1.55,
        display_tracking="-0.045em", body_tracking="-0.004em",
        accent_hue=88, accent_chroma=1.0, support_offset=300,
        neutral_hue=252, neutral_tint=0.05,
        bands=_bands("8rem", "5.5rem", "3rem", "2rem"),
        measures={"read": "40ch", "narrow": "54rem", "content": "76rem", "wide": "100%"},
        radii={"panel": "0", "control": "999px", "pill": "999px"},
        shadows={"lift": "none", "float": "0 0 0 2px currentColor"},
        durations={"tint": "110ms", "move": "240ms"},
        easings={"enter": "cubic-bezier(0.16, 1, 0.3, 1)",
                 "exit": "cubic-bezier(0.7, 0, 0.84, 0)"},
        align="left", grid="bleed-12", gap=("1.75rem", "2.5rem"),
        doctrine=[
            "Yüzeyler keskin, kontroller tam yuvarlak — zıtlık kasıtlı.",
            "Gölge yok; yükseklik kontrast ve kenarlıkla anlatılır.",
            "En az bir bölüm tam genişlik ve ters zemin.",
        ],
    ),
    Archetype(
        key="archive",
        name="Archive",
        note="Condensed display, cool paper, tabular figures, tight rules",
        display_family='"Roboto Condensed", "Oswald", ui-sans-serif, sans-serif',
        body_family='"Source Serif 4", Georgia, serif',
        mono_family='ui-monospace, SFMono-Regular, monospace',
        base_size=1.0625, ratio=1.33,
        display_leading=1.0, body_leading=1.68,
        display_tracking="-0.01em", body_tracking="0.004em",
        accent_hue=222, accent_chroma=0.75, support_offset=28,
        neutral_hue=214, neutral_tint=0.06,
        bands=_bands("5.5rem", "4.5rem", "2.5rem", "1.75rem"),
        measures={"read": "50ch", "narrow": "52rem", "content": "66rem", "wide": "84rem"},
        radii={"panel": "1px", "control": "2px", "pill": "2px"},
        shadows={"lift": "0 1px 0 rgb(30 41 59 / 0.10)", "float": "none"},
        durations={"tint": "130ms", "move": "220ms"},
        easings={"enter": "cubic-bezier(0.25, 0.46, 0.45, 0.94)",
                 "exit": "cubic-bezier(0.55, 0.06, 0.68, 0.19)"},
        align="left", grid="strict-12", gap=("2rem", "2.25rem"),
        doctrine=[
            "Sayılar tabular ve sağa hizalı; ölçüler karşılaştırılabilir olmalı.",
            "Ayrım çizgi ile, kutu ile değil.",
            "Başlıklar sıkışık ve büyük; gövde serif ve rahat.",
        ],
    ),
)

BY_KEY: dict[str, Archetype] = {a.key: a for a in ARCHETYPES}
