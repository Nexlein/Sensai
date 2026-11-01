"""Settings by dotted key: catalog, parsing, validation, sources and formatting."""

import datetime
import re
import tomllib

import pytest

from sensai.core.config import AppConfig, ConfigError, load_config
from sensai.core.config_file import flatten
from sensai.core.settings import (
    SETTINGS,
    assign,
    format_keys,
    format_settings,
    format_value,
    get_value,
    parse_value,
    sources,
    template,
    validated,
)


def test_every_schema_leaf_is_a_documented_setting():
    leaves = set(flatten(AppConfig().model_dump(exclude={"mcp"})))

    assert set(SETTINGS) == leaves
    assert all(setting.description for setting in SETTINGS.values())


def test_catalog_reads_types_bounds_and_restart_flags():
    assert SETTINGS["interface"].kind == '"cli" | "tui" | "web"'
    assert SETTINGS["interface"].restart
    assert SETTINGS["budget.threshold"].kind == "float > 0 ≤ 1"
    assert SETTINGS["options.temperature"].kind == "float | none ≥ 0"
    assert not SETTINGS["options.temperature"].restart


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("0.2", 0.2),
        ("8192", 8192),
        ('"quoted text"', "quoted text"),
        ("qwen3.5:4b", "qwen3.5:4b"),
        ("http://localhost:11434", "http://localhost:11434"),
        ("none", None),
        ("NULL", None),
        ('["a", "b"]', ["a", "b"]),
        ("2024-01-01", datetime.date(2024, 1, 1)),
    ],
)
def test_parse_value_reads_toml_literals_and_falls_back_to_text(raw, expected):
    assert parse_value(raw) == expected


def test_validated_returns_a_new_config_with_the_value():
    config = AppConfig()

    candidate = validated(config, "options.temperature", "0.7")

    assert candidate.options.temperature == 0.7
    assert config.options.temperature is None


def test_validated_falls_back_to_the_raw_text_for_string_settings():
    candidate = validated(AppConfig(), "persona.name", "2024-01-01")

    assert candidate.persona.name == "2024-01-01"


def test_validated_none_resets_to_the_default():
    config = AppConfig(model="llama3.2")

    assert validated(config, "model", None).model == AppConfig().model


@pytest.mark.parametrize(
    ("key", "raw", "reason"),
    [
        ("missing", "1", "Unknown config key: missing"),
        ("options.temperature", "hot", "Invalid options.temperature"),
        ("interface", "gui", "Invalid interface"),
        ("options.num_ctx", "1024", "must not exceed"),
        ("rag.chunk_overlap", "900", "chunk_overlap must be smaller"),
    ],
)
def test_validated_explains_rejected_values(key, raw, reason):
    with pytest.raises(ConfigError, match=re.escape(reason)):
        validated(AppConfig(), key, raw)


def test_validation_errors_drop_pydantics_value_error_prefix():
    with pytest.raises(ConfigError) as caught:
        validated(AppConfig(), "options.num_ctx", "1024")

    assert "Value error" not in str(caught.value)


def test_effort_off_is_stored_as_false():
    assert validated(AppConfig(), "reasoning.think", "off").reasoning.think is False


def test_assign_keeps_nested_objects_in_place():
    config = AppConfig()
    options = config.options

    assign(config, "options.seed", validated(config, "options.seed", "42"))

    assert config.options is options
    assert options.seed == 42


def test_get_value_follows_dotted_keys():
    assert get_value(AppConfig(), "guardrails.pii") == "redact"


def test_format_value_masks_secrets_and_marks_unset_values():
    assert format_value("api_key", "gsk_secret") == "***"
    assert format_value("options.seed", None) == "(unset)"
    assert format_value("model", "x") == '"x"'


def test_sources_tell_default_file_flag_and_session_apart(tmp_path):
    path = tmp_path / "sensai.toml"
    path.write_text('model = "llama3.2"\n[options]\ntemperature = 0.2\n')
    config = load_config(path, provider="mock")
    config.options.temperature = 0.9

    found = sources(config, path, {"options.temperature"})

    assert found["model"] == "file"
    assert found["provider"] == "flag"
    assert found["options.temperature"] == "session"
    assert found["base_url"] == "default"


def test_disabled_file_tools_count_as_set_by_the_file(tmp_path):
    path = tmp_path / "sensai.toml"
    path.write_text("[tools]\nfs_allowed_root = false\n")

    assert sources(load_config(path), path)["tools.fs_allowed_root"] == "file"


def test_format_settings_groups_by_section_and_filters_by_prefix():
    config = AppConfig()
    found = sources(config, None)

    everything = format_settings(config, found)
    options = format_settings(config, found, "options")

    assert everything.startswith("interface = ")
    assert "[guardrails]" in everything
    assert options.splitlines()[0] == "[options]"
    assert "[guardrails]" not in options


def test_format_settings_rejects_an_unknown_prefix():
    with pytest.raises(ConfigError, match="Unknown config key: nothing"):
        format_settings(AppConfig(), {}, "nothing")


def test_format_keys_lists_type_default_restart_and_meaning():
    text = format_keys("rag")

    assert 'rag.model: str = "nomic-embed-text" (restart)' in text
    assert "Ollama embedding model" in text


def test_template_is_valid_toml_and_sets_nothing():
    loaded = tomllib.loads(template())

    assert all(section == {} for section in loaded.values())
    assert AppConfig(**loaded) == AppConfig()


def test_uncommenting_the_template_gives_the_defaults():
    lines = []
    for line in template().splitlines():
        if line.startswith(("# [", "# MCP")):
            break
        match = re.fullmatch(r"# (\w+ = .+)", line)
        if match and not match.group(1).endswith("= ..."):
            lines.append(match.group(1))
        elif line.startswith("["):
            lines.append(line)

    assert AppConfig(**tomllib.loads("\n".join(lines))) == AppConfig()


def test_every_setting_is_documented_in_the_configuration_reference():
    from pathlib import Path

    reference = (
        Path(__file__).resolve().parents[2] / "docs" / "configuration.md"
    ).read_text()

    documented = set(re.findall(r"^\| `([\w.]+)` +\|", reference, re.MULTILINE))

    assert set(SETTINGS) - documented == set()
