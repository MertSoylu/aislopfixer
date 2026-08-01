"""Repetition: how much of the project is a copy of itself.

Headline axis 2. The care needed here is in *what kind* of repetition counts.
Three identical feature cards side by side are a list, not slop — a design
system is supposed to repeat. What gives a generated site away is repetition
that crosses a boundary it has no reason to cross:

* one block shape used for features *and* pricing *and* testimonials;
* two different pages with the same section order;
* card copy whose word counts are all within a hair of each other, because it
  was produced to fill a slot rather than to say something.

So a cluster is only reported when it spans multiple parents or multiple files,
and the copy-shape measure is a coefficient of variation, which is zero exactly
when every card was written to the same length.
"""

from __future__ import annotations

import difflib
from collections import defaultdict

from ..models import (Axis, Document, Element, Observation, PagePair,
                      RepetitionCluster)
from .sections import CANONICAL, ROLE_LABEL, canonical_run, routes
from .util import cap_evidence, coefficient_of_variation, evidence_for

_SIG_DEPTH = 3          # how deep a block signature reaches
_MIN_NODES = 4          # smaller subtrees are too generic to cluster on
_MAX_CHILDREN = 40      # above this an element is a list container, not a block
_MIN_CLUSTER = 3        # copies before a shape is a template
_MIN_PAGES = 2
_SIMILAR_AT = 0.7       # skeleton similarity that counts as "the same page"
# Pairwise skeleton comparison is quadratic. Two hundred pages is 19,900
# comparisons, which is fast; two thousand is two million, which is not. The cut
# is *reported* — a silent truncation reads as "I looked at everything". Which
# two hundred is decided by path, never by walk order, so scanning the same
# repository twice compares the same pages.
_MAX_PAGES = 200
_SHOWN = 8              # evidence entries kept; matches util.cap_evidence


def _signature(doc: Document, idx: int, depth: int = 0,
               memo: dict | None = None) -> str:
    """Structural signature of a subtree: tags and *which* axes they style.

    Values are deliberately excluded. Two cards that differ only in accent
    colour are the same shape, and the whole point is to see the shape.

    ``memo`` keys on ``(idx, depth)`` because the cut at :data:`_SIG_DEPTH`
    makes the same node's signature depth-dependent. Without it every node was
    re-signed once per ancestor that reached it — 208 000 calls on
    ``nuxt-website``, for 96 000 rendered elements.
    """
    key = (idx, depth)
    if memo is not None and key in memo:
        return memo[key]
    el = doc.elements[idx]
    props = sorted({f"{d.axis.value}:{d.prop}" for d in el.decls if not d.variant})
    head = f"{el.tag}[{'|'.join(props)}]"
    if depth >= _SIG_DEPTH or not el.children:
        out = head
    else:
        inner = ",".join(_signature(doc, c, depth + 1, memo)
                         for c in el.children[:6])
        out = f"{head}({inner})"
    if memo is not None:
        memo[key] = out
    return out


def _node_count(doc: Document, idx: int, depth: int = 0,
                memo: dict | None = None) -> int:
    if depth >= _SIG_DEPTH:
        return 1
    key = (idx, depth)
    if memo is not None and key in memo:
        return memo[key]
    out = 1 + sum(_node_count(doc, c, depth + 1, memo)
                  for c in doc.elements[idx].children)
    if memo is not None:
        memo[key] = out
    return out


def _subtree_text(doc: Document, idx: int, depth: int = 0) -> list[str]:
    el = doc.elements[idx]
    out = [el.own_text] if el.own_text else []
    if depth < _SIG_DEPTH:
        for c in el.children:
            out.extend(_subtree_text(doc, c, depth + 1))
    return out


def _label(doc: Document, idx: int) -> str:
    """A human name for a cluster: its first heading, else its tag."""
    stack = [idx]
    seen = 0
    while stack and seen < 40:
        i = stack.pop(0)
        seen += 1
        el = doc.elements[i]
        if el.tag in ("h1", "h2", "h3", "h4") and el.own_text:
            return el.own_text[:40]
        stack.extend(el.children)
    return f"<{doc.elements[idx].tag}>"


def _section_of(doc: Document) -> dict[int, int]:
    """``{element: the *nearest* band it lives in}``, ``-1`` when outside one.

    Nearest, not outermost: a page wrapped in ``<main>`` is one section from the
    outside in, and mapping everything to it would put every block in the same
    band and silence the measure entirely. Parents always precede their children
    in document order, so one forward pass resolves the whole tree.
    """
    marks = set(doc.sections)
    out: dict[int, int] = {}
    for i, el in enumerate(doc.elements):
        out[i] = i if i in marks else out.get(el.parent, -1)
    return out


