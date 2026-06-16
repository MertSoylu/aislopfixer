"""User-confirmed false positives must stay suppressed across scans."""

from aislopfixer.allowlist import FILENAME, Allowlist
from aislopfixer.engine.models import Category, Finding, Severity, SourceFile
from aislopfixer.engine.runner import run_file_rules


def mk(rule_id: str, value: str, file: str = "index.html",
       category: Category = Category.PLACEHOLDER) -> Finding:
    return Finding(
        rule_id=rule_id, category=category, severity=Severity.WARNING,
        message="msg", file=file, abs_path=file, line=1, col=1,
        start=0, end=len(value), snippet=value, matched_text=value,
    )


# ------------------------------------------------------------------- core gate
def test_add_then_filter_suppresses_same_signature(tmp_path):
    allow = Allowlist(str(tmp_path))
    f = mk("placeholder.bracket", "[checked]")
    assert allow.add(f) is True
    assert allow.filter([mk("placeholder.bracket", "[checked]")]) == []


def test_other_value_not_suppressed(tmp_path):
    allow = Allowlist(str(tmp_path))
    allow.add(mk("placeholder.bracket", "[checked]"))
    kept = allow.filter([mk("placeholder.bracket", "[Your Company Name]")])
    assert len(kept) == 1


def test_same_value_other_rule_not_suppressed(tmp_path):
    allow = Allowlist(str(tmp_path))
    allow.add(mk("placeholder.bracket", "[checked]"))
    kept = allow.filter([mk("duplicate.block", "[checked]", category=Category.DUPLICATE)])
    assert len(kept) == 1


def test_suppression_is_global_across_files(tmp_path):
    # signature carries no file -> ignoring [city] in page A clears it in page B
    allow = Allowlist(str(tmp_path))
    allow.add(mk("placeholder.bracket", "[city]", file="a.jsx"))
    kept = allow.filter([mk("placeholder.bracket", "[city]", file="b.jsx")])
    assert kept == []


# --------------------------------------------------------------- persistence
def test_persists_across_instances(tmp_path):
    Allowlist(str(tmp_path)).add(mk("placeholder.bracket", "[id]"))
    assert (tmp_path / FILENAME).exists()
    fresh = Allowlist(str(tmp_path))          # reloads file from disk
    assert fresh.filter([mk("placeholder.bracket", "[id]")]) == []


def test_add_is_idempotent(tmp_path):
    allow = Allowlist(str(tmp_path))
    assert allow.add(mk("placeholder.bracket", "[tag]")) is True
    assert allow.add(mk("placeholder.bracket", "[tag]")) is False
    assert len(allow) == 1


def test_unicode_value_roundtrips(tmp_path):
    Allowlist(str(tmp_path)).add(mk("buzzword.x", "çığır açan"))
    assert Allowlist(str(tmp_path)).filter([mk("buzzword.x", "çığır açan")]) == []


def test_missing_file_is_empty(tmp_path):
    allow = Allowlist(str(tmp_path))
    assert len(allow) == 0
    findings = [mk("placeholder.bracket", "[Your Name]")]
    assert allow.filter(findings) == findings


# --------------------------------------------------------------- end to end
def test_real_finding_suppressed_on_next_scan(tmp_path):
    text = "<p>Welcome to [Your Company Name] — edit me.</p>\n"
    sf = SourceFile(abs_path="i.html", rel_path="i.html", text=text)
    first = [f for f in run_file_rules(sf) if f.rule_id == "placeholder.bracket"]
    assert first, "real placeholder should be detected on the first scan"

    allow = Allowlist(str(tmp_path))
    allow.add(first[0])

    second = allow.filter(run_file_rules(sf))
    assert not [f for f in second if f.rule_id == "placeholder.bracket"]
