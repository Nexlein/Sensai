"""Web app."""

import signal
import socket
from types import SimpleNamespace
from typing import cast

import pytest
import uvicorn

from sensai.core.commands import CommandContext
from sensai.interfaces.web import app as web_app


def _context() -> CommandContext:
    """The app only stores the context; these tests never reach a route using it."""
    return cast(CommandContext, SimpleNamespace())


async def test_run_web_serves_the_app_on_the_given_address(monkeypatch, capsys):
    seen = {}

    class FakeServer:
        def __init__(self, config):
            seen["config"] = config

        async def serve(self):
            seen["served"] = True

    monkeypatch.setattr(web_app, "QuietServer", FakeServer)

    await web_app.run_web(_context(), host="127.0.0.1", port=9001)

    assert seen["served"]
    assert seen["config"].host == "127.0.0.1"
    assert seen["config"].port == 9001
    assert "http://127.0.0.1:9001" in capsys.readouterr().out


def test_server_does_not_replay_the_signal_it_stopped_on(monkeypatch):
    replayed = []
    monkeypatch.setattr(signal, "raise_signal", replayed.append)
    server = web_app.QuietServer(uvicorn.Config(web_app.build_app(_context())))

    with server.capture_signals():
        server.handle_exit(signal.SIGINT, None)  # what Ctrl+C does

    assert server.should_exit
    assert replayed == []


def test_plain_uvicorn_server_would_replay_it(monkeypatch):
    # Guards the reason QuietServer exists: if uvicorn stops doing this, drop it.
    replayed = []
    monkeypatch.setattr(signal, "raise_signal", replayed.append)
    server = uvicorn.Server(uvicorn.Config(web_app.build_app(_context())))

    with server.capture_signals():
        server.handle_exit(signal.SIGINT, None)

    assert replayed == [signal.SIGINT]


def test_app_hides_the_generated_api_docs():
    app = web_app.build_app(_context())

    assert app.docs_url is None
    assert app.openapi_url is None


async def test_busy_port_is_one_clear_line_and_nothing_starts(capsys):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]

        with pytest.raises(SystemExit) as exit_info:
            await web_app.run_web(_context(), host="127.0.0.1", port=port)

    out = capsys.readouterr()
    assert exit_info.value.code == 1
    assert f"Port {port} is already in use" in out.err
    assert "Sensai web UI" not in out.out
