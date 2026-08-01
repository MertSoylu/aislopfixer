"""Section role classification — what each band of a page is *for*.

The template is not a set of classes, it is an order: hero → logos → features →
how it works → testimonials → pricing → FAQ → final CTA. Detecting that order
needs a name for each band, which is what this module produces.

Classification is content-first (what the band says) with structure as a
tie-breaker (how many equal children it has), because the same three-card grid
is a feature row, a pricing table or a testimonial wall depending only on the
words inside it. Anything unrecognized stays ``content`` — a wrong role would
put a real page into the canonical sequence and manufacture a finding.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ..models import Axis, Document

_I = re.IGNORECASE

# Canonical order of the generated landing page. Matching a long run of this is
# the structural half of the template score.
CANONICAL = [
    "nav", "hero", "logos", "features", "how", "stats",
    "testimonials", "pricing", "faq", "cta", "footer",
]

# Roles that describe a band's *shape* rather than its place in the landing
# sequence. They are deliberately outside :data:`CANONICAL`, so naming one
# neither extends the template run nor breaks it — the same transparency
# ``content`` already had. What they buy is everything else: a band the
# classifier can name gets its own rhythm token instead of the catch-all one,
# two pages made of different shapes stop reading as the same page, and the
# report can say how much of a project it could actually name.
STRUCTURAL = ["gallery", "list", "statement", "prose", "contact"]

ROLE_LABEL = {
    "nav": "Menü", "hero": "Hero", "logos": "Logo şeridi",
    "features": "Özellikler", "how": "Nasıl çalışır", "stats": "Sayı şeridi",
    "testimonials": "Yorumlar", "pricing": "Fiyatlandırma", "faq": "SSS",
    "cta": "Son çağrı", "footer": "Alt bilgi", "content": "İçerik",
    "gallery": "Görsel dizi", "list": "Liste / dizin", "statement": "Söz",
    "prose": "Metin", "contact": "İletişim",
}

# Turkish is not a translation layer here: a Turkish landing page reaches for
# its own stock phrases, and a tool whose interface is Turkish measuring only
# English pages is a blind spot with a flag on it. Each pattern below is the
# phrase a generated Turkish page actually uses, not a dictionary rendering of
# the English one.
_PRICING = re.compile(
    r"(?:^|\s)\$\d|\bper\s+month\b|/\s*mo\b|\bpricing\b|\bfiyat|\bpaket(?:ler)?\b|"
    r"\bayl[ıi]k\b|\b₺\s?\d|\btl\s*/\s*ay\b|\büyelik\b|\babonelik\b", _I)
_FAQ = re.compile(r"\bfaq\b|frequently\s+asked|sık\s+sorulan|sıkça\s+sorulan|"
                  r"merak\s+edilenler", _I)
_HOW = re.compile(r"how\s+it\s+works|nasıl\s+çalışır|\bstep\s+\d\b|\badım\s+\d|"
                  r"\b\d\s*\.\s*adım\b|nasıl\s+kullan", _I)
_TESTIMONIAL = re.compile(
    r"\btestimonial|what\s+(?:our|people)\s+(?:customers?|users?|clients?)?\s*say|"
    r"loved\s+by|müşteri(?:lerimiz)?\s+ne\s+diyor|kullanıcılar(?:ımız)?\s+ne\s+diyor|"
    r"\breferans(?:lar)?\b|\bcto\b|\bceo\b,|\bfounder\s+(?:at|of)\b|"
    r"\bkurucu(?:su)?\b|\bgenel\s+müdür\b",
    _I)
_LOGOS = re.compile(
    r"trusted\s+by|as\s+seen\s+(?:in|on)|featured\s+in|powering\s+teams|"
    r"companies\s+that\s+trust|bize\s+güvenenler|bizi\s+tercih\s+edenler|"
    r"\bbinlerce\s+(?:ekip|şirket|marka)", _I)
_STATS = re.compile(
    r"\b\d{1,3}(?:[.,]\d+)?%|\b\d[\d,.]*[km]\+|\b24\s*/\s*7\b|\b\d{1,4}x\b|"
    r"\b\d[\d,.]*\s*(?:bin|milyon)\+?", _I)
_CTA = re.compile(
    r"ready\s+to\s+(?:get\s+started|dive\s+in|begin)|get\s+started\s+(?:today|now|free)|"
    r"start\s+(?:your\s+)?free|hemen\s+başla|başlamaya\s+hazır|ücretsiz\s+dene|"
    r"hemen\s+dene|şimdi\s+kaydol|hemen\s+kaydol", _I)
_FEATURES = re.compile(
    r"\bfeatures?\b|everything\s+you\s+need|why\s+(?:choose|us)\b|"
    r"built\s+for|özellikler|neden\s+biz|ihtiyacınız\s+olan\s+her\s+şey|"
    r"öne\s+çıkan", _I)
_CONTACT = re.compile(
    r"\bcontact\s+us\b|\bget\s+in\s+touch\b|\biletişim\b|bize\s+ulaşın|"
    r"bize\s+yaz[ıi]n|\bdrop\s+us\s+a\s+line\b", _I)


def _child_blocks(doc: Document, idx: int) -> int:
    """Number of repeated sibling blocks the section contains (grid children)."""
    best = 0
    stack = [(idx, 0)]
    while stack:
        i, depth = stack.pop()
        el = doc.elements[i]
        if depth > 4:
            continue
        if any(d.axis is Axis.LAYOUT and d.prop in ("grid-cols", "display")
               and d.value in ("2", "3", "4", "flex", "grid") for d in el.decls):
            best = max(best, len(el.children))
        stack.extend((c, depth + 1) for c in el.children)
    return best


def classify(doc: Document, idx: int) -> str:
    """The role of the section at ``idx``."""
    el = doc.elements[idx]
    if el.tag == "nav":
        return "nav"
    if el.tag == "footer":
        return "footer"
    text = el.own_text[:1400]

    if _FAQ.search(text):
        return "faq"
    if _PRICING.search(text):
        return "pricing"
    if _TESTIMONIAL.search(text):
        return "testimonials"
    if _HOW.search(text):
        return "how"
    if _LOGOS.search(text):
        return "logos"
    # The h1 test runs *before* the call-to-action and feature tests on purpose.
    # A generated hero almost always says "Everything you need to …" and puts
    # "Get Started Free" under it, which matches both vocabularies — and
    # misreading the hero as a feature or a final CTA gave the page's most
    # important section the tightest rhythm in the rewrite, and broke the
    # canonical sequence at its first band.
    if el.tag == "header" or _has_h1(doc, idx):
        return "hero"
    if _CTA.search(text) and len(text.split()) < 60:
        return "cta"
    if len(_STATS.findall(text)) >= 2 and len(text.split()) < 80:
        return "stats"
    if _FEATURES.search(text):
        return "features"
    if _CONTACT.search(text):
        return "contact"
    # A band that is only a grid of three or more children is a *list*, and a
    # list is not a landing role. Naming it "features" put every catalogue page
    # into the canonical sequence and made two unrelated pages of a studio site
    # read as the same skeleton — the manufactured finding this module's own
    # docstring refuses to produce. Structure is a tie-breaker for a *named*
    # band only.
    if _child_blocks(doc, idx) >= 3 and _FEATURE_HINT.search(text):
        return "features"
    return _structural(doc, idx, text)


# Words a feature grid's own copy reaches for when its heading does not say
# "Features". Narrow on purpose: the fallback below it is ``content``.
_FEATURE_HINT = re.compile(
    r"\bbuilt[- ]in\b|\bpowered\s+by\b|\bintegrat\w+|\bautomat\w+|"
    r"\banalytics\b|\bcollaborat\w+|\bworkflow", _I)


# ------------------------------------------------------- structural fallback
# Everything below runs only after every vocabulary test has declined, so it can
# never take a band away from a landing role. It answers a different question:
# not "which step of the template is this" but "what shape is it", which is the
# question a page that is not a template actually has an answer to.
_MEDIA_TAGS = frozenset({"img", "figure", "picture", "video", "svg", "canvas"})
_FORM_TAGS = frozenset({"form", "input", "textarea", "select"})
_TEXT_TAGS = frozenset({"p", "li", "blockquote", "dd", "dt"})
_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_STATEMENT_WORDS = 60      # above this a lone paragraph is prose, not a line
_STATEMENT_MIN = 8         # below it, a line of text is not a statement
_PROSE_WORDS = 90          # below this a multi-paragraph band is still a note


@dataclass(frozen=True)
class Shape:
    """What a band is made of, counted rather than read."""

    media: int
    texts: int
    forms: int
    links: int
    headings: int
    repeats: int           # equal sibling blocks, the grid/list signal
    words: int


def shape_of(doc: Document, idx: int) -> Shape:
    """Count the parts of the band at ``idx``. Never raises, never recurses."""
    media = texts = forms = links = headings = 0
    stack = list(doc.elements[idx].children)
    seen = 0
    while stack and seen < _SHAPE_LIMIT:
        i = stack.pop()
        seen += 1
        el = doc.elements[i]
        tag = el.renders_tag or el.tag
        if tag in _MEDIA_TAGS:
            media += 1
        elif tag in _TEXT_TAGS:
            texts += 1
        elif tag in _FORM_TAGS:
            forms += 1
        elif tag in ("a", "button"):
            links += 1
        elif tag in _HEADINGS:
            headings += 1
        stack.extend(el.children)
    return Shape(media=media, texts=texts, forms=forms, links=links,
                 headings=headings, repeats=_child_blocks(doc, idx),
                 words=len(doc.elements[idx].own_text.split()))


# A band's subtree is walked once and bounded, for the same reason every other
# walk here is: a page the scanner could not close cleanly must cost a fixed
# amount rather than the whole file.
_SHAPE_LIMIT = 400


def _structural(doc: Document, idx: int, text: str) -> str:
    """A shape name for a band no vocabulary could place, or ``content``."""
    s = shape_of(doc, idx)
    if s.forms:
        return "contact"
    if s.repeats >= 3 and s.media >= s.repeats and s.words < 40 * s.repeats:
        return "gallery"
    if s.repeats >= 3:
        return "list"
    if (s.headings == 0 and s.texts <= 2
            and _STATEMENT_MIN <= s.words <= _STATEMENT_WORDS):
        return "statement"
    if s.texts >= 2 and s.words >= _PROSE_WORDS and s.repeats == 0:
        return "prose"
    return "content"


def _has_h1(doc: Document, idx: int) -> bool:
    stack = list(doc.elements[idx].children)
    seen = 0
    while stack and seen < 60:
        i = stack.pop()
        seen += 1
        if doc.elements[i].tag == "h1":
            return True
        stack.extend(doc.elements[i].children)
    return False


def _collapse(roles: list[str]) -> list[str]:
    out: list[str] = []
    for role in roles:                    # collapse consecutive duplicates
        if not out or out[-1] != role:
            out.append(role)
    return out


def skeleton(doc: Document) -> list[str]:
    """The page's section roles, in document order."""
    return _collapse([classify(doc, i) for i in doc.sections])


