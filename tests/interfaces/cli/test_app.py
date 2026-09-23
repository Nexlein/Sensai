from rich.console import Console

from sensai.interfaces.cli.app import _build_tool_registry, _run


def _script_stdin(monkeypatch, inputs):
    answers = iter(inputs)

    def fake_input(self, prompt=""):
        try:
            return next(answers)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr(Console, "input", fake_input)


async def test_chat_streams_mock_provider_reply_until_exit(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["hello", "/exit"])

    code = await _run(["chat", "--provider", "mock"])

    out = capsys.readouterr().out
    assert code == 0
    assert "sensai:" in out
    assert "This is a mocked response from SENSAI." in out


async def test_chat_exits_cleanly_on_eof(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, [])

    code = await _run(["chat", "--provider", "mock"])

    assert code == 0


async def test_chat_reports_empty_input_and_continues(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["", "/exit"])

    code = await _run(["chat", "--provider", "mock"])

    assert code == 0
    assert "Empty input" in capsys.readouterr().out


async def test_chat_rejects_unknown_provider(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    code = await _run(["chat", "--provider", "does-not-exist"])

    assert code == 1
    assert "Unknown provider" in capsys.readouterr().out


async def test_chat_rejects_malformed_config_file(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad_config = tmp_path / "sensai.toml"
    bad_config.write_text("not [ valid toml")

    code = await _run(["chat", "--provider", "mock", "--config", str(bad_config)])

    assert code == 1
    assert "Malformed config file" in capsys.readouterr().out


async def test_chat_session_resumes_across_restarts(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["hello", "/exit"])
    code = await _run(["chat", "--provider", "mock", "--session", "my-session"])
    assert code == 0

    from sensai.memory.session import SqliteMemoryStore

    store = SqliteMemoryStore()
    conversation = await store.load("my-session")
    assert conversation is not None
    assert conversation.id == "my-session"
    assert [m.content for m in conversation.messages] == [
        "hello",
        "This is a mocked response from SENSAI.",
    ]


async def test_chat_session_resume_prints_prior_messages(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["hello", "/exit"])
    await _run(["chat", "--provider", "mock", "--session", "my-session"])
    capsys.readouterr()

    _script_stdin(monkeypatch, ["/exit"])
    code = await _run(["chat", "--provider", "mock", "--session", "my-session"])

    out = capsys.readouterr().out
    assert code == 0
    assert "hello" in out
    assert "This is a mocked response from SENSAI." in out


async def test_chat_session_unknown_name_creates_new(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    _script_stdin(monkeypatch, ["hi", "/exit"])
    code = await _run(["chat", "--provider", "mock", "--session", "brand-new"])
    assert code == 0

    from sensai.memory.session import SqliteMemoryStore

    store = SqliteMemoryStore()
    conversation = await store.load("brand-new")
    assert conversation is not None
    assert conversation.id == "brand-new"


def test_build_tool_registry_is_empty_when_root_is_unset():
    assert _build_tool_registry(None).get_tools_schema() == []


def test_build_tool_registry_registers_file_tools(tmp_path):
    schemas = _build_tool_registry(str(tmp_path)).get_tools_schema()

    assert {schema["function"]["name"] for schema in schemas} == {
        "read_file",
        "list_dir",
    }
