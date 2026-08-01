"""Copy shape: the words a template reaches for when it has nothing to say.

The design axes measure how a page looks; this one measures whether the page
has content or filler. It is deliberately structural rather than a banned-word
list — "seamless" in one sentence is a word choice, but a page whose section
headings are *Features / How It Works / Testimonials / Pricing / FAQ* and whose
hero says "Everything you need to ship faster" has no copy at all, it has
slots.

Every signal here is count-gated. One stock heading is a convention; five is a
table of contents for a template nobody wrote.
"""

from __future__ import annotations

import re

from ..models import Axis, Document, Element, Evidence, Observation
from .util import (cap_evidence, coefficient_of_variation, evidence_for)

_I = re.IGNORECASE

# Section headings that arrive with the template. Matched whole, so a page that
# says "Pricing that scales with you" is not counted — that one was written.
STOCK_HEADINGS = frozenset({
    "features", "our features", "key features", "core features",
    "how it works", "why choose us", "why us", "benefits", "our benefits",
    "testimonials", "what our customers say", "loved by developers",
    "pricing", "simple pricing", "simple, transparent pricing", "our pricing",
    "faq", "faqs", "frequently asked questions",
    "get started", "ready to get started?", "get started today",
    "everything you need", "built for teams", "trusted by teams",
    "our mission", "our story", "meet the team", "contact us",
})

# The current-generation prose tells. Phrasal, not single adjectives: a single
# adjective is a style; these constructions are a voice nobody chose.
_PHRASES: list[tuple[str, re.Pattern]] = [
    ("değil-ama kalıbı",
     re.compile(r"\b(?:it'?s|this is|we'?re)\s+not\s+just\s+[^.;!?]{3,60}?[—,-]\s*it'?s\b", _I)),
    ("ister-ister kalıbı",
     re.compile(r"\bwhether\s+you'?re\s+(?:a|an)\s+[^.;!?]{3,40}?\bor\b", _I)),
    ("günümüz dünyası",
     re.compile(r"\bin\s+today'?s\s+(?:fast[- ]paced|digital|modern|competitive)\b", _I)),
    ("gücünü açığa çıkar",
     re.compile(r"\bunlock\s+the\s+(?:power|potential|full\s+potential)\s+of\b", _I)),
    ("bir üst seviye",
     re.compile(r"\btake\s+your\s+[\w\s]{2,30}?\bto\s+the\s+next\s+level\b", _I)),
    ("ihtiyacın olan her şey",
     re.compile(r"\beverything\s+you\s+need\s+to\b", _I)),
    ("kredi kartı gerekmez",
     re.compile(r"\bno\s+credit\s+card\s+required\b", _I)),
    ("binlerce kişiye katıl",
     re.compile(r"\bjoin\s+(?:over\s+)?(?:thousands|\d[\d,.]*[km]?\+?)\s+of\b", _I)),
    ("üçlü paralel",
     re.compile(r"(?:^|[.>])\s*\b\w{3,12}\.\s+\w{3,12}\.\s+\w{3,12}\.")),
]

# Verb/adjective filler. Counted as a density, never reported one by one.
_BUZZWORDS = re.compile(
    r"\b(?:seamless(?:ly)?|effortless(?:ly)?|cutting[- ]edge|game[- ]?chang\w+|"
    r"revolutioniz\w+|elevat\w+|empower\w+|leverag\w+|supercharg\w+|unleash\w+|"
    r"harness\w*|streamlin\w+|robust|best[- ]in[- ]class|next[- ]level|"
    r"state[- ]of[- ]the[- ]art|world[- ]class|delve|tapestry|realm\b|"
    r"unparalleled|bespoke|holistic|synerg\w+)\b",
    _I,
)
_BUZZ_PER_100 = 1.2       # words per 100 above which the voice is filler
_MIN_WORDS = 120
_MIN_STOCK_HEADINGS = 3
_HEADINGS = frozenset({"h1", "h2", "h3"})

_CTA_PRIMARY = re.compile(
    r"\b(?:get\s+started(?:\s+free)?|start\s+(?:for\s+)?free|try\s+(?:it\s+)?free|"
    r"sign\s+up\s+free|start\s+free\s+trial)\b", _I)
_CTA_SECONDARY = re.compile(
    r"\b(?:learn\s+more|book\s+a\s+demo|watch\s+(?:the\s+)?demo|"
    r"see\s+how\s+it\s+works|contact\s+sales|talk\s+to\s+sales)\b", _I)

