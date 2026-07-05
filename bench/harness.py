"""Scoring for the calibration corpus."""

from __future__ import annotations

from aislopfixer.engine.models import SourceFile
from aislopfixer.engine.runner import run_file_rules


def _findings(case: dict):
    name = case["filename"]
    sf = SourceFile(abs_path=name, rel_path=name, text=case["text"])
    return run_file_rules(sf)


def evaluate(cases: list[dict]) -> dict:
    """Return recall over expected detections and false positives on clean files."""
    tp = fn = clean_fp = 0
    missed: list[tuple[str, str, list[str]]] = []
    fp_detail: list[tuple[str, list[str]]] = []
    for c in cases:
        ids = [f.rule_id for f in _findings(c)]
        if c.get("clean"):
            if ids:
                clean_fp += len(ids)
                fp_detail.append((c["name"], ids))
            continue
        for pref in c["expect"]:
            if any(rid.startswith(pref) for rid in ids):
                tp += 1
            else:
                fn += 1
                missed.append((c["name"], pref, ids))
    total = tp + fn
    return {
        "tp": tp,
        "fn": fn,
        "recall": (tp / total) if total else 1.0,
        "clean_fp": clean_fp,
        "missed": missed,
        "fp_detail": fp_detail,
    }


def format_report(r: dict) -> str:
    lines = [
        "AI Slop Fixer — calibration",
        "=" * 32,
        f"recall          {r['recall'] * 100:5.1f}%   ({r['tp']}/{r['tp'] + r['fn']} expected detections)",
        f"clean-file FPs  {r['clean_fp']:5d}",
    ]
    if r["missed"]:
        lines.append("")
        lines.append("MISSED (expected but not detected):")
        for name, pref, ids in r["missed"]:
            lines.append(f"  - {name}: expected '{pref}'  got {ids}")
    if r["fp_detail"]:
        lines.append("")
        lines.append("FALSE POSITIVES on clean files:")
        for name, ids in r["fp_detail"]:
            lines.append(f"  - {name}: {ids}")
    return "\n".join(lines)
