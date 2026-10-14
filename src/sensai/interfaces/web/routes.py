"""HTTP page and websocket chat endpoint over a shared Sensai session."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from sensai.core.commands import CommandContext
from sensai.core.input import process_input
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import BudgetEvent, Event, GuardrailEvent, TextChunkEvent
from sensai.domain.models import ToolCall
from sensai.interfaces.notices import error_text, guardrail_notice
from sensai.interfaces.prompts import tool_confirmation
from sensai.interfaces.usage import format_usage

INDEX_PATH = Path(__file__).parent / "index.html"


def history_payload(context: CommandContext) -> dict[str, Any]:
    """Past user and assistant messages, so a reload shows the resumed session."""
    messages = [
        {"role": m.role, "content": m.content}
        for m in context.engine.conversation.messages
        if m.role in ("user", "assistant") and m.content
    ]
    return {"type": "history", "messages": messages}


def event_payload(event: Event) -> dict[str, Any] | None:
    """Wire form of an engine event; None for events the page does not show."""
    if isinstance(event, TextChunkEvent):
        return {"type": "text_chunk", "content": event.content}
    if isinstance(event, GuardrailEvent):
        return {"type": "notice", "message": guardrail_notice(event)}
    return None


class WebTurn:
    """One websocket connection: runs a turn at a time and relays confirmations."""

    def __init__(self, context: CommandContext, websocket: WebSocket) -> None:
        self.context = context
        self.websocket = websocket
        self._task: asyncio.Task[None] | None = None
        self._confirmation: asyncio.Future[bool] | None = None

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    async def handle(self, data: dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "message":
            await self._start(str(data.get("text", "")))
        elif kind == "confirm":
            if self._confirmation is not None and not self._confirmation.done():
                self._confirmation.set_result(bool(data.get("approved")))
        elif kind == "stop" and self.busy and self._task is not None:
            self._task.cancel()

    async def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _start(self, text: str) -> None:
        if self.busy:
            await self.websocket.send_json(
                {"type": "error", "message": "A reply is already in progress."}
            )
            return
        self._task = asyncio.create_task(self._run(text))

    async def _render(self, events: AsyncIterator[Event]) -> None:
        usage: BudgetEvent | None = None
        try:
            async for event in events:
                if isinstance(event, BudgetEvent):
                    usage = event  # the engine reports it per chunk; show the last
                    continue
                payload = event_payload(event)
                if payload is not None:
                    await self.websocket.send_json(payload)
        finally:
            if usage is not None:
                await self.websocket.send_json(
                    {"type": "usage", "message": format_usage(usage)}
                )

    async def _confirm_tool(self, tc: ToolCall) -> bool:
        question = tool_confirmation(tc)
        loop = asyncio.get_running_loop()
        self._confirmation = loop.create_future()
        await self.websocket.send_json(
            {
                "type": "confirm",
                "title": question.title,
                "details": [list(item) for item in question.details],
                "preview": tc.preview,
            }
        )
        try:
            return await self._confirmation
        finally:
            self._confirmation = None

    async def _run(self, text: str) -> None:
        try:
            result = await process_input(
                self.context, text, self._render, confirm_tool=self._confirm_tool
            )
            if result.message:
                await self.websocket.send_json(
                    {"type": "notice", "message": result.message}
                )
        except (EmptyInputError, ProviderError) as exc:
            await self.websocket.send_json(
                {"type": "error", "message": error_text(exc)}
            )
        except asyncio.CancelledError:
            await self.websocket.send_json({"type": "notice", "message": "Stopped."})
        await self.websocket.send_json({"type": "done"})


def build_router(context: CommandContext) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return INDEX_PATH.read_text(encoding="utf-8")

    @router.websocket("/ws")
    async def chat(websocket: WebSocket) -> None:
        await websocket.accept()
        turn = WebTurn(context, websocket)
        await websocket.send_json(history_payload(context))
        try:
            while True:
                data = await websocket.receive_json()
                if isinstance(data, dict):
                    await turn.handle(data)
        except WebSocketDisconnect:
            pass
        finally:
            await turn.close()

    return router
