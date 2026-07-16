from pathlib import Path

from aislopfixer import fixer
from aislopfixer.engine.models import SourceFile
from aislopfixer.engine.runner import run_file_rules


def _scan(p: Path):
    text = p.read_text(encoding="utf-8")
    return run_file_rules(SourceFile(abs_path=str(p), rel_path=p.name, text=text))


def _get(findings, rule_id):
    return next(f for f in findings if f.rule_id == rule_id)


def _leak(findings):
    return next(f for f in findings if f.rule_id.startswith("ai_leak"))


def test_auto_fix_deletes_whole_line(tmp_path):
    p = tmp_path / "index.html"
    p.write_text("keep\nAs an AI language model, I cannot.\nkeep2\n", encoding="utf-8")
    assert fixer.apply_fix(_leak(_scan(p)))
    assert p.read_text(encoding="utf-8") == "keep\nkeep2\n"
    assert Path(str(p) + ".aislopfixer.bak").exists()


def test_prompt_fix_replaces_value(tmp_path):
    p = tmp_path / "c.html"
    p.write_text("mail john@example.com now\n", encoding="utf-8")
    assert fixer.apply_fix(_get(_scan(p), "placeholder.email"), "real@site.com")
    assert "real@site.com" in p.read_text(encoding="utf-8")


def test_dead_href_uses_template(tmp_path):
    p = tmp_path / "d.html"
    p.write_text('<a href="#">x</a>\n', encoding="utf-8")
    assert fixer.apply_fix(_get(_scan(p), "placeholder.dead_href"), "https://x.com")
    assert 'href="https://x.com"' in p.read_text(encoding="utf-8")


def test_relocation_survives_prior_edit(tmp_path):
    p = tmp_path / "e.html"
    p.write_text('As an AI language model, hi.\n<a href="#">x</a>\n', encoding="utf-8")
    findings = _scan(p)
    assert fixer.apply_fix(_leak(findings))                         # shifts offsets
    assert fixer.apply_fix(_get(findings, "placeholder.dead_href"), "https://x.com")
    out = p.read_text(encoding="utf-8")
    assert "As an AI" not in out and 'href="https://x.com"' in out


def test_diff_preview(tmp_path):
    p = tmp_path / "f.html"
    p.write_text("mail john@example.com\n", encoding="utf-8")
    diff = fixer.diff_preview(_get(_scan(p), "placeholder.email"), "real@site.com")
    assert diff and "real@site.com" in diff


def test_annotate_inserts_comment(tmp_path):
    p = tmp_path / "g.html"
    p.write_text("<p>TODO: finish this</p>\n", encoding="utf-8")
    assert fixer.annotate(_get(_scan(p), "placeholder.todo"))
    assert "aislopfixer:" in p.read_text(encoding="utf-8")


def test_img_alt_fix_inserts_attribute(tmp_path):
    p = tmp_path / "h.html"
    p.write_text('<img src="logo.png">\n', encoding="utf-8")
    assert fixer.apply_fix(_get(_scan(p), "a11y.img_no_alt"), "Company logo")
    assert '<img alt="Company logo" src="logo.png">' in p.read_text(encoding="utf-8")


def test_multiple_img_alt_fixes_hit_distinct_tags(tmp_path):
    # Each <img> shares the bare "<img" prefix, so a generic anchor would relocate
    # every later fix onto the first image. The full-tag anchor keeps them apart.
    p = tmp_path / "gallery.html"
    p.write_text('<img src="a.png">\n<img src="b.png">\n', encoding="utf-8")
    imgs = [f for f in _scan(p) if f.rule_id == "a11y.img_no_alt"]
    assert len(imgs) == 2
    assert fixer.apply_fix(imgs[0], "first")
    assert fixer.apply_fix(imgs[1], "second")
    assert p.read_text(encoding="utf-8") == (
        '<img alt="first" src="a.png">\n<img alt="second" src="b.png">\n'
    )


def test_img_alt_fix_preserves_jsx_braces(tmp_path):
    p = tmp_path / "Card.jsx"
    p.write_text("<img src={cover} />\n", encoding="utf-8")
    assert fixer.apply_fix(_get(_scan(p), "a11y.img_no_alt"), "cover photo")
    assert p.read_text(encoding="utf-8") == '<img alt="cover photo" src={cover} />\n'


def test_fix_preserves_lf_line_endings(tmp_path):
    # On Windows a bare write_text would rewrite the whole file as CRLF.
    p = tmp_path / "lf.html"
    p.write_bytes(b"keep\nAs an AI language model, I cannot.\nkeep2\n")
    assert fixer.apply_fix(_leak(_scan(p)))
    assert p.read_bytes() == b"keep\nkeep2\n"


def test_fix_preserves_crlf_line_endings(tmp_path):
    p = tmp_path / "crlf.html"
    p.write_bytes(b"keep\r\nAs an AI language model, I cannot.\r\nkeep2\r\n")
    assert fixer.apply_fix(_leak(_scan(p)))
    assert p.read_bytes() == b"keep\r\nkeep2\r\n"


def test_annotate_preserves_lf_line_endings(tmp_path):
    p = tmp_path / "ann.html"
    p.write_bytes(b"<p>TODO: finish this</p>\n")
    assert fixer.annotate(_get(_scan(p), "placeholder.todo"))
    raw = p.read_bytes()
    assert b"aislopfixer:" in raw
    assert b"\r\n" not in raw


def test_reanchor_updates_shifted_positions(tmp_path):
    # Deleting line 1 shifts the TODO up; reanchor must move its line/snippet.
    p = tmp_path / "shift.html"
    p.write_text(
        "As an AI language model, hi.\n<p>TODO: later</p>\n", encoding="utf-8"
    )
    findings = _scan(p)
    todo = _get(findings, "placeholder.todo")
    assert todo.line == 2
    assert fixer.apply_fix(_leak(findings))
    fixer.reanchor(findings)
    assert todo.line == 1
    assert "TODO" in todo.snippet


def test_fix_preserves_bom_and_crlf(tmp_path):
    # Offsets are computed on BOM-stripped text (utf-8-sig, like the scanner);
    # the write-back must restore both the BOM and the CRLF endings.
    p = tmp_path / "leak.html"
    p.write_bytes("﻿keep\r\nAs an AI language model, x.\r\nkeep2\r\n".encode("utf-8"))
    text = p.read_text(encoding="utf-8-sig")
    findings = run_file_rules(SourceFile(abs_path=str(p), rel_path=p.name, text=text))
    assert fixer.apply_fix(_leak(findings))
    assert p.read_bytes() == "﻿keep\r\nkeep2\r\n".encode("utf-8")


def test_snapshot_and_restore_roundtrip(tmp_path):
    p = tmp_path / "a.html"
    original = "﻿hello\r\nworld\r\n".encode("utf-8")
    p.write_bytes(original)
    state = fixer.snapshot_file(str(p))
    assert state is not None
    p.write_bytes(b"clobbered")
    assert fixer.restore_file(str(p), state)
    assert p.read_bytes() == original


def test_snapshot_missing_file_returns_none(tmp_path):
    assert fixer.snapshot_file(str(tmp_path / "nope.html")) is None
