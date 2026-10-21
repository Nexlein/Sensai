"""Reads and edits a TOML config file in place, keeping the user's comments and layout."""

import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument


class ConfigError(Exception):
    """Raised when a config file exists but cannot be parsed, validated or written."""


def read_document(path: Path) -> TOMLDocument:
    """The parsed file, or an empty document when it does not exist yet."""
    if not path.exists():
        return tomlkit.document()
    try:
        return tomlkit.parse(path.read_text(encoding="utf-8"))
    except TOMLKitError as exc:
        raise ConfigError(f"Malformed config file {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config file {path}: {exc}") from exc


def flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """`{"a": {"b": 1}}` as `{"a.b": 1}`; lists and scalars are leaves."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            flat.update(flatten(value, f"{name}."))
        else:
            flat[name] = value
    return flat


def file_values(path: Path) -> dict[str, Any]:
    """Every leaf the file sets, by dotted key, as plain Python values."""
    return flatten(read_document(path).unwrap())


def _parent(document: TOMLDocument, parts: list[str], create: bool) -> Any:
    """The table holding the last part of a dotted key, or None when missing."""
    node: Any = document
    for part in parts[:-1]:
        if part not in node:
            if not create:
                return None
            node[part] = tomlkit.table(is_super_table=len(parts) > 2)
        node = node[part]
        if not isinstance(node, Mapping):
            return None
    return node


def _prune(document: TOMLDocument, parts: list[str]) -> None:
    """Drop the tables left empty after a removal, innermost first."""
    for depth in range(len(parts) - 1, 0, -1):
        holder = _parent(document, parts[:depth], create=False)
        name = parts[depth - 1]
        if holder is None or name not in holder:
            continue
        table = holder[name]
        if isinstance(table, Table) and not table.unwrap():
            del holder[name]


def update_file(
    path: Path, values: Mapping[str, Any], removed: Iterable[str] = ()
) -> None:
    """Set each dotted key of `values` and drop each key of `removed`.

    Everything else in the file (comments, order, unknown keys) is kept. The file
    is replaced atomically so a crash never leaves it half written.
    """
    document = read_document(path)
    for key, value in values.items():
        parts = key.split(".")
        parent = _parent(document, parts, create=True)
        if parent is None:
            raise ConfigError(f"Cannot write {key}: a parent key is not a table")
        parent[parts[-1]] = value
    for key in removed:
        parts = key.split(".")
        parent = _parent(document, parts, create=False)
        if parent is not None and parts[-1] in parent:
            del parent[parts[-1]]
            _prune(document, parts)
    write_text(path, tomlkit.dumps(document))


def write_text(path: Path, text: str) -> None:
    """Write `text` to `path` through a temporary file and an atomic rename."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            if path.exists():
                os.chmod(temp, path.stat().st_mode)
            os.replace(temp, path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise ConfigError(f"Could not write config file {path}: {exc}") from exc
