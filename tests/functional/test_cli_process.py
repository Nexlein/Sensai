"""The installed CLI as a user runs it: a real process, piped stdin, exit code."""

import subprocess
import sys

RUN_SENSAI = "import sys; from sensai import main; sys.argv[0] = 'sensai'; main()"


def sensai(workspace, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", RUN_SENSAI, *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=workspace,
        timeout=60,
        check=False,
        env={"PATH": "/usr/bin:/bin", "COLUMNS": "200", "NO_COLOR": "1"},
    )


def test_cli_chats_runs_a_command_and_exits_cleanly(workspace):
    done = sensai(
        workspace,
        "chat",
        "--provider",
        "mock",
        "--session",
        "demo",
        stdin="bonjour\n/help\n/exit\n",
    )

    assert done.returncode == 0, done.stderr
    assert "This is a mocked response from SENSAI." in done.stdout
    assert "/exit" in done.stdout  # listed by /help
    assert "Traceback" not in done.stdout + done.stderr
    assert (workspace / ".sensai" / "sensai.db").exists()  # session persisted


def test_cli_stops_at_end_of_input(workspace):
    done = sensai(workspace, "chat", "--provider", "mock", stdin="bonjour\n")

    assert done.returncode == 0, done.stderr


def test_cli_reports_a_bad_provider_in_one_line(workspace):
    done = sensai(workspace, "chat", "--provider", "nope")

    assert done.returncode == 1
    assert "Unknown provider 'nope'" in done.stdout
    assert "Traceback" not in done.stdout + done.stderr


def test_cli_reports_a_broken_config_file_in_one_line(workspace):
    (workspace / "broken.toml").write_text("provider = \n", encoding="utf-8")

    done = sensai(workspace, "chat", "--config", "broken.toml")

    assert done.returncode == 1
    assert "Traceback" not in done.stdout + done.stderr