# ------------------------------------------------------------------- routes
# A Next.js App Router page is only half a page: the nav and the footer live in
# ``layout.tsx``, the bands in ``page.tsx``, and nothing in either file links
# them. Read separately, the canonical sequence hero → features → testimonials
# → cta → footer never appears in one document — so the tool's single strongest
# structural tell went silent on exactly the projects it was written for.
#
# The pairing is a convention, not an import, so it is resolved the way the
# framework resolves it: every ``layout.*`` from the scan root down to the page's
# own directory wraps that page, outermost first.
# ``.mdx`` is here for the same reason: `page.mdx` is a route in App Router and
# the layout chain above it wraps that page exactly like a `page.tsx`.
_ROUTE_EXTS = frozenset({".jsx", ".tsx", ".js", ".ts", ".mjs", ".mdx"})
_CHILDREN_AT = re.compile(r"\{\s*(?:props\s*\.\s*)?children\s*\}")


def _stem(rel_path: str) -> tuple[str, str, str]:
    folder, name = os.path.split(rel_path.replace("\\", "/"))
    stem, ext = os.path.splitext(name)
    return folder, stem.lower(), ext.lower()


def _split_at_children(doc: Document) -> tuple[list[str], list[str]]:
    """A layout's roles, split into what renders before and after the page."""
    # The *last* match, and only past the first element: `function Layout({
    # children })` is a destructuring pattern, not the hole, and taking the
    # first match put the whole layout after the page — so a nav and a footer
    # arrived at the end of the route and the canonical order read backwards.
    body_at = doc.elements[0].start if doc.elements else 0
    hits = [m.start() for m in _CHILDREN_AT.finditer(doc.text) if m.start() > body_at]
    roles_before: list[str] = []
    roles_after: list[str] = []
    cut = hits[-1] if hits else len(doc.text)
    for i in doc.sections:
        (roles_before if doc.elements[i].start < cut else roles_after).append(
            classify(doc, i))
    return roles_before, roles_after


