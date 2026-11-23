"""Command-line tests (offline)."""

import json
from pathlib import Path

import pytest

from anyvideo import cli

ROOT = Path(__file__).resolve().parent.parent


def test_link_shortcut_means_get(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "cmd_get", lambda a: seen.update(vars(a)))
    parser = cli.build_parser()
    for sub in parser._subparsers._group_actions[0].choices.values():
        if sub.get_default("func").__name__ == "cmd_get":
            sub.set_defaults(func=cli.cmd_get)
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    cli.main(["https://example.com/v", "-a", "mp3"])
    assert seen["url"] == "https://example.com/v" and seen["audio"] == "mp3"


def test_no_args_means_serve(monkeypatch):
    called = {}
    monkeypatch.setattr(cli, "cmd_serve", lambda a: called.setdefault("serve", a))
    parser = cli.build_parser()
    parser._subparsers._group_actions[0].choices["serve"].set_defaults(func=cli.cmd_serve)
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    cli.main([])
    assert "serve" in called and called["serve"].no_browser is False


def test_get_refuses_private_address(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["get", "http://127.0.0.1/video.mp4"])
    assert e.value.code == 1
    assert "private" in capsys.readouterr().err


def test_get_refuses_multi_format_keyword(capsys, monkeypatch):
    monkeypatch.setattr(cli._core(), "normalize_url", lambda u: u)
    with pytest.raises(SystemExit):
        cli.main(["get", "https://example.com/v", "-f", "all"])
    assert "Invalid format id" in capsys.readouterr().err


def test_extension_manifest_is_consistent():
    m = json.loads((ROOT / "extension/manifest.json").read_text())
    assert m["manifest_version"] == 3
    for path in [*m["icons"].values(), m["action"]["default_popup"], m["background"]["service_worker"],
                 *m["background"]["scripts"]]:
        assert (ROOT / "extension" / path).is_file(), path


def test_plugin_files_are_consistent():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert market["plugins"][0]["name"] == plugin["name"]
    skill = (ROOT / "skills/download-video/SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\n") and "description:" in skill.split("---")[1]


def test_versions_match():
    import tomllib

    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    from anyvideo import __version__

    assert version == __version__
    assert json.loads((ROOT / "extension/manifest.json").read_text())["version"] == version
    assert json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"] == version


def test_emoji_titles_do_not_crash_output(monkeypatch):
    import io
    import sys

    # A Windows console in cp1252 can't encode emoji; output must not crash.
    fake = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", fake)
    cli._safe_output()
    print("Saved: C:/videos/guess it 😍❤️.mp4")
    sys.stdout.flush()
    assert "guess it" in fake.buffer.getvalue().decode("utf-8")