def clusters(docs: list[Document]) -> list[RepetitionCluster]:
    """Block shapes used three or more times across *sections* or files.

    The boundary is the section, not the parent element. Four catalogue entries
    in one grid have four different parent wrappers and are still a list — the
    loop that produced them is the correct way to build a list. What gives the
    template away is the same shape serving as a feature, a price and a quote,
    and that is a crossing between bands.
    """
    groups: dict[str, list[tuple[Document, int]]] = defaultdict(list)
    bands: dict[str, dict[int, int]] = {}
    for doc in docs:
        bands[doc.rel_path] = _section_of(doc)
        # One memo per document: both walks are pure over the element tree, and
        # a rendered page of four thousand virtual elements re-signs the same
        # subtree once per ancestor without one.
        sig_memo: dict = {}
        count_memo: dict = {}
        for i, el in enumerate(doc.elements):
            if el.tag in ("html", "head", "body", "script", "style"):
                continue
            # Pre-filter before signing: signing a subtree is the expensive
            # step, and neither a leaf pair nor a forty-child list container is
            # ever the block shape this metric is looking for.
            if not 2 <= len(el.children) <= _MAX_CHILDREN:
                continue
            if _node_count(doc, i, 0, count_memo) < _MIN_NODES:
                continue
            groups[_signature(doc, i, 0, sig_memo)].append((doc, i))

    out: list[RepetitionCluster] = []
    for sig, members in groups.items():
        if len(members) < _MIN_CLUSTER:
            continue
        sections = {(d.rel_path, bands[d.rel_path].get(i, -1)) for d, i in members}
        files = sorted({d.rel_path for d, _ in members})
        if len(sections) < 2 and len(files) < 2:
            continue          # one band's worth of siblings — a list
        words = [
            sum(len(t.split()) for t in _subtree_text(d, i))
            for d, i in members
        ]
        out.append(RepetitionCluster(
            signature=sig,
            label=_label(*members[0]),
            count=len(members),
            files=files,
            # Evidence is built for the members that will be shown, not for all
            # of them: a cluster of four hundred copies produced four hundred
            # source snippets to display eight.
            evidence=[evidence_for(d, d.elements[i])
                      for d, i in members[:_SHOWN]],
            text_variance=round(coefficient_of_variation([float(w) for w in words]), 3),
            words=sum(words),
        ))
    out.sort(key=lambda c: -c.count)
    return out


def _comparable(docs: list[Document]) -> list[tuple[str, list[str]]]:
    """Every route with enough bands to compare, sorted by path.

    Sorted, not walk-ordered: which pages survive the :data:`_MAX_PAGES` cut has
    to be a property of the repository, not of which read finished first.

    Only bands with a *canonical* role take part. The claim this feeds is
    "different pages follow the same hero → features → pricing → cta
    sequence", and a band named by its shape rather than by its place in that
    sequence has nothing to say about it — which is exactly how
    ``sections.canonical_run`` already treats it. A studio site whose three
    pages are each hero → statement → list shares a house style, not a
    template, and grading that as 86% the same page is the manufactured
    finding this module exists to avoid.
    """
    out: list[tuple[str, list[str]]] = []
    for label, _roles, own in routes(docs):
        canonical = [r for r in own if r in CANONICAL]
        if len(canonical) >= 3:
            out.append((label, canonical))
    return sorted(out, key=lambda pair: pair[0])


def page_count(docs: list[Document]) -> int:
    """How many rendered routes are comparable pages at all."""
    return len(_comparable(docs))


def page_pairs(docs: list[Document], limit: int = _MAX_PAGES) -> list[PagePair]:
    """Pairwise skeleton similarity between every two pages, up to ``limit``."""
    pages = _comparable(docs)[:limit]
    out: list[PagePair] = []
    for i in range(len(pages)):
        for j in range(i + 1, len(pages)):
            ratio = difflib.SequenceMatcher(
                None, pages[i][1], pages[j][1]).ratio()
            out.append(PagePair(pages[i][0], pages[j][0], round(ratio, 3)))
    out.sort(key=lambda p: (-p.similarity, p.a, p.b))
    return out


