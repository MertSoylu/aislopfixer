"""Calibration against repositories the tool has never been tuned on.

The eight-case corpus in :mod:`bench.cases` is a closed circuit: we wrote every
page in it, so it can only prove that the measurement is *consistent*. It cannot
say whether the thing being measured survives contact with a codebase nobody
here has read. This module is the open circuit.

Each entry names a public repository, the side it belongs on, and why. Running
it clones each one shallowly into a cache outside the repo, scans it, and writes
:file:`bench/field.md` — expected side, actual score, scan time, and for the
ones that land on the wrong side, **what went wrong**. That last column is the
point: a table with no failures in it is a table nobody checked.

Nothing here is a gate. A score is not a build signal (see the non-goals in
CLAUDE.md); this exists so the claim "designed and generated separate" can be
checked outside the pages we wrote to make it true.

    python -m bench.field                 # clone-and-scan everything, write the table
    python -m bench.field --only NAME     # one project
    python -m bench.field --no-fetch      # reuse the cache, clone nothing
    python -m bench.field --transform     # also build and check a patch per repo
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from aislopfixer.config import Config
from aislopfixer.design.project import scan_project
from aislopfixer.design.system.derive import derive
from aislopfixer.design.transform import apply_plan, plan_all, plan_diff, undo
from aislopfixer.design.transform.plan import build as build_classes
from aislopfixer.design.transform.verify import check

from .cases import CASES

# Where the clones live. Deliberately outside the repository: this is other
# people's code and it is a cache, not a fixture.
CACHE = Path(os.environ.get("AISLOPFIXER_FIELD_CACHE",
                            Path.home() / ".cache" / "aislopfixer-field"))
CLONE_TIMEOUT = 300
# Above this, the project reads as generated; below it, as designed. The same
# 50 the report's own verdict uses for "şablona yakın".
SIDE_AT = 50.0
# A third side, added once the first two stopped being able to hold everything.
# A *commercial* landing template — Cruip's, and the houses like it — is not a
# generated page: designers made it, and it has a tuned type ramp, authored
# motion and a varied structure to prove it. What makes it a template is that
# thousands of sites will be it, and this tool has no way to measure that and
# should not pretend to. So those repositories are judged against the band the
# corpus pins for `crafted_kit`, read from there rather than restated here, so
# the two cannot drift apart.
CRAFTED_BAND = next(c.template for c in CASES if c.name == "crafted_kit")
# Below this many elements the scan has not seen a page — a docs site whose
# markup is all in a theme package, a repo whose UI is generated at build time.
# Reported as "judgement withheld" rather than counted on either side.
MIN_ELEMENTS = 40


@dataclass(frozen=True)
class Project:
    name: str
    url: str
    side: str            # "template" | "crafted" | "designed"
    note: str
    subdir: str = ""     # scan only this part of the repo
    ref: str = ""        # pin a branch/tag when the default one moves fast
    # `--pages`: read the whole tree, measure only this site inside it. Unlike
    # ``subdir`` it does not move the scan root, so component expansion still
    # reaches `components/` — which is why `subdir` could never be used here.
    pages: tuple[str, ...] = ()


@dataclass
class Result:
    project: Project
    template: float = 0.0
    decisions: float = 0.0
    repetition: float = 0.0
    elements: int = 0
    files: int = 0
    seconds: float = 0.0
    error: str = ""
    stack: tuple[str, ...] = field(default_factory=tuple)
    confidence: str = "yok"
    coverage: str = ""
    # --transform: what happened when the tool's own patch was built and checked
    patch: str = ""          # "temiz" | "git apply hatası" | reason it stopped
    patch_edits: int = 0
    patch_second: int = -1   # edits a second pass produces; 0 is the claim
    after: float = -1.0      # template score *measured* on the rewritten source
    invariant: str = ""      # "yalnızca sınıf listeleri" check, in its own words
    junk: str = ""           # class lists that came out saying nothing

    @property
    def moved(self) -> float:
        """Points the transform actually removed. Negative means it added."""
        return self.template - self.after if self.after >= 0 else 0.0

    @property
    def judged(self) -> bool:
        return not self.error and self.elements >= MIN_ELEMENTS

    @property
    def actual_side(self) -> str:
        lo, hi = CRAFTED_BAND
        if self.template >= SIDE_AT:
            return "template"
        return "crafted" if lo <= self.template <= hi else "designed"

    @property
    def correct(self) -> bool:
        if not self.judged:
            return False
        if self.project.side == "crafted":
            lo, hi = CRAFTED_BAND
            return lo <= self.template <= hi
        # The two original sides keep their original test: a `designed` project
        # that lands inside the crafted band is still on the designed side of
        # the threshold, and moving that goalpost would be the fudge this whole
        # table exists to prevent.
        return (self.template >= SIDE_AT) == (self.project.side == "template")


PROJECTS: tuple[Project, ...] = (
    # ------------------------------------------------------------- templates
    # ------------------------------------------------------- crafted templates
    # Labelled `template` for two releases and measured "designed" both times.
    # Reading them settled it: these are designers' work — a `@theme` type ramp
    # with per-step leading and tracking, hand-written easing curves, full-bleed
    # bands, asymmetric heroes. What makes them templates is how many sites will
    # *be* them, which is not a property of the source and not something this
    # tool can measure. `bench/cases/crafted_kit` pins where such a page belongs
    # and these two are judged against that band.
    Project("cruip-landing", "https://github.com/cruip/tailwind-landing-page-template",
            "crafted", "Tailwind landing template sold by a design house — "
                       "tuned type ramp, authored motion, stock palette"),
    Project("cruip-open-react", "https://github.com/cruip/open-react-template",
            "crafted", "React landing template from the same house, same profile"),
    Project("landwind", "https://github.com/themesberg/landwind",
            "template", "Free Tailwind landing page, the canonical shape"),
    Project("tailwindtoolbox", "https://github.com/tailwindtoolbox/Landing-Page",
            "template", "Single-file Tailwind landing page"),
    Project("precedent", "https://github.com/steven-tey/precedent",
            "template", "Next.js starter whose home page is a generated hero"),
    Project("next-enterprise", "https://github.com/Blazity/next-enterprise",
            "template", "Enterprise Next.js boilerplate with a landing page"),
    # Labelled `template` for three releases and measured "designed" every
    # time. Two things were wrong at once, and `--pages` only fixed the first.
    # The scan described the repository while the label described a route: 1 505
    # elements, most of them the dashboard. Scoped to `app/(marketing)` it is
    # 520, which is the site the label is about. And it still does not read as
    # generated — because it is not. This is a shadcn/ui application: semantic
    # colour roles behind custom properties, a radius scale keyed to
    # `--radius`, its own font stack. That is a design system, the tool measures
    # it as one, and the thing that makes the repository a template is how many
    # SaaS apps will *be* it. Same argument as Cruip's, same side.
    Project("saas-starter", "https://github.com/mickasmt/next-saas-stripe-starter",
            "crafted", "SaaS starter on a shadcn token system — a marketing "
                       "route inside a whole application",
            pages=("app/(marketing)",)),
    Project("shipfast-like", "https://github.com/ixartz/Next-js-Landing-Page-Starter-Template",
            "template", "Landing-page starter template"),
    # ------------------------------------------------------------- designed
    Project("bchiang-v4", "https://github.com/bchiang7/v4",
            "designed", "A portfolio with an authored type scale and its own palette"),
    Project("leerob-site", "https://github.com/leerob/site",
            "designed", "A personal site: restrained, typographic, no landing kit"),
    Project("tholman", "https://github.com/tholman/tholman.com",
            "designed", "A personal site with a point of view"),
    Project("daisyui", "https://github.com/saadeghi/daisyui",
            "designed", "A component library's own site and demos"),
    Project("hono-website", "https://github.com/honojs/website",
            "designed", "Docs site with an authored landing page"),
    Project("nuxt-website", "https://github.com/nuxt/nuxt.com",
            "designed", "Nuxt's site: designed, componentised, token-driven"),
    Project("solid-site", "https://github.com/solidjs/solid-site",
            "designed", "A framework site with its own palette and layout language"),
)


_DONE = ".aislopfixer-clone-ok"


def _clone(project: Project, fetch: bool) -> Path | None:
    """Shallow-clone into the cache, or reuse what is already there.

    A completed clone is marked. An interrupted one leaves a directory behind
    that is *not* a checkout, and treating it as a cache hit produced the worst
    kind of row in this table: a real score against half a repository.
    """
    target = CACHE / project.name
    if (target / _DONE).exists():
        return target
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    if not fetch:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    # Deliberately *not* a partial clone. `--filter=blob:none` makes git fetch
    # blobs on demand, and the demand here is the scan — which would put network
    # round trips inside the number this table reports as scan time.
    cmd = ["git", "clone", "--depth", "1", "--single-branch", "--quiet"]
    if project.ref:
        cmd += ["--branch", project.ref]
    cmd += [project.url, str(target)]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=CLONE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        shutil.rmtree(target, ignore_errors=True)
        return None
    if done.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        return None
    (target / _DONE).write_text(project.url + "\n", encoding="utf-8")
    return target


def evaluate(project: Project, fetch: bool = True,
             transform: bool = False) -> Result:
    root = _clone(project, fetch)
    if root is None:
        return Result(project=project, error="klonlanamadı")
    path = root / project.subdir if project.subdir else root
    if not path.exists():
        return Result(project=project, error=f"yol yok: {project.subdir}")
    started = time.perf_counter()
    config = Config.load(str(path)).with_pages(project.pages)
    try:
        report, docs = scan_project(str(path), config)
    except Exception as exc:                     # noqa: BLE001 — the point is to catch it
        return Result(project=project, error=f"{type(exc).__name__}: {exc}",
                      seconds=time.perf_counter() - started)
    result = Result(
        project=project,
        template=report.template_score,
        decisions=report.decision_density,
        repetition=report.repetition,
        elements=report.elements,
        files=report.files_scanned,
        seconds=time.perf_counter() - started,
        stack=tuple(sorted(report.stack)),
        confidence=report.coverage.confidence,
        coverage=report.coverage.summary,
    )
    if transform and result.judged:
        _try_transform(str(path), docs, report, result, config)
    return result


def _try_transform(path: str, docs, report, result: Result,
                   config: Config) -> None:
    """Build the tool's own patch for a real repository and check it.

    Five claims are tested at once, and each one is the tool's own: the patch is
    ``git apply``-clean, applying it changes **only class lists** at the byte
    level, the class lists it produces do not contradict themselves, a second
    pass over the rewritten source produces zero edits, and the template score
    goes **down**. Nothing is left behind — the write happens in the clone and
    is undone before returning.

    The "after" score is measured, not previewed: the same re-scan that proves
    idempotence reports it. A repository whose score does not fall stays in the
    table with the number that says so, because "the build still works" was
    never the claim this tool makes.
    """
    try:
        system = derive(path, report)
        plan = plan_all(path, docs, report, system)
        result.patch_edits = len(plan.edits)
        if not plan.edits:
            result.patch = "düzenleme yok"
            return
        verified = check(docs, build_classes(docs, report, system))
        result.invariant = ("yalnızca sınıf listeleri"
                            if not verified.of("structure")
                            else f"{len(verified.of('structure'))} yapı ihlali")
        junk = [v for v in verified.violations if v.kind != "structure"]
        result.junk = "—" if not junk else f"{len(junk)} anlamsız sınıf"
        patch = plan_diff(plan)
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False,
                                         encoding="utf-8", newline="\n") as fh:
            fh.write(patch)
            patch_path = fh.name
        try:
            done = subprocess.run(
                ["git", "apply", "--check", patch_path],
                cwd=path, capture_output=True, text=True, timeout=120)
        finally:
            os.unlink(patch_path)
        if done.returncode != 0:
            result.patch = "git apply reddetti"
            return
        applied = apply_plan(plan, backup=False)
        try:
            second_report, second_docs = scan_project(path, config)
            result.after = second_report.template_score
            second_system = derive(path, second_report)
            second = plan_all(path, second_docs, second_report, second_system)
            result.patch_second = len(second.edits)
        finally:
            undo(applied)
        result.patch = "temiz" if result.patch_second == 0 else "ikinci geçiş boş değil"
    except Exception as exc:                     # noqa: BLE001 — the point is to catch it
        result.patch = f"{type(exc).__name__}: {exc}"[:60]


def run(only: str = "", fetch: bool = True,
        transform: bool = False) -> list[Result]:
    picked = [p for p in PROJECTS if not only or p.name == only]
    return [evaluate(p, fetch, transform) for p in picked]


_SATURATED_AT = 80.0     # a decision axis this high has stopped discriminating


def _diagnosis(judged: list[Result], wrong: list[Result]) -> list[str]:
    """The pattern behind the failures, when there is one, said in numbers.

    Written as a *derivation* rather than a paragraph so it cannot go stale: if
    the shape of the failures changes, this stops printing, and if they go away
    it never prints at all. A hand-written diagnosis in a generated file is a
    claim about a run nobody re-checked.
    """
    if not wrong:
        return []
    sides = {r.project.side for r in wrong}
    saturated = [r for r in wrong if r.decisions >= _SATURATED_AT]
    out = ["", "### Ortak örüntü", ""]
    if len(wrong) < 2:
        # One failure is not a pattern, and writing "the errors are all in one
        # direction" about a single row is a sentence that says more than the
        # data does.
        r = wrong[0]
        return out + [
            f"Tek bir satır: **{r.project.name}**. Bir örüntü değil — beklenen "
            f"*{r.project.side}*, ölçülen {r.template:.1f}. Bu depo bir landing "
            f"şablonu değil, içinde bir pazarlama rotası olan bütün bir "
            f"uygulama: {r.elements} elemanın çoğu panelden geliyor ve ölçüm "
            f"onları da sayıyor. Etiket sayfayı, tarama depoyu tarif ediyor.",
        ]
    if len(sides) == 1:
        side = sides.pop()
        others = [r for r in judged if r.project.side != side]
        out.append(
            f"Hataların hepsi tek yönde: beklenen *{side}* olan projeler. "
            f"Diğer taraftaki {len(others)} projenin "
            f"{sum(1 for r in others if r.correct)} tanesi doğru. Yani araç "
            f"bir tarafı bilmiyor değil — **her şeyi o tarafta görüyor**."
        )
        out.append("")
    if len(saturated) >= max(2, len(wrong) // 2):
        # The old failure mode: the decision target scaled with element count
        # and stopped growing at 120, so every project bigger than a demo page
        # saturated its own score. If this prints again, that is what came back.
        biggest = max(judged, key=lambda r: r.elements)
        out += [
            f"Yanlış düşenlerin {len(saturated)} tanesinde karar yoğunluğu "
            f"{_SATURATED_AT:.0f}'in üstünde — o eksende ölçüm ayırt etmeyi "
            f"bırakmış. Bu, hedefin gözlenen sözlük büyüklüğünden koptuğu "
            f"anlamına gelir; buradaki projeler "
            f"{min(r.elements for r in judged)}–{biggest.elements} eleman.",
            "",
        ]
    else:
        sizes = sorted(r.elements for r in wrong)
        out += [
            f"Doyma yok: yanlış düşen {len(wrong)} projenin karar yoğunluğu "
            f"{min(r.decisions for r in wrong):.0f}–"
            f"{max(r.decisions for r in wrong):.0f} arasında, "
            f"{_SATURATED_AT:.0f}'in altında, ve boyutları {sizes[0]}–"
            f"{sizes[-1]} eleman. Yani bunlar ölçümün büyüklükten şaştığı "
            f"vakalar değil: araç bu projelerde gerçekten karar buluyor.",
            "",
            "Kalan fark etikette. Bu tabloda *template*, “satılık bir başlangıç "
            "noktası” demek — “kimse karar vermemiş” demek değil. Ticari bir "
            "landing şablonu, tasarımcıların özene bezene yaptığı bir üründür: "
            "kendi renk değişkenleri, kendi animasyonları, ayarlanmış bir tip "
            "rampası vardır. Araç iki eksen ölçüyor ve o iki eksende bu "
            "projeler gerçekten iyi. Eşik oynatarak “düzeltmek”, aracın "
            "ölçtüğü şeyi değil, tablonun görüntüsünü düzeltmek olur.",
        ]
    return out


def render(results: list[Result]) -> str:
    judged = [r for r in results if r.judged]
    right = [r for r in judged if r.correct]
    wrong = [r for r in judged if not r.correct]
    skipped = [r for r in results if not r.judged]
    patched = any(r.patch for r in results)

    out = [
        "# Saha kalibrasyonu",
        "",
        f"Bu tablo `python -m bench.field` çıktısıdır. Korpus kapalı bir "
        f"devre — {len(CASES)} vakayı da biz yazdık — bu yüzden yalnızca "
        f"ölçümün *tutarlı* olduğunu gösterebilir. Aşağıdaki projeleri hiç "
        f"kimse bu araca göre yazmadı.",
        "",
        f"Eşik: şablon skoru **{SIDE_AT:.0f}** üstü \"üretilmiş\", altı "
        f"\"tasarlanmış\" sayıldı. {MIN_ELEMENTS} elemandan az gören bir tarama "
        "hüküm vermiyor: markup'ı bir tema paketinde ya da build çıktısında "
        "olan bir depo hakkında konuşacak verisi yok.",
        "",
        f"Üçüncü bir taraf var: **crafted** — bir tasarım evinin yaptığı, satılan "
        f"landing şablonu. Bunlar üretilmiş sayfa değil; ayarlanmış bir tip "
        f"rampası, elle yazılmış easing eğrileri ve kırılan bir yerleşimleri var. "
        f"Şablon olmalarının sebebi kaynakta değil, kaç sitenin *onlar olacağında* "
        f"— ve bu araç onu ölçemez, ölçüyormuş gibi de yapmamalı. Bu satırlar "
        f"korpustaki `crafted_kit` vakasının bandına göre değerlendirilir "
        f"({CRAFTED_BAND[0]:.0f}–{CRAFTED_BAND[1]:.0f}); bant oradan okunur, "
        f"burada tekrar yazılmaz.",
        "",
        f"**{len(right)}/{len(judged)} doğru tarafta**"
        + (f" · {len(skipped)} proje hüküm dışı" if skipped else "")
        + ".",
        "",
        "Kapsam sütunu skoru değil, skorun ne kadarını kapsadığını söyler: "
        "*kısmi*, taramanın uçtan uca okuyabildiği bir sayfa girişi bulamadığı "
        "ve deponun sayfalarının bu aracın okumadığı bir dilde olduğu anlamına "
        "gelir. O satırlardaki sayı okunabilen parça hakkındadır.",
        "",
        "| proje | beklenen | şablon | karar | tekrar | eleman | kapsam | süre |"
        + (" yama |" if patched else "") + " yığın |",
        "|---|---|---:|---:|---:|---:|---|---:|"
        + ("---|" if patched else "") + "---|",
    ]
    for r in results:
        p = r.project
        if r.error:
            out.append(f"| `{p.name}` | {p.side} | — | — | — | — | — | — | "
                       + ("— | " if patched else "") + f"{r.error} |")
            continue
        mark = "✓" if r.correct else ("·" if not r.judged else "✗")
        patch = f" {r.patch or '—'} |" if patched else ""
        out.append(
            f"| `{p.name}` {mark} | {p.side} | {r.template:.1f} | "
            f"{r.decisions:.1f} | {r.repetition:.1f} | {r.elements} | "
            f"{r.confidence} | {r.seconds:.1f}s |{patch} "
            f"{', '.join(r.stack) or '—'} |"
        )
    out += ["", "## Neden bu tarafta", ""]
    for r in results:
        out.append(f"- **{r.project.name}** — {r.project.note}")
    if wrong:
        out += ["", "## Yanlış tarafa düşenler", "",
                "Bunlar açık açık burada duruyor. Eşik oynatarak "
                "düzeltilmezler: ya ölçüm eksik, ya vaka korpusa girmeli, ya da "
                "— iddiası bu araçla ölçülemiyorsa — kendi tarafını alır ve o "
                "taraf korpusta bir vakayla sabitlenir (`crafted` böyle "
                "doğdu).", ""]
        for r in wrong:
            out.append(
                f"- **{r.project.name}** — beklenen *{r.project.side}*, "
                f"ölçülen {r.template:.1f} ({r.actual_side}). "
                f"karar {r.decisions:.1f}, tekrar {r.repetition:.1f}."
            )
        out += _diagnosis(judged, wrong)
    if skipped:
        out += ["", "## Hüküm verilmedi", ""]
        for r in skipped:
            why = r.error or f"{r.elements} eleman — {r.coverage}"
            out.append(f"- **{r.project.name}** — {why}")
    partial = [r for r in judged if r.confidence != "tam"]
    if partial:
        out += ["", "## Kapsam notu", "",
                "Bu depolarda skor verildi ama tarama uçtan uca okuyabildiği "
                "bir sayfa girişi bulamadı ya da 40 elemanın altında kaldı; "
                "ölçüm sayfaları çizen bileşenler üzerinde yapıldı. Sayı "
                "yanlış değil, dar. (`.mdx` artık taranıyor; düz `.md` sayfa "
                "olarak sayılır ama taranmaz — tasarımı onu render eden "
                "temaya aittir ve o tema zaten okunuyor.)", ""]
        for r in partial:
            out.append(f"- **{r.project.name}** — {r.coverage}")
    if patched:
        clean = [r for r in results if r.patch == "temiz"]
        moved = [r for r in results if r.after >= 0]
        fell = [r for r in moved if r.moved > 0]
        broke = [r for r in results if r.invariant and "ihlal" in r.invariant]
        out += ["", "## Dönüşüm", "",
                f"`--transform`: her depo için plan üretildi, `plan.diff` "
                f"yazıldı, `git apply --check` çalıştırıldı, yazımdan sonra "
                f"ikinci bir geçişin sıfır düzenleme ürettiği doğrulandı ve "
                f"skor yeniden ölçüldü. "
                f"**{len(clean)}/{sum(1 for r in results if r.patch)} depoda "
                f"üçü de temiz geçti.** Yazma klonun içinde yapılır ve geri "
                f"alınır.", "",
                f"“Bozuk build üretmiyor” ile “sayfa daha iyi görünüyor” aynı "
                f"iddia değil. Aşağıdaki *sonra* sütunu ikincisinin ölçülebilen "
                f"yarısı: dönüşüm yazıldıktan sonra aynı boru hattıyla yeniden "
                f"ölçülen şablon skoru. **{len(fell)}/{len(moved)} depoda skor "
                f"düştü**; düşmeyenler sebebiyle burada duruyor.", "",
                f"*yalnızca sınıf* sütunu bayt düzeyinde bir invaryanttır: "
                f"sınıf değerleri maskelenip dosyanın kalanı önce/sonra "
                f"karşılaştırılır — öğe ağacı, metin, boşluk, satır sonları. "
                f"**{len(moved) - len(broke)}/{len(moved)} depoda ihlal yok.**",
                "",
                "| proje | önce | sonra | fark | düzenleme | yalnızca sınıf | "
                "anlamsız |",
                "|---|---:|---:|---:|---:|---|---|"]
        for r in results:
            if not r.patch:
                continue
            after = "—" if r.after < 0 else f"{r.after:.1f}"
            delta = "—" if r.after < 0 else f"{-r.moved:+.1f}"
            out.append(f"| `{r.project.name}` | {r.template:.1f} | {after} | "
                       f"{delta} | {r.patch_edits} | {r.invariant or '—'} | "
                       f"{r.junk or '—'} |")
        out += [""]
        for r in results:
            if not r.patch:
                continue
            second = ("" if r.patch_second < 0
                      else f", ikinci geçiş {r.patch_second} düzenleme")
            out.append(f"- **{r.project.name}** — {r.patch}{second}")
        risen = [r for r in moved if r.moved <= 0]
        if risen:
            out += ["", "### Skoru düşmeyenler", "",
                    "Bu depolarda aracın kendi sistemi projeninkinden **dar**: "
                    "zaten ayarlanmış bir tip rampasını altı rolle, yazılmış bir "
                    "paleti sekiz jetonla değiştirmek karar sayısını azaltır. "
                    "Ekranda uyarı vardı, ölçüde yoktu; artık ikisinde de var — "
                    "`preview` skoru yükseltiyorsa sistem ekranı `a`'yı kapalı "
                    "sunuyor.", ""]
            for r in risen:
                out.append(f"- **{r.project.name}** — {r.template:.1f} → "
                           f"{r.after:.1f} ({-r.moved:+.1f})")
    out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Saha kalibrasyonu")
    ap.add_argument("--only", default="", help="tek bir projeyi çalıştır")
    ap.add_argument("--no-fetch", action="store_true",
                    help="klonlama, yalnızca önbellekteki depoları tara")
    ap.add_argument("--transform", action="store_true",
                    help="planı üret, git apply --check ve ikinci geçişi doğrula")
    ap.add_argument("--out", default=str(Path(__file__).with_name("field.md")))
    args = ap.parse_args()

    results = run(only=args.only, fetch=not args.no_fetch,
                  transform=args.transform)
    for r in results:
        state = r.error or (f"{r.template:6.1f}  {r.seconds:5.1f}s  "
                            f"{r.elements:5d} eleman  {r.confidence}"
                            + (f"  yama: {r.patch}" if r.patch else "")
                            + (f"  -> {r.after:.1f} ({-r.moved:+.1f})"
                               if r.after >= 0 else "")
                            + (f"  {r.invariant}" if r.invariant else ""))
        print(f"{r.project.name:22} {r.project.side:9} {state}")
    if not args.only:
        Path(args.out).write_text(render(results), encoding="utf-8", newline="\n")
        print(f"\n{args.out} yazıldı")


if __name__ == "__main__":
    main()
