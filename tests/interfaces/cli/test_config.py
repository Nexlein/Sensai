"""`sensai config` from the shell: show, get, set, reset, keys, init, path."""

import io

import pytest
from rich.console import Console

from sensai.core.config import load_config
from sensai.interfaces.cli.config import run_config_command
from sensai.interfaces.dispatcher import build_arg_parser


def _run(*argv: str) -> tuple[int, str]:
    output = io.StringIO()
    console = Console(file=output, width=200, color_system=None)
    code = run_config_command(build_arg_parser().parse_args(["config", *argv]), console)
    return code, output.getvalue()


def test_init_writes_a_documented_file_once(tmp_path):
    path = tmp_path / "sensai.toml"

    code, out = _run("init", "--config", str(path))

    assert code == 0
    assert "Wrote" in out
    assert "# temperature = ..." in path.read_text()
    assert load_config(path) == load_config(None)
    assert _run("init", "--config", str(path))[0] == 1
    assert _run("init", "--config", str(path), "--force")[0] == 0


def test_set_then_get_round_trips_through_the_file(tmp_path):
    path = tmp_path / "sensai.toml"

    code, out = _run("set", "options.temperature", "0.3", "--config", str(path))

    assert code == 0
    assert out.strip() == f"options.temperature = 0.3 (saved to {path})"
    assert _run("get", "options.temperature", "--config", str(path))[1].strip() == (
        "options.temperature = 0.3"
    )


def test_set_joins_words_and_reset_drops_the_key(tmp_path):
    path = tmp_path / "sensai.toml"
    _run("set", "persona.name", "Sensai", "Collecte", "--config", str(path))

    assert load_config(path).persona.name == "Sensai Collecte"

    _run("reset", "persona.name", "--config", str(path))
    assert "persona" not in path.read_text()


@pytest.mark.parametrize(
    ("argv", "reason"),
    [
        (("set", "options.temperature", "hot"), "Invalid options.temperature"),
        (("set", "nope", "1"), "Unknown config key: nope"),
        (("set", "model"), "Usage: sensai config set"),
        (("reset",), "Usage: sensai config reset"),
    ],
)
def test_errors_are_one_line_and_exit_1(tmp_path, argv, reason):
    code, out = _run(*argv, "--config", str(tmp_path / "sensai.toml"))

    assert code == 1
    assert reason in out
    assert len(out.strip().splitlines()) == 1


def test_show_lists_sections_with_sources(tmp_path):
    path = tmp_path / "sensai.toml"
    path.write_text('model = "llama3.2"\n')

    code, out = _run("show", "--config", str(path))

    assert code == 0
    assert out.startswith(f"Config file: {path}")
    assert 'model = "llama3.2"' in out
    assert "[guardrails]" in out


def test_keys_and_path(tmp_path):
    assert "options.seed: int | none" in _run("keys", "options")[1]
    path = tmp_path / "x.toml"
    assert _run("path", "--config", str(path))[1].strip() == str(path.resolve())
