from types import SimpleNamespace

import pytest

from sensai.interfaces import dispatcher


async def test_dispatch_builds_one_session_then_runs_selected_interface(monkeypatch):
    calls = []
    context = SimpleNamespace(config=SimpleNamespace(interface="tui"))

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


def test_console_entry_point_invokes_dispatcher(monkeypatch):
    async def fake_dispatch(argv):
        assert argv == ["chat", "--ui", "cli"]
        return 0

    monkeypatch.setattr(dispatcher, "dispatch", fake_dispatch)
    monkeypatch.setattr("sys.argv", ["sensai", "chat", "--ui", "cli"])

    with pytest.raises(SystemExit) as exc:
        dispatcher.main()

    assert exc.value.code == 0
