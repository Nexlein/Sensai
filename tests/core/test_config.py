import pytest

from sensai.core.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    AppConfig,
    ConfigError,
    EvalConfig,
    GuardrailsConfig,
    McpConfig,
    McpServerConfig,
    MemoryConfig,
    PersonaConfig,
    RagConfig,
    ReasoningConfig,
    ToolsConfig,
    load_config,
    save_config,
)
from sensai.domain.models import ModelOptions


def test_missing_config_file_falls_back_to_defaults(tmp_path):
    config = load_config(tmp_path / "does-not-exist.toml")

    assert config.provider == DEFAULT_PROVIDER
    assert config.model == DEFAULT_MODEL
    assert config.base_url == DEFAULT_BASE_URL


def test_config_file_overrides_defaults(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text('model = "mistral"\nbase_url = "http://example:1234"\n')

    config = load_config(config_file)

    assert config.model == "mistral"
    assert config.base_url == "http://example:1234"
    assert config.provider == DEFAULT_PROVIDER


def test_cli_arg_overrides_config_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text('model = "mistral"\n')

    config = load_config(config_file, model="llama3.2")

    assert config.model == "llama3.2"


def test_cli_arg_overrides_default_when_no_config_file(tmp_path):
    config = load_config(tmp_path / "missing.toml", model="phi3")

    assert config.model == "phi3"


def test_malformed_config_file_raises_clear_error(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text("this is not [valid toml")

    with pytest.raises(ConfigError, match="Malformed config file"):
        load_config(config_file)


def test_no_config_path_uses_defaults():
    config = load_config(config_path=None)

    assert config.provider == DEFAULT_PROVIDER
    assert config.model == DEFAULT_MODEL
    assert config.base_url == DEFAULT_BASE_URL


def test_tools_config_defaults():
    config = load_config(config_path=None)
    assert config.tools.fs_allowed_root == "."


def test_tools_config_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text('[tools]\nfs_allowed_root = "/tmp"\n')

    config = load_config(config_file)
    assert config.tools.fs_allowed_root == "/tmp"


def test_save_config_round_trips_all_values(tmp_path):
    config_file = tmp_path / "nested" / "sensai.toml"
    config = AppConfig(
        provider="mock",
        model="custom-model",
        base_url="http://example:1234",
        tools=ToolsConfig(fs_allowed_root="/tmp/project"),
    )

    save_config(config, config_file)
    loaded = load_config(config_file)

    assert loaded == config


def test_save_config_round_trips_api_key(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(provider="groq", model="m", api_key="gsk_secret")

    save_config(config, config_file)

    assert load_config(config_file) == config


def test_save_config_omits_unset_api_key(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "api_key" not in config_file.read_text()


def test_save_config_omits_unset_tools_section(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "[tools]" not in config_file.read_text()
    assert load_config(config_file) == AppConfig()


def test_fs_tools_disabled_with_false(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text("[tools]\nfs_allowed_root = false\n")

    assert load_config(config_file).tools.fs_allowed_root is None


def test_save_config_round_trips_disabled_fs_tools(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(tools=ToolsConfig(fs_allowed_root=None))

    save_config(config, config_file)

    assert "fs_allowed_root = false" in config_file.read_text()
    assert load_config(config_file) == config


def test_interface_cli_override_takes_precedence_over_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text('interface = "tui"\n', encoding="utf-8")

    assert load_config(config_file).interface == "tui"
    assert load_config(config_file, interface="cli").interface == "cli"


def test_invalid_interface_is_rejected(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text('interface = "unknown"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid config values"):
        load_config(config_file)


def test_save_config_preserves_interface(tmp_path):
    config_file = tmp_path / "sensai.toml"
    save_config(AppConfig(interface="tui"), config_file)

    assert load_config(config_file).interface == "tui"


def test_guardrails_are_on_by_default_with_safe_actions():
    guardrails = load_config(config_path=None).guardrails

    assert guardrails.enabled is True
    assert guardrails.injection == "block"
    assert guardrails.pii == "redact"


def test_guardrails_can_be_disabled_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text("[guardrails]\nenabled = false\n")

    assert load_config(config_file).guardrails.enabled is False


def test_save_config_keeps_guardrails_disabled(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(guardrails=GuardrailsConfig(enabled=False))

    save_config(config, config_file)

    assert "enabled = false" in config_file.read_text()
    assert load_config(config_file).guardrails.enabled is False


def test_guardrails_config_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(
        '[guardrails]\nenabled = true\ninjection = "flag"\npii = "block"\n'
    )

    guardrails = load_config(config_file).guardrails

    assert guardrails == GuardrailsConfig(enabled=True, injection="flag", pii="block")


def test_guardrails_partial_section_keeps_other_defaults(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text("[guardrails]\nenabled = true\n")

    guardrails = load_config(config_file).guardrails

    assert guardrails == GuardrailsConfig(enabled=True)


@pytest.mark.parametrize(
    "section",
    [
        '[guardrails]\ninjection = "redact"\n',
        '[guardrails]\npii = "flag"\n',
        '[guardrails]\nenabled = "maybe"\n',
    ],
)
def test_invalid_guardrails_values_are_rejected(tmp_path, section):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(section)

    with pytest.raises(ConfigError, match="Invalid config values"):
        load_config(config_file)


def test_save_config_round_trips_guardrails(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(
        tools=ToolsConfig(fs_allowed_root="/tmp/project"),
        guardrails=GuardrailsConfig(enabled=True, injection="flag", pii="block"),
    )

    save_config(config, config_file)

    assert load_config(config_file) == config


def test_save_config_omits_default_guardrails_section(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "[guardrails]" not in config_file.read_text()


def test_reply_log_is_off_by_default():
    assert load_config(config_path=None).eval == EvalConfig(
        log_replies=False, replies_path="logs/replies.jsonl"
    )


def test_eval_config_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text('[eval]\nlog_replies = true\nreplies_path = "r.jsonl"\n')

    assert load_config(config_file).eval == EvalConfig(
        log_replies=True, replies_path="r.jsonl"
    )


def test_save_config_round_trips_eval(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(
        eval=EvalConfig(
            log_replies=True,
            replies_path="out/r.jsonl",
            log_prompts=True,
            prompts_path="out/p.jsonl",
        )
    )

    save_config(config, config_file)

    assert load_config(config_file) == config


def test_save_config_omits_default_eval_section(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "[eval]" not in config_file.read_text()


def test_mcp_has_no_servers_by_default():
    assert load_config(config_path=None).mcp.servers == {}


def test_mcp_servers_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(
        '[mcp.servers.fs]\ncommand = "npx"\nargs = ["-y", "server"]\ntimeout = 5\n'
        '[mcp.servers.fs.env]\nTOKEN = "abc"\n'
        '[mcp.servers.bare]\ncommand = "tool"\n'
    )

    servers = load_config(config_file).mcp.servers

    assert servers["fs"] == McpServerConfig(
        command="npx", args=["-y", "server"], env={"TOKEN": "abc"}, timeout=5
    )
    assert servers["bare"] == McpServerConfig(command="tool")
    assert servers["bare"].timeout == 30.0


@pytest.mark.parametrize(
    "section",
    [
        '[mcp.servers.a]\ncommand = ""\n',
        '[mcp.servers.a]\ncommand = "  "\n',
        "[mcp.servers.a]\nargs = []\n",
        '[mcp.servers.a]\ncommand = "x"\ntimeout = 0\n',
        '[mcp.servers.a]\ncommand = "x"\nargs = "not-a-list"\n',
        '[mcp.servers."bad name"]\ncommand = "x"\n',
        '[mcp.servers."a.b"]\ncommand = "x"\n',
    ],
)
def test_invalid_mcp_server_is_a_config_error(tmp_path, section):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(section)

    with pytest.raises(ConfigError):
        load_config(config_file)


def test_save_config_round_trips_mcp_servers(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(
        mcp=McpConfig(
            servers={
                "fs": McpServerConfig(
                    command="npx",
                    args=["-y", 'quote"d', "é"],
                    env={"A-B": "x y", "TOKEN": 'se"cret'},
                    timeout=12.5,
                ),
                "bare": McpServerConfig(command="tool"),
            }
        )
    )

    save_config(config, config_file)

    assert load_config(config_file).mcp == config.mcp


def test_save_config_omits_mcp_when_unset(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "mcp" not in config_file.read_text()


def test_memory_config_defaults():
    assert load_config(config_path=None).memory == MemoryConfig(
        enabled=True, auto_inject=True
    )


def test_memory_config_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text("[memory]\nenabled = false\nauto_inject = false\n")

    assert load_config(config_file).memory == MemoryConfig(
        enabled=False, auto_inject=False
    )


def test_reasoning_config_defaults():
    assert load_config(config_path=None).reasoning == ReasoningConfig(
        enabled=True, show_thoughts=False, max_steps=5, think="low"
    )


def test_reasoning_config_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(
        '[reasoning]\nshow_thoughts = true\nmax_steps = 3\nthink = "high"\n'
    )

    assert load_config(config_file).reasoning == ReasoningConfig(
        enabled=True, show_thoughts=True, max_steps=3, think="high"
    )


def test_reasoning_max_steps_must_be_positive(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text("[reasoning]\nmax_steps = 0\n")

    with pytest.raises(ConfigError):
        load_config(config_file)


def test_save_config_round_trips_memory(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(memory=MemoryConfig(enabled=False, auto_inject=False))

    save_config(config, config_file)

    assert load_config(config_file).memory == config.memory


def test_save_config_round_trips_reasoning(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(
        reasoning=ReasoningConfig(
            enabled=True, show_thoughts=True, max_steps=3, think="high"
        )
    )

    save_config(config, config_file)

    assert load_config(config_file).reasoning == config.reasoning


def test_options_are_unset_by_default():
    assert AppConfig().options.to_payload() == {}


def test_options_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(
        'model = "qwen3.5:4b"\n\n[options]\ntemperature = 0\nseed = 42\nnum_ctx = 8192\n'
    )

    options = load_config(config_file).options

    assert options.to_payload() == {"temperature": 0, "seed": 42, "num_ctx": 8192}


@pytest.mark.parametrize(
    "section",
    [
        "[options]\nnum_ctx = 4096\n",
        "[options]\nnum_ctx = 8192\nnum_predict = 512\n",
        "[budget]\nmax_tokens = 9000\n[options]\nnum_ctx = 8192\n",
    ],
)
def test_budget_larger_than_context_is_a_one_line_error(tmp_path, section):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(section)

    with pytest.raises(ConfigError, match="budget.max_tokens") as exc:
        load_config(config_file)

    assert "\n" not in str(exc.value)


def test_budget_within_context_is_accepted(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(
        "[budget]\nmax_tokens = 3584\n[options]\nnum_ctx = 4096\nnum_predict = 512\n"
    )

    assert load_config(config_file).options.num_ctx == 4096


@pytest.mark.parametrize(
    "section", ["temperature = -1", "top_p = 0", "num_ctx = 0", "num_predict = 0"]
)
def test_invalid_option_values_are_rejected(tmp_path, section):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(f"[options]\n{section}\n")

    with pytest.raises(ConfigError, match="Invalid config values"):
        load_config(config_file)


def test_save_config_round_trips_options(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(
        options=ModelOptions(temperature=1.2, top_p=0.9, seed=42, num_ctx=16384)
    )

    save_config(config, config_file)

    assert load_config(config_file).options == config.options


def test_save_config_omits_unset_options_section(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "[options]" not in config_file.read_text()


def test_rag_is_off_by_default_and_tools_are_on():
    config = AppConfig()

    assert config.rag == RagConfig()
    assert config.rag.enabled is False
    assert (config.tools.web_search, config.tools.sandbox) == (True, True)


def test_rag_config_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(
        '[rag]\nenabled = true\ndir = "data/collecte"\ntop_k = 3\nchunk_size = 800\n'
    )

    rag = load_config(config_file).rag

    assert rag == RagConfig(enabled=True, dir="data/collecte", top_k=3, chunk_size=800)


@pytest.mark.parametrize(
    "section",
    [
        "[rag]\ntop_k = 0\n",
        "[rag]\nchunk_size = 0\n",
        "[rag]\nchunk_size = 100\nchunk_overlap = 100\n",
        "[rag]\nenabled = true\n",
        "[tools]\nsandbox = 3\n",
    ],
)
def test_invalid_rag_or_tool_values_are_rejected(tmp_path, section):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(section)

    with pytest.raises(ConfigError, match="Invalid config values"):
        load_config(config_file)


def test_save_config_round_trips_rag_and_tool_toggles(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(
        rag=RagConfig(
            enabled=True,
            dir="data/collecte",
            model="mxbai-embed-large",
            db="collecte.db",
            top_k=8,
            chunk_size=1000,
            chunk_overlap=100,
        ),
        tools=ToolsConfig(web_search=False, sandbox=False),
    )

    save_config(config, config_file)
    loaded = load_config(config_file)

    assert loaded.rag == config.rag
    assert loaded.tools == config.tools


def test_save_config_omits_default_rag_section(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "[rag]" not in config_file.read_text()


def test_persona_is_off_by_default():
    assert AppConfig().persona == PersonaConfig()
    assert AppConfig().persona.enabled is False


def test_persona_config_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(
        '[persona]\nenabled = true\nname = "Collecte"\nfile = "personas/collecte.md"\n'
    )

    persona = load_config(config_file).persona

    assert persona == PersonaConfig(
        enabled=True, name="Collecte", file="personas/collecte.md"
    )


@pytest.mark.parametrize(
    "section",
    [
        "[persona]\nenabled = true\n",
        '[persona]\ninstruction = "a"\nfile = "b.md"\n',
    ],
)
def test_invalid_persona_is_rejected(tmp_path, section):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text(section)

    with pytest.raises(ConfigError, match="Invalid config values"):
        load_config(config_file)


def test_save_config_round_trips_persona(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(
        persona=PersonaConfig(
            enabled=True, name="Collecte", instruction='Tu es "Collecte".\nRègle 1.'
        )
    )

    save_config(config, config_file)

    assert load_config(config_file).persona == config.persona


def test_save_config_omits_default_persona_section(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "[persona]" not in config_file.read_text()
