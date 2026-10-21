"""Session parts built from settings, at start-up and again when a setting changes."""

from pathlib import Path
from typing import TYPE_CHECKING

from sensai.core.config import GuardrailsConfig, PersonaConfig
from sensai.core.settings import SETTINGS, get_value
from sensai.domain.models import Persona
from sensai.domain.protocols import Guardrail
from sensai.eval.guardrails import RegexGuardrail
from sensai.eval.logger import PromptLogger, ReplyLogger

if TYPE_CHECKING:
    from sensai.core.commands import CommandContext

PROVIDER_KEYS = {"provider", "model", "base_url", "api_key"}
RESTART_NOTE = "applies on the next start"
REASONING_ATTRIBUTES = {
    "reasoning.enabled": "reasoning",
    "reasoning.max_steps": "max_steps",
    "reasoning.think": "think",
}


class BootstrapError(Exception):
    """Raised when optional session components cannot be initialized."""


def load_persona(config: PersonaConfig) -> Persona | None:
    """Build the configured persona, reading its file if it has one."""
    if config.file is not None:
        try:
            instruction = Path(config.file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise BootstrapError(f"Could not read persona file: {exc}") from exc
        source = config.file
    elif config.instruction is not None:
        instruction, source = config.instruction.strip(), "sensai.toml"
    else:
        return None
    if not instruction:
        raise BootstrapError(f"Persona instruction is empty ({source}).")
    return Persona(
        id=config.name,
        name=config.name,
        description=f"from {source}",
        system_instruction=instruction,
    )


def build_guardrail(config: GuardrailsConfig) -> Guardrail | None:
    if not config.enabled:
        return None
    return RegexGuardrail(injection_action=config.injection, pii_action=config.pii)


def _rebuild_provider(context: "CommandContext") -> None:
    config = context.config
    context.engine.provider = context.provider_factory(
        config.provider,
        model=config.model,
        base_url=config.base_url,
        api_key=config.api_key,
        options=config.options,
    )


def _rebuild_tools(context: "CommandContext") -> None:
    registry = context.tool_registry_factory(context.config.tools.fs_allowed_root)
    context.tool_registry = registry
    context.engine.registry = registry


def apply_setting(context: "CommandContext", key: str) -> str | None:
    """Push the new value of `key` into the running session.

    Returns a note for the user when the setting only applies on the next start.
    Raises BootstrapError or ProviderError when the session cannot use the value;
    the caller then restores the previous one.
    """
    config, engine = context.config, context.engine
    section = key.partition(".")[0]
    if key in PROVIDER_KEYS:
        _rebuild_provider(context)
    elif section == "tools":
        _rebuild_tools(context)
    elif section == "guardrails":
        engine.guardrail = build_guardrail(config.guardrails)
    elif key == "persona.enabled":
        if engine.persona is None:
            engine.persona = load_persona(config.persona)
        engine.persona_enabled = config.persona.enabled
    elif section == "persona":
        engine.persona = load_persona(config.persona)
    elif key in REASONING_ATTRIBUTES:
        setattr(engine, REASONING_ATTRIBUTES[key], get_value(config, key))
    elif key == "memory.auto_inject":
        engine.memory_auto_inject = config.memory.auto_inject
    elif section == "eval":
        engine.recorder = (
            ReplyLogger(config.eval.replies_path) if config.eval.log_replies else None
        )
        engine.prompt_recorder = (
            PromptLogger(config.eval.prompts_path) if config.eval.log_prompts else None
        )
    return RESTART_NOTE if SETTINGS[key].restart else None
