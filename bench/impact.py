"""Does the tool's own forecast match what its transform actually does?

Two different numbers are checked here, because they answer two different
questions and only one of them is a promise.

* **The transform's own forecast** (:func:`~aislopfixer.design.transform.preview`)
  — what the score will be after ``a``. It is not a model: the plan is built,
  the edits are applied *in memory*, and the result goes back through the same
  measurement. It must match the real run exactly, and if it ever does not,
  something in the pipeline is reading from disk when it should be reading from
  the plan.
* **The ordering model** (:func:`~aislopfixer.design.analyze.projected_score`)
  — what closing *one* observation is worth, used to sort the "what do I fix
  first" list. It answers a human-sized question and deliberately assumes a
  human-sized outcome (:data:`~analyze.DESIGNED_AT`), so it does not track the
  transform, which goes further. The gap is measured here and written into the
  table rather than tuned away.

    python -m bench.impact

The corpus is copied to a scratch directory first. Nothing under ``bench/cases``
is ever written to — a calibration run that mutates its own fixtures measures
the run before it.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aislopfixer.design.analyze import (DESIGNED_AT, SELF_FIXABLE, priorities,
                                        projected_all)
from aislopfixer.design.project import scan_project
from aislopfixer.design.system.derive import derive
from aislopfixer.design.transform import preview
from aislopfixer.design.transform import run as transform_run

from .cases import CASES

# The forecast is the transform run in memory, so anything above rounding is a
# defect, not a calibration drift.
TOLERANCE = 0.1


@dataclass
class Impact:
    name: str
    before: float
    forecast: float          # transform.preview — the number the tool shows
    after: float             # the real run
    ordering: float          # analyze.projected_all over the ⚡ observations
    closed: tuple[str, ...]

    @property
    def actual(self) -> float:
        return round(self.before - self.after, 1)

    @property
    def predicted(self) -> float:
        return round(self.before - self.forecast, 1)

    @property
    def error(self) -> float:
        return round(abs(self.forecast - self.after), 1)

    @property
    def ordering_drop(self) -> float:
        return round(max(0.0, self.before - self.ordering), 1)

    @property
    def ok(self) -> bool:
        return self.error <= TOLERANCE

    @property
    def helped(self) -> bool:
        """Did the transform actually move the score down at all?"""
        return self.after < self.before


def measure(name: str, source: str) -> Impact | None:
    """Forecast the transform, then run it, then compare."""
    with tempfile.TemporaryDirectory(prefix="aislopfixer-impact-") as tmp:
        root = Path(tmp) / name
        shutil.copytree(source, root)
        before, docs = scan_project(str(root))
        if not before.measured:
            return None
        system = derive(str(root), before)
        forecast = preview(str(root), docs, before, system)
        mine = [p.observation for p in priorities(before, limit=0)
                if p.self_fixable]
        transform_run(str(root), docs, before, system)
        after, _ = scan_project(str(root))
        return Impact(
            name=name,
            before=before.template_score,
            forecast=forecast.template_score,
            after=after.template_score,
            ordering=projected_all(before, mine) if mine else before.template_score,
            closed=tuple(o.id for o in mine),
        )


def run() -> list[Impact]:
    out: list[Impact] = []
    for case in CASES:
        found = measure(case.name, case.path)
        if found is not None:
            out.append(found)
    return out


def render(results: list[Impact]) -> str:
    """The table, written the way the field table is: failures included."""
    exact = [r for r in results if r.ok]
    worse = [r for r in results if not r.helped]
    out = [
        "# Etki kalibrasyonu",
        "",
        "Bu tablo `python -m bench.impact` çıktısıdır. İki ayrı sayı "
        "doğrulanıyor, çünkü iki ayrı soruya cevap veriyorlar.",
        "",
        "**1. Dönüşümün kendi tahmini** — `a`'ya basıldığında skorun ne olacağı. "
        "Bu bir model değil: plan kurulur, düzenlemeler **bellekte** uygulanır ve "
        "sonuç aynı ölçümden geçer (`transform.preview`). Gerçek çalıştırmayla "
        "birebir tutmak zorunda.",
        "",
        f"**{len(exact)}/{len(results)} vakada tahmin ile gerçekleşen arasındaki "
        f"fark {TOLERANCE} puanın altında.**",
        "",
        "| vaka | önce | tahmin | gerçekleşen | fark |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results:
        out.append(f"| `{r.name}` | {r.before:.1f} | {r.forecast:.1f} | "
                   f"{r.after:.1f} | {r.error:.1f} |")
    out += [
        "",
        "**2. Sıralama modeli** — “önce ne” listesindeki tek tek düşüşler "
        "(`analyze.projected_score`). Bu farklı bir soru: bir **insan** o "
        "gözlemi kapatırsa ne olur. Modelin varsayımı `DESIGNED_AT` "
        f"({DESIGNED_AT:.0f}), yani bir eksenin tasarlandığında ulaştığı yer. "
        "Aracın kendi dönüşümü bunun ötesine geçer — bütün ekseni proje "
        "token'larına bağlar — dolayısıyla model dönüşümü izlemez, izlememeli.",
        "",
        "| vaka | sıralama modeli | dönüşümün gerçeği | fark |",
        "|---|---:|---:|---:|",
    ]
    for r in results:
        gap = round(abs(r.ordering_drop - r.actual), 1)
        out.append(f"| `{r.name}` | −{r.ordering_drop:.1f} | −{r.actual:.1f} | "
                   f"{gap:.1f} |")
    out += [
        "",
        "Sapma tek yönlü ve bilerek: listedeki düşüş bir **alt sınırdır**. "
        "Sıralama için doğru sayıdır, seviye için değil — ve seviyeyi öğrenmek "
        "isteyen zaten yukarıdaki tahmini görüyor.",
    ]
    if worse:
        out += [
            "",
            "## Dönüşümün yardım etmediği vakalar",
            "",
            "Bunlar da tabloda duruyor. Zaten tasarlanmış bir projede dönüşüm "
            "skoru **yükseltebilir**: araç kendi sistemini kurar, o sistem de "
            "projenin kendi sisteminden daha dar olabilir. Tahmin ekranda "
            "göründüğü için kullanıcı bunu uygulamadan önce görür.",
            "",
        ]
        for r in worse:
            out.append(f"- **{r.name}** — {r.before:.1f} → {r.after:.1f}")
    out += ["", "## Kapatılan işler", ""]
    for r in results:
        out.append(f"- **{r.name}** — {', '.join(r.closed) or 'yok'}")
    out += [
        "",
        f"Aracın kendi kapattığı gözlemler (`analyze.SELF_FIXABLE`): "
        f"{', '.join('`' + o + '`' for o in sorted(SELF_FIXABLE))}.",
        "",
        "`slop_styled` listede ama kapattığı iş yok: bütün stiller CSS-in-JS'te "
        "ve ortada yeniden yazılacak bir `class` özniteliği yok. Rapor o "
        "projede ⚡ işareti koymaz, tahmin de skorun değişmeyeceğini söyler.",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    results = run()
    width = max((len(r.name) for r in results), default=10)
    print(f"{'case':<{width}}  önce   tahmin  gerçek  fark   sıralama  durum")
    print("-" * (width + 48))
    for r in results:
        print(f"{r.name:<{width}}  {r.before:5.1f}  {r.forecast:6.1f}  "
              f"{r.after:6.1f}  {r.error:4.1f}  {r.ordering_drop:8.1f}  "
              f"{'ok' if r.ok else 'SAPMA'}")
    bad = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} vakada tahmin "
          f"{TOLERANCE} puanın altında")
    out = Path(__file__).with_name("impact.md")
    out.write_text(render(results), encoding="utf-8", newline="\n")
    print(f"{out} yazıldı")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