_EMOJI = re.compile(
    "[\U0001f680✨\U0001f3af\U0001f4a1⚡\U0001f525\U0001f389\U0001f31f⭐"
    "\U0001f4aa\U0001f6e0\U0001f512\U0001f4c8\U0001f4ca\U0001f3a8\U0001f916"
    "\U0001f449\U0001f4bb\U0001f308\U0001f9e0✅❤]")
_EMOJI_GATE = 3


def _text_elements(docs: list[Document]) -> list[tuple[Document, Element]]:
    """Leaf-ish elements that carry visible copy."""
    out: list[tuple[Document, Element]] = []
    for doc in docs:
        for el in doc.elements:
            if el.tag in ("script", "style", "head", "html", "meta", "link"):
                continue
            if el.own_text and len(el.own_text) > 1:
                out.append((doc, el))
    return out


def visible_text(docs: list[Document]) -> str:
    """All visible copy, concatenated — the corpus the density measures use."""
    return "\n".join(el.own_text for _, el in _text_elements(docs))


def analyze(docs: list[Document]) -> tuple[list[Observation], float]:
    """Copy observations plus the COPY axis repetition score (0..100)."""
    out: list[Observation] = []
    shares: list[float] = []
    pairs = _text_elements(docs)
    text = "\n".join(el.own_text for _, el in pairs)
    words = len(text.split())

    # `renders_tag` before `tag`: `const Title = styled.h2` means every
    # `<Title>` on the page is a heading, and reading only the authored tag made
    # a CSS-in-JS landing page look like one with no headings at all.
    headings = [(d, e) for d, e in pairs if (e.renders_tag or e.tag) in _HEADINGS]
    stock = [(d, e) for d, e in headings
             if e.own_text.strip().lower().rstrip(".!") in STOCK_HEADINGS]
    if len(stock) >= _MIN_STOCK_HEADINGS:
        share = len(stock) / max(1, len(headings))
        shares.append(share)
        listing = ", ".join(f"“{e.own_text.strip()}”" for _, e in stock[:6])
        out.append(Observation(
            axis=Axis.COPY,
            id="copy.stock_headings",
            title="Bölüm başlıkları şablon içindekiler tablosu",
            detail=(
                f"{len(headings)} başlığın {len(stock)}'i şablonla birlikte "
                f"gelen kelimeler: {listing}. Bunlar bölümün ne dediğini değil, "
                f"bölümün türünü söylüyor — okuyucu için bilgi taşımıyorlar."
            ),
            severity=round(min(1.0, 0.4 + share), 3),
            stat=f"{len(stock)}/{len(headings)} hazır başlık",
            evidence=cap_evidence([evidence_for(d, e, e.own_text[:50])
                                   for d, e in stock]),
            prescription=(
                "Başlığı iddia haline getir: “Features” yerine bölümün "
                "gerçekten söylediği şey. Başlığı okuyan biri bölümü "
                "okumadan ne öğreneceğini bilmeli."
            ),
        ))

    if words >= _MIN_WORDS:
        hits = _BUZZWORDS.findall(text)
        density = len(hits) * 100.0 / words
        if density >= _BUZZ_PER_100:
            shares.append(min(1.0, density / (_BUZZ_PER_100 * 3)))
            uniq = ", ".join(sorted({h.lower() for h in hits})[:8])
            out.append(Observation(
                axis=Axis.COPY,
                id="copy.filler_voice",
                title="Metin doldurucu kelimelerle yürüyor",
                detail=(
                    f"{words} kelimede {len(hits)} doldurucu "
                    f"(100 kelimede {density:.1f}): {uniq}. Bu kelimeler bir "
                    f"iddia taşımaz; okuyucu için hiçbir şeyi doğrulanabilir "
                    f"kılmazlar ve her üretilmiş sayfada aynı sıklıkta çıkarlar."
                ),
                severity=round(min(1.0, density / (_BUZZ_PER_100 * 3)), 3),
                stat=f"100 kelimede {density:.1f}",
                evidence=cap_evidence(_phrase_evidence(pairs, _BUZZWORDS)),
                prescription=(
                    "Her doldurucuyu ölçülebilir bir iddiayla değiştir ya da "
                    "cümleyi sil. “Seamless integration” yerine neyle, kaç "
                    "adımda entegre olduğunu yaz."
                ),
            ))

    found = [(label, rx) for label, rx in _PHRASES if rx.search(text)]
    if len(found) >= 2:
        shares.append(min(1.0, len(found) / 5.0))
        out.append(Observation(
            axis=Axis.COPY,
            id="copy.template_phrasing",
            title="Şablon cümle kalıpları",
            detail=(
                f"{len(found)} farklı kalıp bir arada: "
                + ", ".join(label for label, _ in found)
                + ". Tek başına her biri bir üslup tercihi olabilir; bir arada "
                  "bulunmaları metnin bir modelin varsayılan sesiyle "
                  "yazıldığını gösterir."
            ),
            severity=round(min(1.0, 0.3 + len(found) / 6.0), 3),
            stat=f"{len(found)} kalıp",
            evidence=cap_evidence(
                [e for _, rx in found for e in _phrase_evidence(pairs, rx)][:8]),
            prescription=(
                "Kalıpları söktükten sonra kalan cümleyi oku: bir şey "
                "söylüyorsa tut, söylemiyorsa sil. Sayfanın sesini ürünün "
                "gerçekten yaptığı iş belirlesin."
            ),
        ))

    if _CTA_PRIMARY.search(text) and _CTA_SECONDARY.search(text):
        shares.append(0.7)
        out.append(Observation(
            axis=Axis.COPY,
            id="copy.cta_pair",
            title="İkili çağrı düğmesi kalıbı",
            detail=(
                "Birincil “Get Started” + ikincil “Learn More” ikilisi, "
                "üretilmiş hero'nun standart donanımı. İki düğme, kullanıcıya "
                "iki farklı yol sunmak yerine kararsızlığı arayüze taşır."
            ),
            severity=0.45,
            stat="2 düğme",
            evidence=cap_evidence(_phrase_evidence(pairs, _CTA_PRIMARY), 4),
            prescription=(
                "Tek bir birincil eylem bırak ve onu ürünün gerçekten yaptığı "
                "şeyle adlandır. İkinciyi bağlantıya indir ya da kaldır."
            ),
        ))

    emoji = [(d, e) for d, e in pairs if _EMOJI.search(e.own_text)]
    if len(emoji) >= _EMOJI_GATE:
        shares.append(0.6)
        out.append(Observation(
            axis=Axis.COPY,
            id="copy.emoji_ui",
            title="Arayüz kopyasında dekoratif emoji",
            detail=(
                f"{len(emoji)} ayrı yerde başlık/etiket emojiyle süslenmiş. "
                f"Emoji burada bir anlam taşımıyor, ikon yerine geçiyor — "
                f"bu da tasarımın ikonografiye hiç girmediğini gösteriyor."
            ),
            severity=0.5,
            stat=f"{len(emoji)} yer",
            evidence=cap_evidence([evidence_for(d, e, e.own_text[:40])
                                   for d, e in emoji]),
            prescription=(
                "Emojiyi kaldır. Gerekiyorsa tek bir ikon seti seç ve ağırlığını "
                "yazı tipiyle uyumlu ayarla."
            ),
        ))

    lengths = [float(len(e.own_text.split())) for _, e in headings if e.own_text]
    if len(lengths) >= 4:
        cv = coefficient_of_variation(lengths)
        if cv < 0.25:
            shares.append(1.0 - cv / 0.25)
            out.append(Observation(
                axis=Axis.COPY,
                id="copy.uniform_headings",
                title="Başlıklar aynı uzunlukta",
                detail=(
                    f"{len(lengths)} başlığın kelime sayısı neredeyse sabit "
                    f"(değişkenlik %{cv * 100:.0f}). Başlık uzunluğu, "
                    f"söylenmesi gereken şeye göre değişmeli; sabit uzunluk "
                    f"başlıkların bir kalıba doldurulduğunu gösterir."
                ),
                severity=round(min(1.0, 1.0 - cv / 0.25), 3),
                stat=f"%{cv * 100:.0f} değişkenlik",
                evidence=cap_evidence([evidence_for(d, e, e.own_text[:50])
                                       for d, e in headings]),
                prescription=(
                    "Başlıkları içeriğe göre yaz: bazıları iki kelime, "
                    "bazıları bir cümle olsun."
                ),
            ))

    repetition = 100.0 * (sum(shares) / len(shares)) if shares else 0.0
    return out, round(repetition, 1)


def _phrase_evidence(pairs: list[tuple[Document, Element]],
                     rx: re.Pattern) -> list[Evidence]:
    out: list[Evidence] = []
    for doc, el in pairs:
        m = rx.search(el.own_text)
        if m is not None:
            out.append(evidence_for(doc, el, m.group(0)[:60]))
    return out
