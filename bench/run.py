"""``python -m bench.run`` — print the corpus table and the separation margin."""

from __future__ import annotations

import sys

from .cases import TWIN_MARGIN
from .harness import run, twin_gaps


def main() -> int:
    outcomes = run()
    width = max(len(o.case.name) for o in outcomes)
    print(f"{'case':<{width}}  şablon  karar  tekrar  band          durum")
    print("-" * (width + 46))
    for o in outcomes:
        lo, hi = o.case.template
        status = "ok" if o.ok else "FAIL"
        print(f"{o.case.name:<{width}}  {o.template:6.1f}  {o.decisions:5.1f}  "
              f"{o.repetition:6.1f}  {lo:>3.0f}–{hi:<3.0f}      {status}")
        for missing in o.missing:
            print(f"{'':<{width}}    eksik gözlem: {missing}")
        for spurious in o.spurious:
            print(f"{'':<{width}}    yanlış pozitif: {spurious}")

    for a, b, gap in twin_gaps(outcomes):
        mark = "ok" if gap <= TWIN_MARGIN else "FAIL"
        print(f"\nikiz farkı {a} / {b}: {gap:.1f} puan "
              f"(sınır {TWIN_MARGIN:.0f})  {mark}")

    slop = [o.template for o in outcomes if o.case.family == "slop"]
    clean = [o.template for o in outcomes if o.case.family in ("middle", "clean")]
    if slop and clean:
        margin = min(slop) - max(clean)
        print(f"\nayrım payı: {margin:.1f} puan "
              f"(en düşük slop {min(slop):.1f} · en yüksek diğer {max(clean):.1f})")
    twins_ok = all(gap <= TWIN_MARGIN for _, _, gap in twin_gaps(outcomes))
    return 0 if all(o.ok for o in outcomes) and twins_ok else 1


if __name__ == "__main__":
    sys.exit(main())
