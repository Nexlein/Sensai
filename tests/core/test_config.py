import pytest

from sensai.core.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    AppConfig,
    ConfigError,
    ToolsConfig,
    load_config,
    save_config,
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


def test_tools_config_defaults():
    config = load_config(config_path=None)
    assert config.tools.fs_allowed_root is None


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


def test_save_config_omits_unset_tools_section(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "[tools]" not in config_file.read_text()
    assert load_config(config_file) == AppConfig()
