import asyncio
import difflib
import uuid
from typing import Any

from .base import SensitiveTool

DEFAULT_IMAGE = "python:3.15-alpine"
DEFAULT_TIMEOUT = 10.0
MAX_TIMEOUT = 60.0
MAX_OUTPUT_CHARS = 4000


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n… [{len(text) - MAX_OUTPUT_CHARS} more chars]"


class RunCodeTool(SensitiveTool):
    """Run Python in a throwaway Docker container: no network, no host files."""

    name = "run_python"
    description = (
        "Run a Python 3 script in an isolated sandbox (no network, no access to the "
        "user's files, read-only filesystem, limited memory and time) and return its "
        "exit code, stdout and stderr. Use it to compute, test or check code. If the "
        "script fails, read the traceback, fix the code and run it again. "
        "The user must confirm every run."
    )

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        docker_bin: str = "docker",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.image = image
        self.docker_bin = docker_bin
        self.timeout = timeout
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Complete Python 3 source to run. Print results to stdout.",
                },
                "timeout": {
                    "type": "number",
                    "description": f"Seconds before the run is killed (default {DEFAULT_TIMEOUT:g}, max {MAX_TIMEOUT:g}).",
                },
            },
            "required": ["code"],
        }

    def preview(self, code: str, **kwargs: Any) -> str | None:
        """The code to run, as an all-added diff so the UI shows it in full."""
        if not isinstance(code, str):
            return None
        return "\n".join(
            difflib.unified_diff(
                [], code.splitlines(), fromfile="", tofile="", lineterm=""
            )
        )

    def _command(self, container: str) -> list[str]:
        return [
            self.docker_bin,
            "run",
            "--rm",
            "-i",
            "--name",
            container,
            "--network",
            "none",
            "--memory",
            "256m",
            "--memory-swap",
            "256m",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=16m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            self.image,
            "python",
            "-I",
            "-",
        ]

    async def _kill(self, container: str) -> None:
        try:
            killer = await asyncio.create_subprocess_exec(
                self.docker_bin,
                "kill",
                container,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), 10)
        except (OSError, TimeoutError):
            pass

    async def execute(self, **kwargs: Any) -> str:
        code = kwargs.get("code")
        if not isinstance(code, str) or not code.strip():
            return "Error: code must be a non-empty string"
        timeout = kwargs.get("timeout", self.timeout)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            return "Error: timeout must be a number"
        if timeout <= 0:
            return "Error: timeout must be positive"
        timeout = min(float(timeout), MAX_TIMEOUT)

        container = f"sensai-sandbox-{uuid.uuid4().hex[:12]}"
        try:
            process = await asyncio.create_subprocess_exec(
                *self._command(container),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            return f"Error: sandbox unavailable, could not start Docker: {e}"

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(code.encode()), timeout
            )
        except (TimeoutError, asyncio.CancelledError) as e:
            await self._kill(container)
            process.kill()
            await process.wait()
            if isinstance(e, asyncio.CancelledError):
                raise
            return f"Error: timed out after {timeout:g}s and was killed"

        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        if not out and (
            process.returncode in (125, 126, 127)
            or (process.returncode == 255 and err.startswith("exec "))
        ):
            # Docker itself failed (daemon down, image missing, or the runtime
            # refused to start Python, as snap Docker does), not the script.
            return f"Error: sandbox unavailable: {_clip(err.strip())}"
        return (
            f"exit code: {process.returncode}\n"
            f"stdout:\n{_clip(out) or '(empty)'}\n"
            f"stderr:\n{_clip(err) or '(empty)'}"
        )