def routes(docs: list[Document]) -> list[tuple[str, list[str], list[str]]]:
    """``(label, rendered roles, the page's own roles)`` for every route.

    App Router routes are composed from their layout chain; every other markup
    document that reads as a page contributes itself. A ``layout.*`` that wraps
    a page is not also listed on its own — it is chrome, not a page.

    Both role lists are returned because the two measures that read them want
    different things. The canonical sequence is about the *rendered* page, chrome
    included: nav → hero → features → cta → footer is the shape. Page-to-page
    similarity is about what each page chose, and every route in an App Router
    project shares the same layout by construction — comparing the composed
    lists reported a studio site's two unrelated pages as 91% the same page.
    """
    layouts: dict[str, Document] = {}
    pages: list[Document] = []
    for doc in docs:
        if doc.kind != "markup":
            continue
        folder, stem, ext = _stem(doc.rel_path)
        if ext not in _ROUTE_EXTS:
            continue
        if stem == "layout":
            layouts.setdefault(folder, doc)
        elif stem == "page":
            pages.append(doc)

    out: list[tuple[str, list[str], list[str]]] = []
    consumed: set[str] = set()
    for page in sorted(pages, key=lambda d: d.rel_path):
        folder = _stem(page.rel_path)[0]
        chain: list[Document] = []
        while True:
            found = layouts.get(folder)
            if found is not None:
                chain.append(found)
                consumed.add(found.rel_path)
            parent = os.path.dirname(folder)
            if parent == folder:
                break
            folder = parent
        chain.reverse()                     # outermost layout first
        before: list[str] = []
        after: list[str] = []
        for layout in chain:
            head, tail = _split_at_children(layout)
            before += head
            after = tail + after
        own = [classify(page, i) for i in page.sections]
        roles = before + own + after
        if len(roles) >= 2:
            consumed.add(page.rel_path)
            out.append((page.rel_path, _collapse(roles), _collapse(own)))

    for doc in docs:
        if doc.rel_path in consumed or not doc.is_page:
            continue
        own = skeleton(doc)
        out.append((doc.rel_path, own, own))
    out.sort(key=lambda entry: entry[0])
    return out


