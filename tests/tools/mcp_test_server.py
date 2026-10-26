"""Self-built MCP server used by the tests: speaks JSON-RPC over stdin/stdout.

Tools: `add` (sums two numbers), `boom` (reports a tool error), `image` (returns a
non-text block). Run with `python mcp_test_server.py`; `--crash-on-call` makes it exit
in the middle of a tools/call, `--hang-on-call` makes it never answer one, `--noisy-call`
prints a non-JSON line before answering one.
"""

import json
import sys
import time

TOOLS = [
    {
        "name": "add",
        "description": "Add two numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
    {"name": "boom", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "image", "inputSchema": {"type": "object", "properties": {}}},
]


def reply(request_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    print(json.dumps(message), flush=True)


def call(name, arguments):
    if name == "add":
        return {
            "content": [{"type": "text", "text": str(arguments["a"] + arguments["b"])}]
        }
    if name == "boom":
        return {"content": [{"type": "text", "text": "it broke"}], "isError": True}
    if name == "image":
        return {"content": [{"type": "image", "data": "AAAA", "mimeType": "image/png"}]}
    return None


for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        # A log notification first: the client must skip it, not mistake it for the reply.
        print(json.dumps({"jsonrpc": "2.0", "method": "notifications/message"}))
        reply(
            request_id,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test", "version": "0"},
            },
        )
    elif method == "tools/list":
        reply(request_id, {"tools": TOOLS})
    elif method == "tools/call":
        if "--crash-on-call" in sys.argv:
            sys.exit(1)
        if "--hang-on-call" in sys.argv:
            time.sleep(60)
        if "--noisy-call" in sys.argv:
            print("server log: not JSON", flush=True)
        params = request["params"]
        result = call(params["name"], params["arguments"])
        if result is None:
            reply(request_id, error={"code": -32602, "message": "unknown tool"})
        else:
            reply(request_id, result)
