"""Live suite: a real Ollama model behind a real session (see tests/conftest.py).

Skipped unless SENSAI_OLLAMA_TEST_MODEL names a pulled model:

    SENSAI_OLLAMA_TEST_MODEL=qwen3.5:4b make test-live

Optional: SENSAI_OLLAMA_BASE_URL (default http://localhost:11434),
SENSAI_LIVE_SANDBOX=1 to run `run_python` in Docker instead of a stub,
SENSAI_LIVE_SEARXNG=1 for the test against the real SearXNG of compose.yaml.

Sampling is pinned (temperature 0, fixed seed) so reruns mostly agree, but these
tests grade a model, not our code: a failure is a finding about the model or the
prompt. Every test prints its transcript; `-rA` shows it even when it passes.
"""

import os

import pytest

from sensai.core.config import DEFAULT_BASE_URL
from sensai.tools.sandbox import RunCodeTool


class RecordingSandbox(RunCodeTool):
    """`run_python` that records the code; with `stdout`, answers without Docker."""

    def __init__(self, stdout: str | None) -> None:
        super().__init__()
        self.stdout = stdout
        self.codes: list[str] = []

    async def execute(self, **kwargs) -> str:
        self.codes.append(str(kwargs.get("code", "")))
        if self.stdout is None:
            return await super().execute(**kwargs)
        return f"exit code: 0\nstdout:\n{self.stdout}\nstderr:\n(empty)"


@pytest.fixture
def live_model() -> str:
    model = os.environ.get("SENSAI_OLLAMA_TEST_MODEL")
    if not model:
        pytest.skip("set SENSAI_OLLAMA_TEST_MODEL to test a real local model")
    return model


@pytest.fixture
def live_session(start_session, live_model):
    """Factory: `await live_session(sections="[rag]\\n...")` on the real model.

    `sections` must only hold TOML tables: top-level keys are set here.
    """

    async def open_(sections: str = "", **kwargs):
        base_url = os.environ.get("SENSAI_OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        config = (
            f'provider = "ollama"\nmodel = "{live_model}"\nbase_url = "{base_url}"\n'
            + sections
            + "\n[options]\ntemperature = 0\nseed = 42\n"
        )
        return await start_session(config, **kwargs)

    return open_


@pytest.fixture
def sandbox():
    """`sandbox(context, stdout)`: swap in a `RecordingSandbox`, stubbed unless
    SENSAI_LIVE_SANDBOX is set (then the code really runs in Docker)."""

    def install(context, stdout: str) -> RecordingSandbox:
        real = bool(os.environ.get("SENSAI_LIVE_SANDBOX"))
        tool = RecordingSandbox(None if real else stdout)
        context.tool_registry.register(tool)
        return tool

    return install
