"""Session parts rebuilt from settings while Sensai runs."""

import pytest

from sensai.core.commands import CommandContext
from sensai.core.components import (
    RESTART_NOTE,
    BootstrapError,
    apply_setting,
    build_guardrail,
    load_persona,
)
from sensai.core.config import AppConfig, GuardrailsConfig, PersonaConfig
from sensai.core.engine import ChatEngine
from sensai.domain.models import Conversation
from sensai.eval.guardrails import RegexGuardrail
from sensai.eval.logger import PromptLogger, ReplyLogger
from sensai.providers import get_provider
from sensai.providers.mock import MockLLMProvider
from sensai.tools.registry import ToolRegistry


class FakeMemoryStore:
    async def save(self, conversation: Conversation) -> None:
        return None

    async def load(self, conversation_id: str) -> Conversation | None:
        return None


def _context() -> CommandContext:
    return CommandContext(
        config=AppConfig(),
        engine=ChatEngine(MockLLMProvider(), Conversation()),
        provider_factory=get_provider,
        tool_registry=ToolRegistry(),
        tool_registry_factory=lambda _: ToolRegistry(),
        memory_store=FakeMemoryStore(),
    )


def test_persona_from_an_instruction():
    persona = load_persona(PersonaConfig(name="Collecte", instruction="  Tu es X. "))

    assert persona is not None
    assert persona.system_instruction == "Tu es X."
    assert persona.name == "Collecte"


def test_persona_from_a_file(tmp_path):
    path = tmp_path / "persona.md"
    path.write_text("Tu es Y.\n")

    persona = load_persona(PersonaConfig(file=str(path)))

    assert persona is not None
    assert persona.system_instruction == "Tu es Y."


def test_no_persona_without_a_source():
    assert load_persona(PersonaConfig()) is None


@pytest.mark.parametrize("instruction", ["", "   "])
def test_empty_persona_is_a_bootstrap_error(instruction):
    with pytest.raises(BootstrapError, match="empty"):
        load_persona(PersonaConfig(instruction=instruction))


def test_unreadable_persona_file_is_a_bootstrap_error(tmp_path):
    with pytest.raises(BootstrapError, match="persona file"):
        load_persona(PersonaConfig(file=str(tmp_path / "missing.md")))


def test_guardrail_follows_its_settings():
    guardrail = build_guardrail(GuardrailsConfig(injection="flag", pii="block"))

    assert guardrail == RegexGuardrail(injection_action="flag", pii_action="block")
    assert build_guardrail(GuardrailsConfig(enabled=False)) is None


def test_provider_settings_rebuild_the_provider():
    context = _context()
    context.config.provider = "mock"

    apply_setting(context, "provider")

    assert isinstance(context.engine.provider, MockLLMProvider)
    assert context.engine.provider is not None


def test_tool_settings_rebuild_the_registry():
    context = _context()
    replacement = ToolRegistry()
    roots: list[str | None] = []

    def factory(root: str | None) -> ToolRegistry:
        roots.append(root)
        return replacement

    context.tool_registry_factory = factory
    apply_setting(context, "tools.web_search")

    assert roots == ["."]
    assert context.engine.registry is replacement
    assert context.tool_registry is replacement


def test_guardrail_settings_rebuild_the_guardrail():
    context = _context()
    context.config.guardrails.pii = "block"

    apply_setting(context, "guardrails.pii")

    assert context.engine.guardrail == RegexGuardrail(pii_action="block")


@pytest.mark.parametrize(
    ("key", "value", "attribute"),
    [
        ("reasoning.enabled", False, "reasoning"),
        ("reasoning.max_steps", 2, "max_steps"),
        ("reasoning.think", "high", "think"),
        ("memory.auto_inject", False, "memory_auto_inject"),
    ],
)
def test_engine_settings_apply_to_the_next_turn(key, value, attribute):
    context = _context()
    section, name = key.split(".")
    setattr(getattr(context.config, section), name, value)

    assert apply_setting(context, key) is None
    assert getattr(context.engine, attribute) == value


def test_log_settings_start_and_stop_the_loggers(tmp_path):
    context = _context()
    context.config.eval.log_replies = True
    context.config.eval.replies_path = str(tmp_path / "r.jsonl")
    context.config.eval.log_prompts = True

    apply_setting(context, "eval.log_replies")

    assert isinstance(context.engine.recorder, ReplyLogger)
    assert isinstance(context.engine.prompt_recorder, PromptLogger)

    context.config.eval.log_replies = False
    apply_setting(context, "eval.log_replies")
    assert context.engine.recorder is None


def test_persona_switch_loads_the_persona_once():
    context = _context()
    context.config.persona.instruction = "Tu es Z."
    context.config.persona.enabled = True

    apply_setting(context, "persona.enabled")

    assert context.engine.persona is not None
    assert context.engine.persona_enabled is True


@pytest.mark.parametrize(
    "key", ["interface", "rag.top_k", "memory.enabled", "reasoning.show_thoughts"]
)
def test_settings_read_at_launch_say_they_apply_on_restart(key):
    assert apply_setting(_context(), key) == RESTART_NOTE
