"""Session harness shared by the functional and live suites.

`start_session` wires config, tools, memory, guardrails and persistence exactly as
the CLI does, through `build_session`. `say` sends one input through
`process_input`, the entry point every frontend shares, and keeps what it produced.
"""

import textwrap
import time
from collections import Counter, defaultdict
from pathlib import Path
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from sensai.core.bootstrap import build_session
from sensai.core.commands import CommandContext, CommandResult
from sensai.core.input import process_input
from sensai.domain.events import (
    Event,
    GuardrailEvent,
    MaxStepsEvent,
    TextChunkEvent,
    ThoughtEvent,
    ToolCallEvent,
)
from sensai.domain.models import ToolCall


@dataclass
class Exchange:
    """Everything one input produced, as a frontend would have seen it."""

    prompt: str
    result: CommandResult
    events: list[Event] = field(default_factory=list)
    confirmations: list[ToolCall] = field(default_factory=list)
    # One per tool call, in order, as stored in the history (so after guardrails).
    tool_results: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(e.content for e in self.events if isinstance(e, TextChunkEvent))

    @property
    def tool_calls(self) -> list[ToolCallEvent]:
        return self.of(ToolCallEvent)

    def of(self, kind: type[Event]) -> list:
        return [e for e in self.events if isinstance(e, kind)]

    def transcript(self) -> str:
        """The exchange as a live test prints it: enough to tell why an answer failed."""
        lines = [f"user: {self.prompt}"]
        results = iter(self.tool_results)
        for event in self.events:
            if isinstance(event, ThoughtEvent):
                lines.append(f"  thought: {_clip(event.content)}")
            elif isinstance(event, ToolCallEvent):
                lines.append(f"  tool {event.tool_name}({event.arguments})")
                result = next(results, None)
                if result is not None:
                    lines.append(f"    -> {_clip(result)}")
            elif isinstance(event, GuardrailEvent):
                lines.append(
                    f"  guardrail {event.stage} {event.action}: {event.reason}"
                )
            elif isinstance(event, MaxStepsEvent):
                lines.append(f"  max steps reached ({event.max_steps})")
        lines.append(f"sensai: {self.text or self.result.message or '(no answer)'}")
        return "\n".join(lines)


