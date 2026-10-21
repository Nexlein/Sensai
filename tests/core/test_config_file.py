"""Config file editing: comments and unknown keys survive every write."""

import os
import stat
import tomllib

import pytest

from sensai.core.config_file import (
    ConfigError,
    file_values,
    flatten,
    read_document,
    update_file,
    write_text,
)

COMMENTED = """# my settings
model = "llama3.2"  # the small one

[options]
# keep answers stable
temperature = 0.2
custom_key = "not in the schema"
"""


def test_missing_file_reads_as_an_empty_document(tmp_path):
    assert read_document(tmp_path / "absent.toml").unwrap() == {}
    assert file_values(tmp_path / "absent.toml") == {}


def test_malformed_file_is_a_one_line_config_error(tmp_path):
    path = tmp_path / "sensai.toml"
    path.write_text("model = \n")

    with pytest.raises(ConfigError, match="Malformed config file"):
        read_document(path)


def test_flatten_joins_nested_keys_and_keeps_lists_whole():
    assert flatten({"a": 1, "b": {"c": [1, 2], "d": {"e": "x"}}}) == {
        "a": 1,
        "b.c": [1, 2],
        "b.d.e": "x",
    }


def test_update_keeps_comments_and_unknown_keys(tmp_path):
    path = tmp_path / "sensai.toml"
    path.write_text(COMMENTED)

    update_file(path, {"options.temperature": 0.7, "provider": "mock"})

    text = path.read_text()
    assert "# my settings" in text
    assert "# the small one" in text
    assert "# keep answers stable" in text
    assert 'custom_key = "not in the schema"' in text
    assert tomllib.loads(text)["options"]["temperature"] == 0.7
    assert tomllib.loads(text)["provider"] == "mock"


def test_update_creates_missing_tables_including_nested_ones(tmp_path):
    path = tmp_path / "sensai.toml"

    update_file(
        path,
        {
            "reasoning.think": "high",
            "mcp.servers.gh": {"command": "docker", "env": {"TOKEN": "x"}},
        },
    )

    data = tomllib.loads(path.read_text())
    assert data["reasoning"] == {"think": "high"}
    assert data["mcp"]["servers"]["gh"] == {"command": "docker", "env": {"TOKEN": "x"}}


def test_removing_the_last_key_of_a_table_drops_the_table(tmp_path):
    path = tmp_path / "sensai.toml"
    update_file(path, {"model": "x", "options.seed": 1, "mcp.servers.a.command": "c"})

    update_file(path, {}, removed=["options.seed", "mcp.servers.a", "missing.key"])

    assert tomllib.loads(path.read_text()) == {"model": "x"}


def test_writing_a_key_under_a_scalar_is_refused(tmp_path):
    path = tmp_path / "sensai.toml"
    path.write_text('model = "x"\n')

    with pytest.raises(ConfigError, match="not a table"):
        update_file(path, {"model.name": "y"})


def test_rewrite_keeps_the_file_permissions(tmp_path):
    path = tmp_path / "sensai.toml"
    path.write_text('model = "x"\n')
    os.chmod(path, 0o600)

    update_file(path, {"model": "y"})

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_failure_is_a_config_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")

    with pytest.raises(ConfigError, match="Could not write"):
        write_text(blocker / "sensai.toml", "x = 1\n")
