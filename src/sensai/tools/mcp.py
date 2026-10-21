import asyncio
import itertools
import json
import os
from typing import Any

from .base import SensitiveTool

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "sensai", "version": "0.1.0"}
# One JSON-RPC message is one line; tool results can be big, the default 64 KiB is not.
MAX_LINE_BYTES = 16 * 1024 * 1024


class McpError(Exception):
    """The MCP server failed, timed out, or answered with a protocol error."""


class McpClient:
    """Minimal MCP client over the stdio transport.

    The server is a child process. We write one JSON-RPC 2.0 message per line to its
    stdin and read one per line from its stdout. Only the three calls Sensai needs
    are implemented: the `initialize` handshake, `tools/list` and `tools/call`.
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.timeout = timeout
        self._process: asyncio.subprocess.Process | None = None
        self._ids = itertools.count(1)
        # One request in flight at a time: replies are matched by reading in order.
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Spawn the server and run the handshake. Raises McpError on failure."""
        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                # Server logs go to stderr; unread, a full pipe would block the server.
                stderr=asyncio.subprocess.DEVNULL,
                env={**os.environ, **self.env} if self.env else None,
                limit=MAX_LINE_BYTES,
            )
        except OSError as exc:
            raise McpError(f"cannot start '{self.command}': {exc}") from exc

        try:
            await self._request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
            )
            # Tells the server the handshake is over. A notification has no id and
            # gets no reply.
            await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except McpError:
            await self.close()
            raise

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._request("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise McpError("tools/list returned no tools list")
        # A definition without a string name cannot be called; drop it.
        return [
            tool
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = await self._request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        text = _content_to_text(result.get("content"))
        if result.get("isError"):
            return f"Error: {text or 'the MCP tool failed'}"
        return text

    async def close(self) -> None:
        process, self._process = self._process, None
        if process is None or process.returncode is not None:
            return
        # Closing stdin is the polite stop signal; kill if the server ignores it.
        if process.stdin is not None:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _send(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            raise McpError("MCP server is not running")
        try:
            process.stdin.write(json.dumps(message).encode() + b"\n")
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise McpError("MCP server closed its input") from exc

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            request_id = next(self._ids)
            await self._send(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            try:
                return await asyncio.wait_for(
                    self._read_response(request_id), timeout=self.timeout
                )
            except TimeoutError as exc:
                raise McpError(f"'{method}' timed out after {self.timeout}s") from exc

    async def _read_response(self, request_id: int) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdout is None:
            raise McpError("MCP server is not running")
        while True:
            line = await process.stdout.readline()
            if not line:
                raise McpError("MCP server exited unexpectedly")
            try:
                message = json.loads(line)
            except ValueError:
                continue  # stray non-JSON output on stdout
            # Server notifications and requests carry a "method"; skip them.
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                detail = error.get("message") if isinstance(error, dict) else error
                raise McpError(f"MCP error: {detail}")
            result = message.get("result")
            return result if isinstance(result, dict) else {}


def _content_to_text(content: Any) -> str:
    """Flatten an MCP result's content blocks into text the model can read."""
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        else:
            parts.append(f"[{block.get('type', 'unknown')} content omitted]")
    return "\n".join(parts)


class McpTool(SensitiveTool):
    """One tool of an MCP server, exposed to the engine like any local tool.

    Sensitive by default: the server is third-party code the user did not vet, so
    every call goes through the confirmation prompt.
    """

    def __init__(
        self, client: McpClient, server_name: str, definition: dict[str, Any]
    ) -> None:
        self._client = client
        self._remote_name = str(definition["name"])
        # The prefix keeps two servers from clashing on a common name like "search".
        self.name = f"{server_name}__{self._remote_name}"
        self.description = str(
            definition.get("description") or f"{self._remote_name} (MCP: {server_name})"
        )
        schema = definition.get("inputSchema")
        self.parameters_schema = (
            schema if isinstance(schema, dict) else {"type": "object", "properties": {}}
        )

    async def execute(self, **kwargs: Any) -> str:
        try:
            return await self._client.call_tool(self._remote_name, kwargs)
        except McpError as exc:
            return f"Error: {exc}"
