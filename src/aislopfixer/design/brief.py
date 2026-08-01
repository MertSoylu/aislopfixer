"""Render a report into a brief an AI coding agent can act on.

The tool fixes what a class rewrite can fix. What is left over is real design
work — a section order that follows the template, one block shape doing three
jobs, copy written to fill slots — and that work needs a person or an agent.

The brief is written for the agent, so it leads with the constraint rather than
the complaint: here is the system that now exists, here is what has already
been changed, here is what is still wrong and what "fixed" would look like.
Observations with no prescription are omitted; a finding an agent cannot act on
is noise in this document even when it is true in the report.
"""

from __future__ import annotations

from .analyze import priorities
from .models import Axis, DesignReport

_MAX_EVIDENCE = 5
_ACT_AT = 0.4          # severities below this are noted, not written out

# Observations the class-level transform cannot act on *by construction*: the
# fix is a change to the element tree, which the tool never makes.
_COMPONENT_BOUNDARY = frozenset({"space.shared_band_wrapper"})


def render(report: DesignReport, system=None, applied: int = 0,
           accepted: set[str] | None = None) -> str:
    """The markdown brief, ready to paste into a coding agent."""
    accepted = accepted or set()
    live = [o for o in report.observations if o.key not in accepted]
    # The one class of finding the transform structurally cannot reach. Pulled
    # out of the ordinary list because it is not "the tool has not done this
    # yet" — it is "the tool will never do this", and an agent reading a mixed
    # list has no way to tell those apart.
    blocked = [o for o in live if o.id in _COMPONENT_BOUNDARY]
    live = [o for o in live if o not in blocked]
    act = [o for o in live if o.severity >= _ACT_AT and o.prescription]
    note = [o for o in live if o not in act]

    out: list[str] = [
        "# Tasarım de-slop görevi",
        "",
        f"Proje: `{report.root}` · {report.files_scanned} dosya, "
        f"{report.elements} eleman.",
        "",
        "## Durum",
        "",
        f"- **Şablon skoru {report.template_score:.0f}/100** — {report.verdict}",
        f"- **Karar yoğunluğu {report.decision_density:.0f}/100** — bu projede kaç "
        f"bağımsız tasarım kararı var. Üretilmiş sayfalar 10–30 arasında kalır.",
        f"- **Tekrar {report.repetition:.0f}/100** — sayfanın ne kadarı kendisinin "
        f"kopyası.",
        "",
        "Bu iki sayı birlikte okunur: az karar + çok tekrar = şablon. Az karar + "
        "az tekrar = sade ama kendine ait bir sayfa; onu şablona benzetme.",
        "",
    ]

    jobs = [p for p in priorities(report) if p.observation.key not in accepted]
    if jobs:
        out += [
            "## Önce ne — etkiye göre",
            "",
            "Sıra, her işi kapatıp aracın kendi skor formülünü yeniden "
            "çalıştırmaktan çıkıyor; yanındaki sayı şablon skorunun tahmini "
            "düşüşü. `⚡` olanları araç `s` ekranından kendisi yapabilir, "
            "`✎` olanlar sana kalıyor.",
            "",
        ]
        out += [
            f"{i}. **−{p.drop:.1f}** {'⚡' if p.self_fixable else '✎'} "
            f"{p.observation.title} — {p.observation.stat}"
            for i, p in enumerate(jobs, 1)
        ]
        out.append("")

    if applied:
        out += [
            f"## Zaten yapıldı ({applied} düzenleme)",
            "",
            "Araç sınıf listelerini yeniden yazdı: stok palet değerleri sistem "
            "rollerine, tek bant ritmi bölüm rolüne göre dört banda, simetrik "
            "ızgaralar asimetrik bölünmeye, ayarsız display tipografisi "
            "ayarlanmış ölçeğe çevrildi. **Bu değişiklikleri geri alma** — "
            "üstüne çalış.",
            "",
        ]

    if system is not None:
        out += ["## Kullanılacak sistem", ""]
        out += [f"- **{label}:** {value}" for label, value in system.summary()]
        out += [
            "",
            "Tokenlar `.aislopfixer/system.css` içinde tanımlı. Yeni yazacağın "
            "her şey bu isimleri kullanmalı — `bg-accent`, `text-ink-muted`, "
            "`py-band-narrative`, `max-w-read`, `rounded-panel` — ham palet "
            "değerlerini (`bg-blue-600`, `text-gray-500`) geri getirme.",
            "",
        ]
        if system.doctrine:
            out += ["Arketipin kuralları:", ""]
            out += [f"- {rule}" for rule in system.doctrine]
            out += [""]

    out += [
        "## Kalan iş",
        "",
        "Sırayla, en ağırdan hafife. Her madde bir ölçüme dayanıyor; ölçümü "
        "değiştirecek şekilde çöz, maddeyi susturacak şekilde değil.",
        "",
    ]
    if not act:
        out.append("_Sınıf düzeyinde çözülemeyen bir şey kalmadı._")
    for i, obs in enumerate(act, 1):
        out += [
            f"### {i}. {obs.title}",
            "",
            f"**Eksen:** {obs.axis.label} · **Ölçüm:** {obs.stat} · "
            f"**Ağırlık:** {obs.severity:.2f}",
            "",
            obs.detail,
            "",
            f"**Yapılacak:** {obs.prescription}",
            "",
        ]
        if obs.evidence:
            out.append("Nerede:")
            out += [f"- `{e.file}:{e.line}`" + (f" — `{e.value}`" if e.value else "")
                    for e in obs.evidence[:_MAX_EVIDENCE]]
            if len(obs.evidence) > _MAX_EVIDENCE:
                out.append(f"- …ve {len(obs.evidence) - _MAX_EVIDENCE} yer daha")
            out.append("")

    if blocked:
        out += [
            "## Aracın yapamadığı: bileşen sınırı",
            "",
            "Dönüşüm yalnızca sınıf listelerini değiştirir — hiçbir etiket "
            "eklenmez, kaldırılmaz, sarılmaz. Aşağıdaki işler tam olarak o "
            "sınırın ötesinde: düzeltme paylaşılan bir bileşen kökünde "
            "toplandığı için araç yazsa bile **her kullanıma aynı değeri** "
            "yazar. Bunlar senin işin.",
            "",
        ]
        for obs in blocked:
            out += [
                f"### {obs.title}",
                "",
                f"**Ölçüm:** {obs.stat}",
                "",
                obs.detail,
                "",
                f"**Yapılacak:** {obs.prescription}",
                "",
            ]
            if obs.evidence:
                out.append("Nerede:")
                out += [f"- `{e.file}:{e.line}`"
                        + (f" — {e.value}" if e.value else "")
                        for e in obs.evidence[:_MAX_EVIDENCE]]
                if len(obs.evidence) > _MAX_EVIDENCE:
                    out.append(f"- …ve {len(obs.evidence) - _MAX_EVIDENCE} yer daha")
                out.append("")

    if report.clusters:
        out += ["## Tekrar eden blok şekilleri", ""]
        for c in report.clusters[:5]:
            out.append(
                f"- **{c.label}** — {c.count} kopya, {len(c.files)} dosya, "
                f"metin uzunluğu değişkenliği %{c.text_variance * 100:.0f}"
            )
        out.append("")

    if note:
        out += ["## Ayrıca ölçüldü (düşük ağırlık)", ""]
        out += [f"- {o.title} — {o.stat}" for o in note]
        out.append("")

    if report.notes:
        out += [
            "## Ölçümün göremediği",
            "",
            "Aşağıdakiler bir bulgu değil, kapsam bildirimi: skorların projenin "
            "ne kadarını gerçekten kapsadığını söyler. Sessiz atlama, "
            "\"her şeye baktım\" gibi okunur.",
            "",
        ]
        out += [f"- {n}" for n in report.notes]
        out.append("")

    out += [
        "## Kabul kriteri",
        "",
        "İşin bittiğinde `aislopfixer` yeniden çalıştırıldığında:",
        "",
        "- Şablon skoru 30'un altına inmeli,",
        "- Karar yoğunluğu 60'ın üstüne çıkmalı,",
        "- `repeat.canonical_order` ve `repeat.block_shape` gözlemleri kalmamalı.",
        "",
        "Skoru düşürmek için ölçümü kandırma: bölüm silmek, metni kısaltmak ya "
        "da sınıfları kaldırmak sayıyı düşürür ama sayfayı iyileştirmez.",
        "",
    ]
    return "\n".join(out)
