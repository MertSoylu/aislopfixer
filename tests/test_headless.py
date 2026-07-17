"""Headless CLI mode: exit codes, JSON output, --fix, memory suppression."""

import json

from aislopfixer.cli import main


def _slop_project(tmp_path):
    (tmp_path / "index.html").write_text(
        "<p>As an AI language model, I cannot browse the internet.</p>\n"
        "<p>Lorem ipsum dolor sit amet.</p>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "try { run(); } catch (e) {}\n", encoding="utf-8"
    )
    return tmp_path


def _clean_project(tmp_path):
    (tmp_path / "index.html").write_text(
        "<html lang='en'><head><title>Bakery</title></head>"
        "<body><p>We open at 8am on weekdays.</p></body></html>\n",
        encoding="utf-8",
    )
    return tmp_path


def test_fix_reanchors_remaining_findings(tmp_path, capsys):
    # The auto-fix deletes line 1; the dead href below must be reported at
    # its *new* line, not its pre-fix one.
    (tmp_path / "index.html").write_text(
        "As an AI language model, I cannot browse the internet.\n"
        '<a href="#">contact</a>\n',
        encoding="utf-8",
    )
    main([str(tmp_path), "--json", "--fix"])
    data = json.loads(capsys.readouterr().out)
    assert data["auto_fixed"] >= 1
    dead = next(
        f for f in data["findings"] if f["rule_id"] == "placeholder.dead_href"
    )
    assert dead["line"] == 1


def test_check_exits_1_on_slop(tmp_path, capsys):
    code = main([str(_slop_project(tmp_path)), "--check"])
    out = capsys.readouterr().out
    assert code == 1
    assert "ai_leak.strong" in out
    assert "slop score" in out


def test_check_exits_0_on_clean(tmp_path, capsys):
    code = main([str(_clean_project(tmp_path)), "--check"])
    assert code == 0
    assert "no slop found" in capsys.readouterr().out


def test_fail_on_never_always_exits_0(tmp_path):
    assert main([str(_slop_project(tmp_path)), "--check", "--fail-on", "never"]) == 0


def test_fail_on_error_ignores_warnings(tmp_path):
    # lone debug log = WARNING; with --fail-on error it must pass
    p = tmp_path
    (p / "app.js").write_text("console.log('here');\n", encoding="utf-8")
    assert main([str(p), "--check", "--fail-on", "error"]) == 0
    assert main([str(p), "--check", "--fail-on", "warning"]) == 1


