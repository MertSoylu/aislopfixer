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


def test_source_modules_sharing_meta_stem_are_scanned(tmp_path):
    """security.md is meta; security.ts is real app code and must scan."""
    (tmp_path / "security.md").write_text("# policy", encoding="utf-8")
    (tmp_path / "security.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "support.tsx").write_text("export const S = () => null;\n", encoding="utf-8")
    rels = {sf.rel_path for sf in collect(str(tmp_path))}
    assert "security.md" not in rels
    assert "security.ts" in rels
    assert "support.tsx" in rels


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


def test_bom_is_stripped_from_scanned_text(tmp_path):
    # A leading BOM must not survive into rule input — it silently breaks
    # every ^-anchored pattern on line 1 (merge markers, emoji headers…).
    (tmp_path / "x.js").write_bytes(b"\xef\xbb\xbf<<<<<<< HEAD\nconst a = 1;\n")
    files = collect(str(tmp_path))
    assert len(files) == 1
    assert files[0].text.startswith("<<<<<<<")


def test_minified_by_name_skipped(tmp_path):
    (tmp_path / "lib.min.js").write_text("const x = 1;\n" * 5, encoding="utf-8")
    (tmp_path / "app-min.css").write_text("body{color:red}\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("const y = 2;\n", encoding="utf-8")
    rels = {sf.rel_path for sf in collect(str(tmp_path))}
    assert rels == {"app.js"}


def test_minified_by_content_skipped(tmp_path):
    # A single multi-KB line is build output, not authored source — scanning it
    # floods per-match rules (a vendor bundle has hundreds of `catch(t){}`).
    bundle = "!function(){" + "var a=1;try{f()}catch(t){}" * 800 + "}();"
    (tmp_path / "bundle.js").write_text(bundle, encoding="utf-8")
    (tmp_path / "app.js").write_text("const y = 2;\n", encoding="utf-8")
    rels = {sf.rel_path for sf in collect(str(tmp_path))}
    assert rels == {"app.js"}


def test_authored_file_with_one_long_line_not_skipped(tmp_path):
    # One inlined data-URI among normal lines is authored code, not a bundle.
    lines = [f".c{i} {{ color: #123; }}" for i in range(80)]
    lines.insert(40, ".hero { background: url(data:image/png;base64," + "A" * 3000 + "); }")
    (tmp_path / "site.css").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rels = {sf.rel_path for sf in collect(str(tmp_path))}
    assert rels == {"site.css"}


def test_count_matches_collect_with_minified(tmp_path):
    (tmp_path / "ok.js").write_text("const y = 2;\n", encoding="utf-8")
    (tmp_path / "vendor.min.js").write_text("var a=1;\n", encoding="utf-8")
    bundle = "!function(){" + "var a=1;" * 1500 + "}();"
    (tmp_path / "chunk.js").write_text(bundle, encoding="utf-8")
    assert count_eligible(str(tmp_path)) == len(collect(str(tmp_path))) == 1


def test_count_eligible_honors_config_ignore(tmp_path):
    from aislopfixer.config import Config

    (tmp_path / "index.html").write_text("<p>hi</p>\n", encoding="utf-8")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "old.html").write_text("<p>old</p>\n", encoding="utf-8")
    (tmp_path / ".aislopfixer.toml").write_text('ignore = ["legacy"]\n', encoding="utf-8")
    assert count_eligible(str(tmp_path)) == 2
    assert count_eligible(str(tmp_path), Config.load(str(tmp_path))) == 1
