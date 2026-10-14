import signal
from types import SimpleNamespace

import uvicorn

from sensai.interfaces.web import app as web_app


async def test_run_web_serves_the_app_on_the_given_address(monkeypatch, capsys):
    seen = {}

    class FakeServer:
        def __init__(self, config):
            seen["config"] = config

        async def serve(self):
            seen["served"] = True

    monkeypatch.setattr(web_app, "QuietServer", FakeServer)

    await web_app.run_web(SimpleNamespace(), host="127.0.0.1", port=9001)

    assert seen["served"]
    assert seen["config"].host == "127.0.0.1"
    assert seen["config"].port == 9001
    assert "http://127.0.0.1:9001" in capsys.readouterr().out


def test_server_does_not_replay_the_signal_it_stopped_on(monkeypatch):
    replayed = []
    monkeypatch.setattr(signal, "raise_signal", replayed.append)
    server = web_app.QuietServer(uvicorn.Config(web_app.build_app(SimpleNamespace())))

    with server.capture_signals():
        server.handle_exit(signal.SIGINT, None)  # what Ctrl+C does

    assert server.should_exit
    assert replayed == []


def test_plain_uvicorn_server_would_replay_it(monkeypatch):
    # Guards the reason QuietServer exists: if uvicorn stops doing this, drop it.
    replayed = []
    monkeypatch.setattr(signal, "raise_signal", replayed.append)
    server = uvicorn.Server(uvicorn.Config(web_app.build_app(SimpleNamespace())))

    with server.capture_signals():
        server.handle_exit(signal.SIGINT, None)

    assert replayed == [signal.SIGINT]


def test_app_hides_the_generated_api_docs():
    app = web_app.build_app(SimpleNamespace())

    assert app.docs_url is None
    assert app.openapi_url is None
