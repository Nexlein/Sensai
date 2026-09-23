import asyncio
from collections.abc import AsyncIterator, Callable

import httpx
from rich.console import Console
from rich.live import Live
from rich.text import Text

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent

SendFn = Callable[[str], AsyncIterator[Event]]


def error_text(exc: Exception) -> str:
    if isinstance(exc, EmptyInputError):
        return "Empty input — please enter a message before sending."
    if isinstance(exc, ProviderError):
        if isinstance(exc.__cause__, httpx.ConnectError):
            return "Connection failed — could not connect to the model server."
        return "Model unavailable — the model is unavailable or returned an error."
    return f"Unexpected error — {exc}"


async def _run_chat(send: SendFn) -> None:
    console = Console()
    console.clear()

    while True:
        try:
            text = console.input("[bold blue]you:[/] ")
        except (EOFError, KeyboardInterrupt):
            break

        console.print()
        label = Text("sensai: ", style="bold magenta")
        content = ""
        try:
            with Live(label, console=console, refresh_per_second=15) as live:
                async for chunk_event in send(text):
                    if isinstance(chunk_event, TextChunkEvent):
                        content += chunk_event.content
                        live.update(label + Text(content))
        except (EmptyInputError, ProviderError) as exc:
            console.print(f"[bold red]✗ {error_text(exc)}[/]")


def run_chat(send: SendFn) -> None:
    asyncio.run(_run_chat(send))
