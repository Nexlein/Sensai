from rich.console import Console

from sensai.interfaces.cli.app import _run


def _script_stdin(monkeypatch, inputs):
    answers = iter(inputs)

    def fake_input(self, prompt=""):
        try:
            return next(answers)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr(Console, "input", fake_input)


async def test_chat_streams_mock_provider_reply_until_exit(monkeypatch, capsys):
    _script_stdin(monkeypatch, ["hello", "exit"])

    code = await _run(["chat", "--provider", "mock"])

    out = capsys.readouterr().out
    assert code == 0
    assert "sensai:" in out
    assert "This is a mocked response from SENSAI." in out


async def test_chat_exits_cleanly_on_eof(monkeypatch, capsys):
    _script_stdin(monkeypatch, [])

    code = await _run(["chat", "--provider", "mock"])

    assert code == 0


async def test_chat_reports_empty_input_and_continues(monkeypatch, capsys):
    _script_stdin(monkeypatch, ["", "exit"])

    code = await _run(["chat", "--provider", "mock"])

    assert code == 0
    assert "Empty input" in capsys.readouterr().out


async def test_chat_rejects_unknown_provider(capsys):
    code = await _run(["chat", "--provider", "does-not-exist"])

    assert code == 1
    assert "Unknown provider" in capsys.readouterr().out


async def test_chat_rejects_malformed_config_file(tmp_path, capsys):
    bad_config = tmp_path / "sensai.toml"
    bad_config.write_text("not [ valid toml")

    code = await _run(["chat", "--provider", "mock", "--config", str(bad_config)])

    assert code == 1
    assert "Malformed config file" in capsys.readouterr().out