def naming(docs: list[Document]) -> tuple[int, int]:
    """``(bands named, bands seen)`` across every page in ``docs``.

    The canonical-order measure only works as far as this classifier can name a
    band, and that reach was never written down anywhere. It is not a verdict:
    a page of bands nobody can name is usually a page that is not a template,
    which is the *good* case. It is the width of the lens, and the report says
    it so the reader can discount the structural half when it is narrow.
    """
    named = total = 0
    for doc in docs:
        for i in doc.sections:
            total += 1
            named += classify(doc, i) != "content"
    return named, total


def canonical_run(roles: list[str]) -> int:
    """Longest run of ``roles`` that follows :data:`CANONICAL` order.

    Sections may be missing (a page without pricing is still the template) but
    they may not be *reordered* — a page that puts testimonials before features
    made a choice, and the run breaks there.

    A band this module could not name is *transparent*: it neither extends the
    run nor breaks it. An unrecognized section is not evidence of a choice, it
    is an absence of evidence, and treating it as a break meant one unusual band
    in the middle of a textbook landing page hid the whole sequence.
    """
    best = run = 0
    last = -1
    for role in roles:
        if role not in CANONICAL:
            continue
        pos = CANONICAL.index(role)
        if pos > last:
            run += 1
            last = pos
        else:
            run, last = 1, pos
        best = max(best, run)
    return best
