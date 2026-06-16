"""The .aislopfixer folder remembers resolved findings across scans."""

import json

from aislopfixer.engine.models import Category, Finding, Severity, Status
from aislopfixer.store import DIRNAME, LEDGER, REPORT, Store


def mk(rule_id, value, file="index.html", status=Status.OPEN,
       category=Category.PLACEHOLDER, line=1):
    return Finding(
        rule_id=rule_id, category=category, severity=Severity.WARNING,
        message="msg", file=file, abs_path=file, line=line, col=1,
        start=0, end=len(value), snippet=value, matched_text=value, status=status,
    )


def test_folder_name_is_dot_aislopfixer():
    assert DIRNAME == ".aislopfixer"


# ---------------------------------------------------------------- suppression
def test_fixed_finding_suppressed_next_scan(tmp_path):
    store = Store(str(tmp_path))
    store.record(mk("placeholder.bracket", "[Your Company Name]", status=Status.FIXED))
    again = mk("placeholder.bracket", "[Your Company Name]")
    assert store.filter([again]) == []


def test_annotated_finding_suppressed(tmp_path):
    store = Store(str(tmp_path))
    store.record(mk("placeholder.todo", "TODO: x", status=Status.ANNOTATED))
    assert store.filter([mk("placeholder.todo", "TODO: x")]) == []


def test_ignored_finding_suppressed(tmp_path):
    store = Store(str(tmp_path))
    store.record(mk("buzzword.delve", "delve", status=Status.IGNORED))
    assert store.filter([mk("buzzword.delve", "delve")]) == []


def test_skipped_finding_resurfaces(tmp_path):
    # "skip" means later, not never — it must come back on the next scan.
    store = Store(str(tmp_path))
    store.record(mk("buzzword.delve", "delve", status=Status.SKIPPED))
    keep = mk("buzzword.delve", "delve")
    assert store.filter([keep]) == [keep]


def test_other_signature_not_suppressed(tmp_path):
    store = Store(str(tmp_path))
    store.record(mk("placeholder.bracket", "[A]", status=Status.FIXED))
    keep = mk("placeholder.bracket", "[B]")
    assert store.filter([keep]) == [keep]


def test_store_also_applies_allowlist(tmp_path):
    store = Store(str(tmp_path))
    store.allowlist.add(mk("placeholder.bracket", "[city]"))
    assert store.filter([mk("placeholder.bracket", "[city]")]) == []


# ---------------------------------------------------------------- persistence
def test_ledger_persists_across_instances(tmp_path):
    Store(str(tmp_path)).record(
        mk("placeholder.lorem", "lorem ipsum dolor", status=Status.FIXED)
    )
    assert (tmp_path / DIRNAME / LEDGER).exists()
    fresh = Store(str(tmp_path))
    assert fresh.filter([mk("placeholder.lorem", "lorem ipsum dolor")]) == []


def test_ledger_json_shape(tmp_path):
    store = Store(str(tmp_path))
    store.record(mk("placeholder.bracket", "[X]", status=Status.IGNORED, line=7))
    data = json.loads((tmp_path / DIRNAME / LEDGER).read_text(encoding="utf-8"))
    assert data["version"] == 1
    e = data["entries"][0]
    assert e["rule_id"] == "placeholder.bracket"
    assert e["value"] == "[X]"
    assert e["status"] == "ignored"
    assert e["line"] == 7
    assert "updated" in e


# --------------------------------------------------------------------- report
def test_write_report_creates_markdown(tmp_path):
    store = Store(str(tmp_path))
    findings = [
        mk("placeholder.lorem", "lorem ipsum", status=Status.FIXED),
        mk("buzzword.delve", "delve", category=Category.BUZZWORD),
    ]
    store.write_report(findings, str(tmp_path))
    report = tmp_path / DIRNAME / REPORT
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "# AI Slop Fixer" in text
    assert "Found:" in text
    assert "## By category" in text
    assert "## Remaining" in text  # the open buzzword finding


def test_write_report_clean_project(tmp_path):
    store = Store(str(tmp_path))
    store.write_report([], str(tmp_path))
    text = (tmp_path / DIRNAME / REPORT).read_text(encoding="utf-8")
    assert "No issues found" in text
