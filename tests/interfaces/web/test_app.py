from types import SimpleNamespace

from sensai.interfaces.web import app as web_app


async def test_run_web_serves_the_app_on_the_given_address(monkeypatch, capsys):
    seen = {}

    class FakeServer:
        def __init__(self, config):
            seen["config"] = config

        async def serve(self):
            seen["served"] = True

    monkeypatch.setattr(web_app.uvicorn, "Server", FakeServer)

    await web_app.run_web(SimpleNamespace(), host="127.0.0.1", port=9001)

    assert seen["served"]
    assert seen["config"].host == "127.0.0.1"
    assert seen["config"].port == 9001
    assert "http://127.0.0.1:9001" in capsys.readouterr().out


def test_app_hides_the_generated_api_docs():
    app = web_app.build_app(SimpleNamespace())

    assert app.docs_url is None
    assert app.openapi_url is None
