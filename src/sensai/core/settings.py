"""Dotted-key access to `AppConfig`, shared by `/config` and `sensai config`.

Every leaf of the schema is a setting (`model`, `options.temperature`, ...), except
the MCP servers, which are edited in the file. A value is parsed like a TOML
literal, validated against the whole config, then assigned in place so the
objects other components hold (the provider's `ModelOptions`, the budget's
`BudgetConfig`) see the change.
"""

import json
import tomllib
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from sensai.core.config import (
    AppConfig,
    ConfigError,
    load_config,
    to_file_value,
    validation_reasons,
)
from sensai.core.config_file import file_values, update_file, write_text

Source = Literal["default", "file", "flag", "session"]
UNSET_WORDS = {"none", "null", "unset"}
SECRET_KEYS = {"api_key"}
_BOUNDS = (("ge", "≥"), ("gt", ">"), ("le", "≤"), ("lt", "<"))


@dataclass(frozen=True)
class Setting:
    """One settable key of the schema."""

    key: str
    kind: str
    default: Any
    description: str
    restart: bool


def _kind(annotation: Any) -> str:
    """Readable type of a field: `bool`, `"cli" | "tui"`, `float | none`."""
    origin = get_origin(annotation)
    if origin is Literal:
        return " | ".join(json.dumps(arg) for arg in get_args(annotation))
    if origin in (Union, types.UnionType):
        return " | ".join(_kind(arg) for arg in get_args(annotation))
    if annotation is type(None):
        return "none"
    return getattr(annotation, "__name__", str(annotation))


def _bounds(info: FieldInfo) -> str:
    return "".join(
        f" {symbol} {getattr(item, name)}"
        for item in info.metadata
        for name, symbol in _BOUNDS
        if getattr(item, name, None) is not None
    )


def _restart(info: FieldInfo) -> bool:
    extra = info.json_schema_extra
    return isinstance(extra, dict) and bool(extra.get("restart"))


def _catalog(
    model: type[BaseModel], defaults: BaseModel, prefix: str = ""
) -> dict[str, Setting]:
    """Settings of `model`; defaults are read from `defaults`, an instance, since a
    section's default can differ from its class defaults (`options.num_ctx`)."""
    settings: dict[str, Setting] = {}
    for name, info in model.model_fields.items():
        key = f"{prefix}{name}"
        annotation = info.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            settings.update(_catalog(annotation, getattr(defaults, name), f"{key}."))
            continue
        if key == "mcp.servers":
            continue
        settings[key] = Setting(
            key=key,
            kind=_kind(annotation) + _bounds(info),
            default=getattr(defaults, name),
            description=info.description or "",
            restart=_restart(info),
        )
    return settings


SETTINGS: dict[str, Setting] = _catalog(AppConfig, AppConfig())


def parse_value(raw: str) -> Any:
    """A TOML literal (`true`, `0.2`, `"x"`, `[1, 2]`) or else the text itself.

    `none`, `null` and `unset` mean "no value" (back to the provider default for
    options, tools off for `tools.fs_allowed_root`).
    """
    text = raw.strip()
    if text.lower() in UNSET_WORDS:
        return None
    try:
        return tomllib.loads(f"value = {text}")["value"]
    except tomllib.TOMLDecodeError:
        return text


def get_value(config: AppConfig, key: str) -> Any:
    node: Any = config
    for part in key.split("."):
        node = getattr(node, part)
    return node


def _candidate(config: AppConfig, key: str, value: Any) -> AppConfig:
    data = config.model_dump()
    *parents, leaf = key.split(".")
    node = data
    for part in parents:
        node = node[part]
    node[leaf] = value
    return AppConfig.model_validate(data)


def validated(config: AppConfig, key: str, raw: str | None) -> AppConfig:
    """The config with `key` set from user text (`None` resets it to its default).

    Raises ConfigError naming the reason when the key is unknown or the value
    breaks a rule, including rules across keys (budget vs `num_ctx`).
    """
    setting = SETTINGS.get(key)
    if setting is None:
        raise ConfigError(f"Unknown config key: {key}")
    if raw is None:
        attempts: list[Any] = [setting.default]
    else:
        parsed = parse_value(raw)
        attempts = [parsed] if parsed == raw.strip() else [parsed, raw.strip()]
    error: ValidationError | None = None
    for value in attempts:
        try:
            return _candidate(config, key, value)
        except ValidationError as exc:
            error = error or exc
    assert error is not None
    raise ConfigError(f"Invalid {key}: {validation_reasons(error)}")


def assign(config: AppConfig, key: str, source: AppConfig) -> None:
    """Copy `key` from `source` into `config`, keeping every nested object in place."""
    *parents, leaf = key.split(".")
    target: Any = config
    origin: Any = source
    for part in parents:
        target, origin = getattr(target, part), getattr(origin, part)
    setattr(target, leaf, getattr(origin, leaf))


