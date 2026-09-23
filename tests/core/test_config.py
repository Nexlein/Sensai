import pytest

from sensai.core.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    ConfigError,
    load_config,
    resolve_session,
)


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

    config = load_config(config_file, cli_model="llama3.2")

    assert config.model == "llama3.2"


def test_cli_arg_overrides_default_when_no_config_file(tmp_path):
    config = load_config(tmp_path / "missing.toml", cli_model="phi3")

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


def test_resolve_session_returns_name_when_given():
    assert resolve_session(["chat", "--session", "my-session"]) == "my-session"


def test_resolve_session_returns_none_when_absent():
    assert resolve_session(["chat"]) is None
