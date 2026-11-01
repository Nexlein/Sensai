"""Functional tests: a real session (see tests/conftest.py), a scripted model."""

import pytest

from sensai.providers.mock import ScriptedLLMProvider


@pytest.fixture
def open_session(start_session):
    """Factory: `await open_session(*rounds, config="...")`, model replaying `rounds`."""

    async def open_(*rounds, config: str = "", **kwargs):
        return await start_session(
            'provider = "mock"\n' + config,
            provider=ScriptedLLMProvider(*rounds),
            **kwargs,
        )

    return open_
