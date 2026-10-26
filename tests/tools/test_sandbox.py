import os
import stat
import sys
from pathlib import Path

import pytest

from sensai.interfaces.diff import parse_diff
from sensai.tools.base import SensitiveTool
from sensai.tools.sandbox import MAX_OUTPUT_CHARS, MAX_TIMEOUT, RunCodeTool


def fake_docker(tmp_path: Path, body: str) -> str:
    """A stand-in `docker` executable; `body` is a Python script reading stdin."""
    path = tmp_path / "docker"
    path.write_text(f"#!{sys.executable}\nimport sys\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


# Echoes argv to stderr-free stdout so tests can inspect the docker command.
RUN_SCRIPT = """
if sys.argv[1] == "kill":
    open(sys.argv[0] + ".killed", "w").write(sys.argv[2])
    sys.exit(0)
"""


def test_run_code_is_a_sensitive_tool():
    tool = RunCodeTool()

    assert isinstance(tool, SensitiveTool)
    assert tool.requires_confirmation is True
    assert tool.parameters_schema["required"] == ["code"]


def test_command_isolates_the_container():
    command = RunCodeTool(image="img:1")._command("box")

    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--user") + 1] != "0"
    assert "-v" not in command and "--volume" not in command
    assert command[-4:] == ["img:1", "python", "-I", "-"]


def test_preview_shows_every_line_as_added():
    diff = RunCodeTool().preview(code="print(1)\nprint(2)")

    lines = parse_diff(diff)
    assert [(line.kind, line.text) for line in lines] == [
        ("add", "print(1)"),
        ("add", "print(2)"),
    ]


def test_preview_rejects_non_string_code():
    assert RunCodeTool().preview(code=None) is None


@pytest.mark.parametrize("code", [None, "", "  \n", 3])
async def test_empty_or_invalid_code_is_rejected(code):
    result = await RunCodeTool().execute(code=code)

    assert result == "Error: code must be a non-empty string"


@pytest.mark.parametrize(
    ("timeout", "message"),
    [
        ("5", "Error: timeout must be a number"),
        (True, "Error: timeout must be a number"),
        (0, "Error: timeout must be positive"),
        (-1, "Error: timeout must be positive"),
    ],
)
async def test_invalid_timeout_is_rejected(timeout, message):
    assert await RunCodeTool().execute(code="pass", timeout=timeout) == message


async def test_stdout_and_exit_code_are_returned(tmp_path):
    docker = fake_docker(
        tmp_path, RUN_SCRIPT + "print('got:', sys.stdin.read().strip())"
    )

    result = await RunCodeTool(docker_bin=docker).execute(code="print(40 + 2)")

    assert result == "exit code: 0\nstdout:\ngot: print(40 + 2)\n\nstderr:\n(empty)"


async def test_traceback_and_nonzero_exit_reach_the_model(tmp_path):
    body = RUN_SCRIPT + (
        "sys.stderr.write('Traceback (most recent call last):\\n"
        "ZeroDivisionError: division by zero\\n')\nsys.exit(1)"
    )

    result = await RunCodeTool(docker_bin=fake_docker(tmp_path, body)).execute(
        code="1/0"
    )

    assert result.startswith("exit code: 1\nstdout:\n(empty)\nstderr:\n")
    assert "ZeroDivisionError: division by zero" in result


async def test_long_output_is_truncated(tmp_path):
    body = RUN_SCRIPT + f"print('x' * {MAX_OUTPUT_CHARS * 3})"

    result = await RunCodeTool(docker_bin=fake_docker(tmp_path, body)).execute(
        code="pass"
    )

    assert "more chars]" in result
    assert len(result) < MAX_OUTPUT_CHARS + 200


async def test_timeout_kills_the_container(tmp_path):
    body = RUN_SCRIPT + "import time\ntime.sleep(30)"
    docker = fake_docker(tmp_path, body)

    result = await RunCodeTool(docker_bin=docker).execute(
        code="while 1: pass", timeout=0.5
    )

    assert result == "Error: timed out after 0.5s and was killed"
    killed = Path(docker + ".killed").read_text()
    assert killed.startswith("sensai-sandbox-")


async def test_timeout_is_capped(tmp_path):
    body = RUN_SCRIPT + "import time\ntime.sleep(0.1)"
    tool = RunCodeTool(docker_bin=fake_docker(tmp_path, body))

    result = await tool.execute(code="pass", timeout=10**6)

    assert result.startswith("exit code: 0")
    assert MAX_TIMEOUT == 60.0


async def test_missing_docker_is_reported(tmp_path):
    tool = RunCodeTool(docker_bin=str(tmp_path / "no-such-docker"))

    result = await tool.execute(code="print(1)")

    assert result.startswith("Error: sandbox unavailable, could not start Docker")


async def test_docker_failure_is_not_mistaken_for_a_script_error(tmp_path):
    body = RUN_SCRIPT + (
        "sys.stderr.write('Cannot connect to the Docker daemon')\nsys.exit(125)"
    )

    result = await RunCodeTool(docker_bin=fake_docker(tmp_path, body)).execute(
        code="print(1)"
    )

    assert result == "Error: sandbox unavailable: Cannot connect to the Docker daemon"


@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("SENSAI_LIVE_SANDBOX"),
    reason="set SENSAI_LIVE_SANDBOX=1 (needs Docker and the python:3.12-alpine image)",
)
class TestLive:
    async def test_runs_code_in_a_container(self):
        result = await RunCodeTool().execute(code="print(6 * 7)")

        assert result == "exit code: 0\nstdout:\n42\n\nstderr:\n(empty)"

    async def test_traceback_is_captured(self):
        result = await RunCodeTool().execute(code="1/0")

        assert "exit code: 1" in result
        assert "ZeroDivisionError" in result

    async def test_network_is_cut(self):
        code = "import socket\nsocket.create_connection(('1.1.1.1', 53), 2)"

        result = await RunCodeTool().execute(code=code)

        assert "exit code: 1" in result

    async def test_host_files_are_invisible(self, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("host-only")
        code = f"import os\nprint(os.path.exists({str(secret)!r}))"

        result = await RunCodeTool().execute(code=code)

        assert result == "exit code: 0\nstdout:\nFalse\n\nstderr:\n(empty)"

    async def test_filesystem_is_read_only(self):
        result = await RunCodeTool().execute(code="open('/x', 'w')")

        assert "exit code: 1" in result

    async def test_infinite_loop_is_killed(self):
        result = await RunCodeTool().execute(code="while True: pass", timeout=2)

        assert "timed out" in result