def _clip(text: str, limit: int = 300) -> str:
    """One line, at most `limit` chars."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


@pytest.fixture
def today(monkeypatch):
    """Freeze the date the prompt gives the model: Monday 2026-10-26."""

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 26)

    monkeypatch.setattr("sensai.core.prompt.date", FrozenDate)
    return FrozenDate.today()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Empty project dir and cwd: `.sensai/`, logs and the fs root land here."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
async def start_session(workspace):
    """Factory: `await start_session(config_toml, provider=None, **build_args)`.

    A given `provider` replaces the configured one after the build.
    """
    opened: list[CommandContext] = []

    async def start(config: str, provider=None, **kwargs) -> CommandContext:
        path = workspace / "sensai.toml"
        path.write_text(textwrap.dedent(config), encoding="utf-8")
        context = await build_session(config_path=path, **kwargs)
        if provider is not None:
            context.engine.provider = provider
        opened.append(context)
        return context

    yield start
    for context in opened:
        await context.aclose()


@pytest.fixture
def say():
    """`await say(context, text, approve=True)`: one input, as typed by the user."""

    async def say_(context: CommandContext, text: str, approve: bool = True):
        exchange = Exchange(prompt=text, result=CommandResult())

        async def render(events):
            async for event in events:
                exchange.events.append(event)

        async def confirm(tc: ToolCall) -> bool:
            exchange.confirmations.append(tc)
            return approve

        seen = {m.id for m in context.engine.conversation.messages}
        exchange.result = await process_input(context, text, render, confirm)
        exchange.tool_results = [
            m.content
            for m in context.engine.conversation.messages
            if m.role == "tool" and m.id not in seen
        ]
        return exchange

    return say_


@pytest.fixture
def route_search(monkeypatch):
    """`route_search(handler)`: send the web_search tool's HTTP calls to `handler`.

    Only `sensai.tools.web` sees the swap; the model's own client is untouched.
    """

    def route(handler) -> None:
        real_client = httpx.AsyncClient

        class SearchHttpx:
            def __getattr__(self, name):
                return getattr(httpx, name)

            @staticmethod
            def AsyncClient(*args, **kwargs):
                transport = httpx.MockTransport(handler)
                return real_client(*args, transport=transport, **kwargs)

        monkeypatch.setattr("sensai.tools.web.httpx", SearchHttpx())

    return route


@pytest.fixture
def searxng(route_search):
    """Fake SearXNG answering every query with `searxng.results`; queries recorded."""
    fake = SimpleNamespace(
        results=[
            {
                "title": "Python 3.15 released",
                "url": "https://www.python.org/downloads/release/python-3150/",
                "content": "Python 3.15.0 is the newest major release.",
            }
        ],
        queries=[],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        fake.queries.append(request.url.params["q"])
        return httpx.Response(200, json={"results": fake.results})

    route_search(handler)
    return fake


MARKS = {
    "passed": ("✓", "PASS", {"green": True}),
    "failed": ("✗", "FAIL", {"red": True, "bold": True}),
    "error": ("✗", "ERROR", {"red": True, "bold": True}),
    "skipped": ("–", "SKIP", {"yellow": True}),
    "xfailed": ("~", "XFAIL", {"yellow": True}),
    "xpassed": ("!", "XPASS", {"red": True}),
}
SLOW_SECONDS = 0.5


@dataclass
class Outcome:
    nodeid: str
    module: str
    title: str
    status: str
    seconds: float
    reason: str = ""


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("sensai")
    group.addoption(
        "--classic", action="store_true", help="Plain pytest output, no titles"
    )
    group.addoption(
        "--test-report",
        default=None,
        metavar="PATH",
        help="Also write every test title and result as Markdown to PATH",
    )


def _first_line(doc: str | None) -> str:
    if not doc or not doc.strip():
        return ""
    return doc.strip().splitlines()[0].strip().rstrip(".")


def _humanize(name: str) -> str:
    words = name.removeprefix("test_").replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def test_title(item: pytest.Item) -> str:
    function = getattr(item, "function", None)
    name = getattr(item, "originalname", None) or item.name.split("[")[0]
    title = _first_line(getattr(function, "__doc__", None)) or _humanize(name)
    parent = getattr(item, "cls", None)
    if parent is not None:
        title = f"{_humanize(parent.__name__.removeprefix('Test'))} › {title}"
    callspec = getattr(item, "callspec", None)
    if callspec is not None:
        label = callspec.id if len(callspec.id) <= 40 else callspec.id[:39] + "…"
        title += f" [{label}]"
    return title


def module_title(item: pytest.Item) -> str:
    path = Path(item.nodeid.split("::")[0])
    doc = _first_line(getattr(getattr(item, "module", None), "__doc__", None))
    location = "/".join(path.with_suffix("").parts[1:]).replace("test_", "")
    return f"{location} — {doc}" if doc else location


def _status(report: pytest.TestReport) -> str | None:
    if hasattr(report, "wasxfail"):
        return "xfailed" if report.skipped else "xpassed"
    if report.when == "call":
        return report.outcome
    if report.failed:
        return "error"
    if report.skipped and report.when == "setup":
        return "skipped"
    return None


def _reason(report: pytest.TestReport) -> str:
    if report.skipped and isinstance(report.longrepr, tuple):
        return str(report.longrepr[2]).removeprefix("Skipped: ")
    if report.failed:
        crash = getattr(report.longrepr, "reprcrash", None)
        return crash.message.splitlines()[0] if crash is not None else ""
    return ""


class SpecReporter:
    """Prints one line per test instead of pytest's dots."""

    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.terminal = config.pluginmanager.getplugin("terminalreporter")
        self.titles: dict[str, tuple[str, str]] = {}
        self.outcomes: list[Outcome] = []
        self.current_module: str | None = None
        self.started = time.perf_counter()

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        self.titles = {
            item.nodeid: (module_title(item), test_title(item)) for item in items
        }

    @pytest.hookimpl(tryfirst=True)
    def pytest_report_teststatus(self, report: pytest.TestReport):
        status = _status(report)
        if status is None:
            return ("", "", "")
        word = {"xfailed": "XFAIL", "xpassed": "XPASS"}.get(status, status.upper())
        return (status, "", word)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        status = _status(report)
        if status is None:
            return
        module, title = self.titles.get(report.nodeid, (report.fspath, report.nodeid))
        outcome = Outcome(
            report.nodeid, module, title, status, report.duration, _reason(report)
        )
        self.outcomes.append(outcome)
        tw = self.terminal
        if module != self.current_module:
            self.current_module = module
            tw.ensure_newline()
            tw.write_line("")
            tw.write_line(module, bold=True)
        symbol, _, markup = MARKS[status]
        tw.write(f"  {symbol} ", **markup)
        tw.write(title)
        if outcome.seconds >= SLOW_SECONDS:
            tw.write(f"  ({outcome.seconds:.2f} s)", yellow=True)
        if outcome.reason:
            tw.write(f"  — {outcome.reason}", **markup)
        tw.write("\n")

    def pytest_terminal_summary(self, terminalreporter) -> None:
        if not self.outcomes:
            return
        areas: dict[str, Counter[str]] = defaultdict(Counter)
        for outcome in self.outcomes:
            parts = Path(outcome.nodeid.split("::")[0]).parts
            area = parts[1] if len(parts) > 2 else "package"
            areas[area][outcome.status] += 1
        tw = terminalreporter
        tw.write_sep("=", "results by area")
        for area, counts in sorted(areas.items()):
            failed = counts["failed"] + counts["error"]
            line = (
                f"  {area:<12} {counts['passed']:>4} passed"
                f"  {failed:>3} failed  {counts['skipped']:>3} skipped"
            )
            tw.write_line(line, red=bool(failed), green=not failed)
        path = self.config.getoption("--test-report")
        if path:
            write_markdown(
                Path(path), self.outcomes, time.perf_counter() - self.started
            )
            tw.write_line(f"  report written to {path}")


