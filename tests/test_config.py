"""Project config (.aislopfixer.toml): rule disabling, path ignores, defaults."""

import json

from aislopfixer.cli import main
from aislopfixer.config import Config


def _slop(tmp_path, conf: str | None = None):
    (tmp_path / "index.html").write_text(
        "<p>As an AI language model, I cannot browse the internet.</p>\n",
        encoding="utf-8",
    )
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "old.html").write_text(
        "<p>As an AI language model, I cannot browse the internet.</p>\n",
        encoding="utf-8",
    )
    if conf is not None:
        (tmp_path / ".aislopfixer.toml").write_text(conf, encoding="utf-8")
    return tmp_path


def _findings(tmp_path, capsys):
    main([str(tmp_path), "--json", "--no-store"])
    return json.loads(capsys.readouterr().out)["findings"]


# ---------------------------------------------------------------- Config.load
def test_missing_config_is_all_defaults(tmp_path):
    cfg = Config.load(str(tmp_path))
    assert cfg.disable == () and cfg.ignore == ()
    assert cfg.fail_on is None and cfg.min_confidence is None


def test_bad_toml_is_ignored(tmp_path, capsys):
    (tmp_path / ".aislopfixer.toml").write_text("disable = [", encoding="utf-8")
    cfg = Config.load(str(tmp_path))
    assert cfg == Config()
    assert "ignoring bad" in capsys.readouterr().err


def test_invalid_values_fall_back(tmp_path, capsys):
    (tmp_path / ".aislopfixer.toml").write_text(
        'fail_on = "sometimes"\nmin_confidence = 7\ndisable = "nope"\n',
        encoding="utf-8",
    )
    cfg = Config.load(str(tmp_path))
    assert cfg.fail_on is None and cfg.min_confidence is None and cfg.disable == ()


def test_path_ignored_matches_dirs_and_globs():
    cfg = Config(ignore=("legacy", "gen/**"))
    assert cfg.path_ignored("legacy/old.html")
    assert cfg.path_ignored("legacy\\old.html")  # windows separators
    assert cfg.path_ignored("gen/a/b.js")
    assert not cfg.path_ignored("src/app.js")


# --------------------------------------------------------------- end to end
def test_disable_prefix_silences_rule(tmp_path, capsys):
    _slop(tmp_path, 'disable = ["ai_leak"]\n')
    assert not any(
        f["rule_id"].startswith("ai_leak") for f in _findings(tmp_path, capsys)
    )


def test_ignore_glob_skips_tree(tmp_path, capsys):
    _slop(tmp_path, 'ignore = ["legacy/**"]\n')
    files = {f["file"] for f in _findings(tmp_path, capsys)}
    assert not any("legacy" in f for f in files)
    assert any("index.html" in f for f in files)


def test_config_fail_on_used_when_flag_absent(tmp_path):
    _slop(tmp_path, 'fail_on = "never"\n')
    assert main([str(tmp_path), "--check", "--no-store"]) == 0
    # explicit flag wins over config
    assert main(
        [str(tmp_path), "--check", "--no-store", "--fail-on", "warning"]
    ) == 1


def test_config_min_confidence_used_when_flag_absent(tmp_path, capsys):
    _slop(tmp_path, "min_confidence = 0.99\n")
    main([str(tmp_path), "--json", "--no-store"])
    assert json.loads(capsys.readouterr().out)["total"] == 0