def _section(key: str) -> str:
    return key.rpartition(".")[0]


def save_setting(config: AppConfig, key: str, path: Path, reset: bool = False) -> None:
    """Write one setting (or drop it from the file when `reset`).

    The file must still load on its own at the next start. When the key alone
    breaks a rule across keys (an enabled persona needs its text, which may only
    live in the session), the other changed settings of its section are written
    too. If the file still would not load, it is put back as it was and
    ConfigError says why.
    """
    before = path.read_text(encoding="utf-8") if path.exists() else None
    value = to_file_value(key, get_value(config, key))
    if reset or value is None:
        update_file(path, {}, [key])
    else:
        update_file(path, {key: value})
    try:
        load_config(path)
        return
    except ConfigError:
        pass
    related = {
        other: to_file_value(other, get_value(config, other))
        for other, setting in SETTINGS.items()
        if _section(other) == _section(key)
        and other != key
        and get_value(config, other) != setting.default
    }
    update_file(path, {k: v for k, v in related.items() if v is not None})
    try:
        load_config(path)
    except ConfigError as exc:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            write_text(path, before)
        raise ConfigError(f"the file would no longer load ({exc})") from exc


def format_value(key: str, value: Any) -> str:
    if value is None:
        return "(unset)"
    if key in SECRET_KEYS:
        return "***"
    return json.dumps(value, ensure_ascii=False)


def sources(
    config: AppConfig, path: Path | None, unsaved: set[str] = frozenset()
) -> dict[str, Source]:
    """Where each current value comes from.

    `session`: changed in this session and not written yet. `file`: the file sets
    it. `flag`: differs from both the file and the default, so a CLI flag set it.
    """
    in_file = file_values(path) if path is not None else {}
    found: dict[str, Source] = {}
    for key, setting in SETTINGS.items():
        value = get_value(config, key)
        if key in unsaved:
            found[key] = "session"
        elif key in in_file and in_file[key] == to_file_value(key, value):
            found[key] = "file"
        elif value != setting.default:
            found[key] = "flag"
        else:
            found[key] = "default"
    return found


def _matching(prefix: str | None) -> list[str]:
    if not prefix:
        return list(SETTINGS)
    keys = [key for key in SETTINGS if key == prefix or key.startswith(f"{prefix}.")]
    if not keys:
        raise ConfigError(f"Unknown config key: {prefix}")
    return keys


def _grouped(keys: list[str]) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = {}
    for key in keys:
        groups.setdefault(_section(key), []).append(key)
    return list(groups.items())


def format_settings(
    config: AppConfig,
    found: dict[str, Source],
    prefix: str | None = None,
) -> str:
    """Current values as TOML-like sections, each line tagged with its source."""
    keys = _matching(prefix)
    lines: list[str] = []
    for section, members in _grouped(keys):
        if section:
            lines.extend(["", f"[{section}]"])
        rows = [
            (key.rpartition(".")[2], format_value(key, get_value(config, key)), key)
            for key in members
        ]
        width = max(len(f"{name} = {value}") for name, value, _ in rows)
        lines.extend(
            f"{f'{name} = {value}':<{width}}  {found.get(key, 'default')}"
            for name, value, key in rows
        )
    return "\n".join(lines).strip("\n")


def format_keys(prefix: str | None = None) -> str:
    """Every setting with its type, default and meaning."""
    lines = []
    for key in _matching(prefix):
        setting = SETTINGS[key]
        restart = " (restart)" if setting.restart else ""
        lines.append(
            f"{key}: {setting.kind} = {format_value(key, setting.default)}{restart}"
            f"\n    {setting.description}"
        )
    return "\n".join(lines)


def template() -> str:
    """A documented `sensai.toml` with every setting commented out at its default."""
    lines = [
        "# Sensai configuration. Precedence: CLI flags > this file > defaults.",
        "# Every setting is listed at its default value: uncomment a line to change it.",
        "# Inside Sensai, `/config set <key> <value>` edits this file for you.",
    ]
    for section, members in _grouped(list(SETTINGS)):
        lines.append("")
        if section:
            lines.append(f"[{section}]")
        for key in members:
            setting = SETTINGS[key]
            name = key.rpartition(".")[2]
            restart = " Applies on the next start." if setting.restart else ""
            lines.append(f"# {setting.description}.{restart}")
            stored = to_file_value(key, setting.default)
            example = (
                "..." if stored is None else json.dumps(stored, ensure_ascii=False)
            )
            lines.append(f"# {name} = {example}")
    lines.extend(
        [
            "",
            "# MCP servers, one table each (tools appear as <name>__<tool>):",
            "# [mcp.servers.github]",
            '# command = "docker"',
            '# args = ["run", "-i", "--rm", "ghcr.io/github/github-mcp-server", "stdio"]',
            "# timeout = 30.0",
        ]
    )
    return "\n".join(lines) + "\n"
