import io
import json

import pytest
from rich.console import Console
from typer.testing import CliRunner

from sentinelforge import terminal_logo
from sentinelforge.cli import app


def test_sf_rotates_as_a_volume_with_bounded_periodic_frames():
    front = terminal_logo.logo_frame(0, ascii_only=True)
    edge = terminal_logo.logo_frame(12, ascii_only=True)
    back = terminal_logo.logo_frame(24, ascii_only=True)
    assert front.plain == terminal_logo.logo_frame(48, ascii_only=True).plain
    assert front.plain != edge.plain != back.plain
    count = lambda frame: sum(char not in " \n" for char in frame.plain)
    assert count(front) > count(edge) * 2
    assert count(back) > count(edge) * 2
    for frame in (front, edge, back):
        assert frame.plain.isascii()
        assert len(frame.plain.splitlines()) == 13
        assert all(len(line) == 54 for line in frame.plain.splitlines())
    front.append("modified")
    assert "modified" not in terminal_logo.logo_frame(0, ascii_only=True).plain


@pytest.mark.parametrize("environment", [
    {"CI": "true"}, {"SENTINELFORGE_NO_ANIMATION": "1"}, {"TERM": "dumb"},
])
def test_motion_disabled_environments_never_sleep_or_move_cursor(monkeypatch, environment):
    for name in ("CI", "SENTINELFORGE_NO_ANIMATION", "TERM"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    stream = io.StringIO()
    term = Console(file=stream, force_terminal=True, force_interactive=True, width=80, height=25)
    monkeypatch.setattr(terminal_logo.time, "sleep", lambda _: pytest.fail("Must not delay automation"))
    terminal_logo.show_logo(term)
    assert stream.getvalue()
    assert "\x1b[?25l" not in stream.getvalue()


def test_non_terminal_static_preview_has_no_ansi_and_never_waits(monkeypatch):
    stream = io.StringIO()
    term = Console(file=stream, force_terminal=False, width=80)
    monkeypatch.setattr(terminal_logo.time, "sleep", lambda _: pytest.fail("Pipe must not sleep"))
    terminal_logo.show_logo(term, seconds=30)
    assert "\x1b" not in stream.getvalue()
    assert len(stream.getvalue().splitlines()) == 13


def test_interrupt_restores_terminal_cursor(monkeypatch):
    for name in ("CI", "SENTINELFORGE_NO_ANIMATION", "TERM"):
        monkeypatch.delenv(name, raising=False)
    stream = io.StringIO()
    term = Console(file=stream, force_terminal=True, force_interactive=True, width=80, height=25)

    def interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(terminal_logo.time, "sleep", interrupt)
    token = terminal_logo.ANIMATION_ENABLED.set(True)
    try:
        with pytest.raises(KeyboardInterrupt):
            terminal_logo.show_logo(term)
    finally:
        terminal_logo.ANIMATION_ENABLED.reset(token)
    assert "\x1b[?25l" in stream.getvalue()
    assert "\x1b[?25h" in stream.getvalue()
    term.print("READY")
    assert "READY" in stream.getvalue()


def test_logo_cli_json_static_and_disable_option_do_not_create_data(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_DATABASE_PATH", str(tmp_path / "unused.sqlite3"))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(terminal_logo.time, "sleep", lambda _: pytest.fail("Must not sleep"))
    runner = CliRunner()
    structured = runner.invoke(app, ["logo", "--format", "json"])
    assert structured.exit_code == 0
    assert json.loads(structured.stdout) == {"logo": "SF", "axis": "Y", "animation": False}
    assert "\x1b" not in structured.stdout
    static = runner.invoke(app, ["--no-animation", "logo", "--format", "pretty"])
    assert static.exit_code == 0, static.output
    assert "SENTINELFORGE" in static.stdout and "\x1b" not in static.stdout
    assert not (tmp_path / "unused.sqlite3").exists()
    assert runner.invoke(app, ["logo", "--seconds", "31"]).exit_code == 2


def test_global_animation_flag_is_respected_in_an_interactive_terminal(monkeypatch):
    stream = io.StringIO()
    term = Console(file=stream, force_terminal=True, force_interactive=True, width=80, height=25)
    token = terminal_logo.ANIMATION_ENABLED.set(False)
    monkeypatch.setattr(terminal_logo.time, "sleep", lambda _: pytest.fail("Disabled animation waited"))
    try:
        terminal_logo.show_logo(term)
    finally:
        terminal_logo.ANIMATION_ENABLED.reset(token)
    assert "\x1b[?25l" not in stream.getvalue()


def test_small_terminal_falls_back_to_compact_sf_without_clipping(monkeypatch):
    stream = io.StringIO()
    term = Console(file=stream, force_terminal=False, width=25, height=10)
    monkeypatch.setattr(terminal_logo.time, "sleep", lambda _: pytest.fail("Small terminal waited"))
    terminal_logo.show_logo(term)
    assert stream.getvalue().strip() == "SF"
