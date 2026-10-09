import re
from dataclasses import dataclass
from typing import Literal

from rich.text import Text

from sensai.domain.models import ToolCall

DIFF_MAX_LINES = 20

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class DiffLine:
    kind: Literal["add", "remove", "context", "gap"]
    number: int | None
    text: str


def parse_diff(diff: str) -> list[DiffLine]:
    """Turn a unified diff into numbered lines: new numbers for added and kept
    lines, old numbers for removed ones, a gap between hunks."""
    lines: list[DiffLine] = []
    old = new = 0
    in_hunk = False
    for raw in diff.splitlines():
        match = _HUNK.match(raw)
        if match:
            if lines:
                lines.append(DiffLine("gap", None, "⋮"))
            old, new = int(match[1]), int(match[2])
            in_hunk = True
        elif not in_hunk or raw.startswith("\\"):
            continue  # file headers and "\ No newline at end of file"
        elif raw.startswith("+"):
            lines.append(DiffLine("add", new, raw[1:]))
            new += 1
        elif raw.startswith("-"):
            lines.append(DiffLine("remove", old, raw[1:]))
            old += 1
        else:
            lines.append(DiffLine("context", new, raw[1:]))
            old += 1
            new += 1
    return lines


_STYLES = {
    "add": ("+", "green"),
    "remove": ("-", "red"),
    "context": (" ", "dim"),
    "gap": (" ", "dim"),
}


def diff_text(tc: ToolCall, max_lines: int = DIFF_MAX_LINES) -> Text | None:
    """Claude Code style block for a pending tool call, or None without preview."""
    if tc.preview is None:
        return None
    lines = parse_diff(tc.preview)
    added = sum(line.kind == "add" for line in lines)
    removed = sum(line.kind == "remove" for line in lines)

    target = tc.arguments.get("path", "")
    text = Text()
    text.append("● ", style="bold #bb9af7")
    text.append(f"{tc.name}", style="bold")
    text.append(f"({target})\n" if target else "\n")
    if not lines:
        text.append("  ⎿  No changes\n", style="dim")
        return text
    text.append(f"  ⎿  +{added} ", style="green")
    text.append(f"-{removed}\n", style="red")

    shown = lines[:max_lines]
    width = max(
        (len(str(line.number)) for line in shown if line.number is not None),
        default=1,
    )
    for line in shown:
        sign, style = _STYLES[line.kind]
        number = "" if line.number is None else str(line.number)
        text.append(f"     {number.rjust(width)} ", style="dim")
        text.append(f"{sign} {line.text}\n", style=style)
    hidden = len(lines) - len(shown)
    if hidden:
        text.append(f"     … {hidden} more lines\n", style="dim italic")
    return text