def write_markdown(path: Path, outcomes: list[Outcome], seconds: float) -> None:
    """Every test with its title and result, one table per file."""
    totals = Counter(outcome.status for outcome in outcomes)
    lines = [
        "# Test report",
        "",
        f"{len(outcomes)} tests in {seconds:.1f} s: "
        + ", ".join(f"{count} {status}" for status, count in sorted(totals.items())),
        "",
    ]
    by_module: dict[str, list[Outcome]] = defaultdict(list)
    for outcome in outcomes:
        by_module[outcome.module].append(outcome)
    for module, members in by_module.items():
        lines.extend(
            [f"## {module}", "", "| Result | Test | Time |", "| --- | --- | --- |"]
        )
        for outcome in members:
            symbol, word, _ = MARKS[outcome.status]
            note = f" — {outcome.reason}" if outcome.reason else ""
            title = (outcome.title + note).replace("|", "\\|")
            lines.append(f"| {symbol} {word} | {title} | {outcome.seconds:.2f} s |")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    terminal = config.pluginmanager.getplugin("terminalreporter")
    plain = config.getoption("--classic") or config.get_verbosity() != 0
    if terminal is None or plain or hasattr(config, "workerinput"):
        return
    terminal.showfspath = False
    terminal._show_progress_info = False
    config.pluginmanager.register(SpecReporter(config), "sensai-spec-reporter")