def analyze(docs: list[Document]) -> tuple[list[Observation], float,
                                           list[RepetitionCluster], list[PagePair]]:
    """Repetition observations, the headline repetition score, and its data."""
    out: list[Observation] = []
    shares: list[float] = []

    found = clusters(docs)
    if found:
        top = found[0]
        blocks = sum(c.count for c in found)
        shares.append(min(1.0, top.count / 8.0))
        out.append(Observation(
            axis=Axis.LAYOUT,
            id="repeat.block_shape",
            title="Tek blok şekli her yerde",
            detail=(
                f"“{top.label}” ile aynı yapıya sahip {top.count} blok var, "
                f"{len(top.files)} dosyaya yayılmış. Aynı ikon+başlık+iki "
                f"satır açıklama iskeleti özellik, fiyat ve yorum bölümlerinde "
                f"tekrarlandığında sayfa tek bir bileşenin kopyalarına dönüşür; "
                f"okuyucu bölümler arasında fark göremez."
            ),
            severity=round(min(1.0, top.count / 10.0 + 0.3), 3),
            stat=f"{top.count} kopya · {len(found)} küme · {blocks} blok",
            evidence=top.evidence,
            prescription=(
                "Her bölüme kendi blok şeklini ver: özellikler sola hizalı "
                "metin bloğu, fiyatlar tablo, yorumlar geniş alıntı. Aynı "
                "kartı üç kez kullanma."
            ),
        ))

        # A cluster whose blocks carry no readable text (a component whose copy
        # arrives through props) has a variance of zero for want of anything to
        # measure. Reporting that as "identical copy" would be a number about
        # the parser, not about the page.
        flat = [c for c in found
                if c.count >= 3 and c.words and c.text_variance < 0.18]
        if flat:
            worst = min(flat, key=lambda c: c.text_variance)
            shares.append(1.0 - worst.text_variance / 0.18)
            out.append(Observation(
                axis=Axis.COPY,
                id="repeat.copy_shape",
                title="Metinler aynı kalıba dökülmüş",
                detail=(
                    f"“{worst.label}” kümesindeki {worst.count} bloğun metin "
                    f"uzunlukları neredeyse birebir aynı (değişkenlik "
                    f"%{worst.text_variance * 100:.0f}). İnsan yazısında "
                    f"uzunluk söylenecek şeye göre değişir; sabit uzunluk, "
                    f"metnin bir yeri doldurmak için üretildiğini gösterir."
                ),
                severity=round(min(1.0, 1.0 - worst.text_variance / 0.18), 3),
                stat=f"%{worst.text_variance * 100:.0f} değişkenlik",
                evidence=worst.evidence,
                prescription=(
                    "Her bloğa söyleyecek kadar yer ver: bazıları bir cümle, "
                    "bazıları bir paragraf olsun. Eşit uzunluk hedefleme."
                ),
            ))

    pairs = page_pairs(docs)
    total_pages = page_count(docs)
    cut = (f" Karşılaştırma ilk {_MAX_PAGES} sayfayla sınırlandı "
           f"({total_pages} sayfa var)." if total_pages > _MAX_PAGES else "")
    twins = [p for p in pairs if p.similarity >= _SIMILAR_AT]
    if len(pairs) >= 1 and twins:
        shares.append(max(p.similarity for p in twins))
        worst = twins[0]
        out.append(Observation(
            axis=Axis.LAYOUT,
            id="repeat.page_skeleton",
            title="Sayfalar aynı iskeleti paylaşıyor",
            detail=(
                f"{worst.a} ve {worst.b} bölüm sırası olarak "
                f"%{worst.similarity * 100:.0f} aynı"
                + (f" ({len(twins)} sayfa çifti bu eşiğin üstünde)."
                   if len(twins) > 1 else ".")
                + " Farklı sayfaların aynı hero→özellik→fiyat→çağrı dizisini "
                  "izlemesi, sayfaların içeriğinden değil şablondan doğduğunu "
                  "gösterir."
                + cut
            ),
            severity=round(worst.similarity, 3),
            stat=f"%{worst.similarity * 100:.0f} benzer",
            evidence=[],
            prescription=(
                "Her sayfayı kendi işine göre kur: bir ürün sayfası ile bir "
                "hakkımızda sayfasının aynı bölüm dizisine ihtiyacı yok."
            ),
        ))

    for label, roles, _own in routes(docs):
        run = canonical_run(roles)
        if run >= 5:
            shares.append(min(1.0, run / 8.0))
            named = " → ".join(ROLE_LABEL.get(r, r) for r in roles)
            out.append(Observation(
                axis=Axis.LAYOUT,
                id="repeat.canonical_order",
                title="Bölüm sırası şablonun kendisi",
                detail=(
                    f"{label}: {named}. Bu dizinin {run} bölümü, "
                    f"üretilmiş landing page'lerin kanonik sırasıyla birebir "
                    f"örtüşüyor. Sıra içeriğin gerektirdiği için değil, "
                    f"şablon böyle olduğu için bu."
                ),
                severity=round(min(1.0, run / 8.0), 3),
                stat=f"{run} bölüm sırayla",
                evidence=[],
                prescription=(
                    "Sayfayı anlatacağın hikâyeye göre sırala. Ürünün en güçlü "
                    "kanıtı neyse onu öne al; şablonun sırasını izleme."
                ),
            ))

    repetition = 100.0 * (sum(shares) / len(shares)) if shares else 0.0
    return out, round(repetition, 1), found, pairs