def test_json_output_is_valid(tmp_path, capsys):
    main([str(_slop_project(tmp_path)), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["tool"] == "aislopfixer"
    assert data["total"] == len(data["findings"]) > 0
    f = data["findings"][0]
    assert {"rule_id", "severity", "file", "line", "message", "confidence"} <= set(f)


def test_min_confidence_filters(tmp_path, capsys):
    main([str(_slop_project(tmp_path)), "--json", "--min-confidence", "0.99"])
    data = json.loads(capsys.readouterr().out)
    assert data["total"] == 0


def test_fix_applies_auto_and_suppresses_next_run(tmp_path, capsys):
    p = _slop_project(tmp_path)
    main([str(p), "--fix"])
    out1 = capsys.readouterr().out
    assert "fixed automatically" in out1
    html = (p / "index.html").read_text(encoding="utf-8")
    assert "As an AI language model" not in html
    assert "Lorem ipsum" not in html
    # backup exists
    assert (p / "index.html.aislopfixer.bak").exists()
    # second run: fixed findings stay suppressed via the ledger
    main([str(p), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert not any(f["rule_id"].startswith("ai_leak") for f in data["findings"])


def test_sarif_output_is_valid(tmp_path, capsys):
    code = main([str(_slop_project(tmp_path)), "--sarif"])
    doc = json.loads(capsys.readouterr().out)
    assert code == 1
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "aislopfixer"
    assert run["results"], "expected findings in the SARIF run"
    res = run["results"][0]
    assert res["level"] in {"note", "warning", "error"}
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"]
    assert loc["region"]["startLine"] >= 1
    rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
    assert res["ruleId"] in rule_ids


def test_bad_path_exits_2(tmp_path):
    assert main([str(tmp_path / "missing"), "--check"]) == 2


def test_version_flag(capsys):
    try:
        main(["--version"])
    except SystemExit as e:
        assert e.code == 0
    assert "aislopfixer" in capsys.readouterr().out


def test_min_confidence_out_of_range_rejected(capsys):
    import pytest

    with pytest.raises(SystemExit) as exc:
        main([".", "--check", "--min-confidence", "1.5"])
    assert exc.value.code == 2
    assert "0..1" in capsys.readouterr().err


def test_fix_reports_what_it_fixed(tmp_path, capsys):
    _slop_project(tmp_path)
    main([str(tmp_path), "--check", "--fix"])
    out = capsys.readouterr().out
    assert "fixed [ai_leak.strong" in out
    assert "removed `" in out
    assert "backups: *.aislopfixer.bak" in out


def test_fix_cascade_surfaces_unmasked_findings_same_run(tmp_path, capsys):
    # Stripping the emoji turns `# 🎯 Conclusion` into a bare boilerplate
    # heading — the same --fix run must both fix and re-report, not leave the
    # discovery to the user's next invocation.
    (tmp_path / "notes.md").write_text(
        "# 🎯 Conclusion\n\nSome text.\n", encoding="utf-8"
    )
    code = main([str(tmp_path), "--check", "--fix"])
    out = capsys.readouterr().out
    assert "fixed [md.emoji_header]" in out
    assert "md.boilerplate_section" in out
    assert code == 0  # leftover is info-level; default fail-on is warning
    assert (tmp_path / "notes.md").read_text(encoding="utf-8").startswith("# Conclusion")


def test_json_lists_fixed_findings(tmp_path, capsys):
    _slop_project(tmp_path)
    main([str(tmp_path), "--json", "--fix"])
    data = json.loads(capsys.readouterr().out)
    assert data["auto_fixed"] == len(data["fixed"]) >= 1
    entry = data["fixed"][0]
    assert entry["rule_id"] and entry["file"] and entry["line"]


def test_bom_file_line_one_is_scanned(tmp_path, capsys):
    # BOM used to shift offsets so ^-anchored rules missed line 1 entirely.
    (tmp_path / "x.js").write_bytes(
        b"\xef\xbb\xbf<<<<<<< HEAD\na\n=======\nb\n>>>>>>> main\n"
    )
    code = main([str(tmp_path), "--check", "--no-store"])
    out = capsys.readouterr().out
    assert code == 1
    assert "x.js:1:1" in out and "merge.conflict_marker" in out


# ------------------------------------------------------- the --fail-on gate
def test_fail_on_risky_ignores_the_polish_tail(tmp_path, capsys):
    """A page whose only sin is adjectives must not turn CI red.

    19 POLISH rules carry severity=warning, so under the default severity gate
    a zero-defect marketing page exited 1 — while the tool's own fix brief told
    the agent those were "simple warnings… do not spend this pass on them".
    """
    (tmp_path / "index.html").write_text(
        "<h1>A seamless, robust and scalable platform</h1>\n"
        "<p>Our cutting-edge solution leverages best-in-class technology to "
        "deliver a seamless experience. Unlock the power of a robust, scalable "
        "and innovative platform that is truly game-changing.</p>\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path), "--check"]) == 1          # severity gate: red
    capsys.readouterr()
    assert main([str(tmp_path), "--check", "--fail-on", "risky"]) == 0
    capsys.readouterr()


def test_fail_on_impact_gates_separate_risky_from_broken(tmp_path, capsys):
    (tmp_path / "app.js").write_text(
        "const q = `SELECT * FROM users WHERE id = ${userId}`;\n", encoding="utf-8"
    )
    assert main([str(tmp_path), "--check", "--fail-on", "risky"]) == 1
    capsys.readouterr()
    assert main([str(tmp_path), "--check", "--fail-on", "broken"]) == 0  # runs fine
    capsys.readouterr()

    (tmp_path / "gone.js").write_text(
        "export function boot() {\n  // ... rest of the code ...\n}\n", encoding="utf-8"
    )
    assert main([str(tmp_path), "--check", "--fail-on", "broken"]) == 1
    capsys.readouterr()


# ------------------------------------------------------------------ encoding
def test_machine_output_is_utf8_on_a_legacy_codepage_stream(tmp_path):
    """JSON/SARIF are UTF-8 by spec — never the console codepage.

    On a cp1252 stream an em-dash went out as a raw 0x97, so the artifact this
    tool advertises as its CI path was not valid UTF-8 and would not parse.
    """
    import io
    import json as _json

    from aislopfixer.headless import run_check

    _slop_project(tmp_path)
    for kw in ({"as_json": True}, {"as_sarif": True}):
        buf = io.BytesIO()
        stream = io.TextIOWrapper(buf, encoding="cp1252", errors="replace", newline="")
        run_check(str(tmp_path), use_store=False, stream=stream, **kw)
        stream.flush()
        _json.loads(buf.getvalue().decode("utf-8"))  # raises if not UTF-8 / not JSON


def test_ascii_degrade_is_per_character(tmp_path):
    """One unencodable character must not degrade the whole document."""
    import io

    from aislopfixer.headless import _fit_encoding

    class Stream(io.StringIO):
        encoding = "cp1252"

    # cp1252 has an em-dash: keep it, even next to a character it cannot encode.
    assert _fit_encoding("a — b \U0001f680 c", Stream()).startswith("a — b ")
    # cp1252 has no arrow: that one degrades.
    assert _fit_encoding("done → yes", Stream()) == "done -> yes"
