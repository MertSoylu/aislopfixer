from aislopfixer.scanner import MAX_BYTES, collect, count_eligible


def test_extension_and_ignore_filtering(tmp_path):
    (tmp_path / "a.html").write_text("hi", encoding="utf-8")
    (tmp_path / "b.txt").write_text("no", encoding="utf-8")
    (tmp_path / "style.css").write_text("body{}", encoding="utf-8")
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "c.js").write_text("x", encoding="utf-8")

    files = collect(str(tmp_path))
    names = {f.rel_path for f in files}

    assert "a.html" in names
    assert "style.css" in names
    assert "b.txt" not in names
    assert all("node_modules" not in n for n in names)
    assert count_eligible(str(tmp_path)) == 2


def test_hidden_dirs_skipped(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    (git / "h.js").write_text("x", encoding="utf-8")
    (tmp_path / "ok.js").write_text("x", encoding="utf-8")
    names = {f.rel_path for f in collect(str(tmp_path))}
    assert "ok.js" in names
    assert all(".git" not in n for n in names)


def test_meta_docs_skipped(tmp_path):
    for name in ("README.md", "CLAUDE.md", "AGENTS.md", "LICENSE",
                 "CONTRIBUTING.md", "changelog.md", "security.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
    (tmp_path / "guide.md").write_text("# real content page", encoding="utf-8")

    rels = {sf.rel_path for sf in collect(str(tmp_path))}
    assert rels == {"index.html", "guide.md"}


def test_meta_match_is_case_insensitive(tmp_path):
    (tmp_path / "ReadMe.md").write_text("x", encoding="utf-8")
    (tmp_path / "Agents.MD").write_text("x", encoding="utf-8")
    (tmp_path / "app.js").write_text("const x = 1", encoding="utf-8")
    rels = {sf.rel_path for sf in collect(str(tmp_path))}
    assert rels == {"app.js"}


def test_count_matches_collect_with_meta(tmp_path):
    for name in ("README.md", "claude.md", "index.html", "about.html"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert count_eligible(str(tmp_path)) == len(collect(str(tmp_path))) == 2


def test_count_matches_collect_with_oversized_file(tmp_path):
    # An oversized file is skipped by collect(); count_eligible must agree, else
    # the scan progress bar's "done / total" never reaches its total.
    (tmp_path / "ok.html").write_text("<h1>hi</h1>", encoding="utf-8")
    (tmp_path / "huge.js").write_text("/* x */\n" * (MAX_BYTES // 4), encoding="utf-8")
    assert count_eligible(str(tmp_path)) == len(collect(str(tmp_path))) == 1
