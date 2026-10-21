"""Entry point: argument parsing and interface choice."""

from types import SimpleNamespace

import pytest

from sensai.interfaces import dispatcher


def _context(interface, warnings=()):
    context = SimpleNamespace(
        config=SimpleNamespace(interface=interface),
        startup_warnings=list(warnings),
        closed=False,
    )

    async def aclose():
        context.closed = True

    context.aclose = aclose
    return context


async def test_dispatch_builds_one_session_then_runs_selected_interface(monkeypatch):
    calls = []
    context = _context("tui")

    async def fake_build_session(**kwargs):
        calls.append(("build", kwargs))
        return context

    async def fake_run_tui(received_context):
        calls.append(("tui", received_context))

    async def unexpected_cli(*args):
        raise AssertionError("CLI runner should not be called")

    monkeypatch.setattr(dispatcher, "build_session", fake_build_session)
    monkeypatch.setattr(dispatcher, "run_tui", fake_run_tui)
    monkeypatch.setattr(dispatcher, "run_cli", unexpected_cli)

    code = await dispatcher.dispatch(["chat", "--ui", "tui", "--session", "saved"])

    assert code == 0
    assert [call[0] for call in calls] == ["build", "tui"]
    assert calls[0][1]["interface"] == "tui"
    assert calls[0][1]["session_name"] == "saved"
    assert calls[1][1] is context


async def test_dispatch_prints_startup_warnings_and_closes_the_session(
    monkeypatch, capsys
):
    context = _context("cli", ["MCP server 'x' skipped: [boom]"])

    async def fake_build_session(**kwargs):
        return context

    async def fake_run_cli(received_context, console):
        assert not context.closed

    monkeypatch.setattr(dispatcher, "build_session", fake_build_session)
    monkeypatch.setattr(dispatcher, "run_cli", fake_run_cli)

    assert await dispatcher.dispatch(["chat"]) == 0

    assert "MCP server 'x' skipped: [boom]" in capsys.readouterr().out
    assert context.closed


async def test_dispatch_closes_the_session_when_the_interface_crashes(monkeypatch):
    context = _context("cli")

    async def fake_build_session(**kwargs):
        return context

    async def crashing_cli(received_context, console):
        raise RuntimeError("ui crashed")

    monkeypatch.setattr(dispatcher, "build_session", fake_build_session)
    monkeypatch.setattr(dispatcher, "run_cli", crashing_cli)

    with pytest.raises(RuntimeError, match="ui crashed"):
        await dispatcher.dispatch(["chat"])

    assert context.closed


async def test_dispatch_runs_the_web_interface(monkeypatch):
    context = _context("web")
    ran = []

    async def fake_build_session(**kwargs):
        return context

    async def fake_run_web(received_context):
        ran.append(received_context)

    monkeypatch.setattr(dispatcher, "build_session", fake_build_session)
    monkeypatch.setattr(dispatcher, "run_web", fake_run_web)

    assert await dispatcher.dispatch(["chat", "--ui", "web"]) == 0

    assert ran == [context]
    assert context.closed


def test_console_entry_point_invokes_dispatcher(monkeypatch):
    async def fake_dispatch(argv):
        assert argv == ["chat", "--ui", "cli"]
        return 0

    monkeypatch.setattr(dispatcher, "dispatch", fake_dispatch)
    monkeypatch.setattr("sys.argv", ["sensai", "chat", "--ui", "cli"])

    with pytest.raises(SystemExit) as exc:
        dispatcher.main()

    assert exc.value.code == 0
