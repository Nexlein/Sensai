"""Web frontend for a shared Sensai session."""

import contextlib
import socket
import sys
from collections.abc import Iterator

import uvicorn
from fastapi import FastAPI

from sensai.core.commands import CommandContext
from sensai.interfaces.web.routes import build_router

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class QuietServer(uvicorn.Server):
    """uvicorn server that does not re-raise the Ctrl+C it shut down on.

    uvicorn replays SIGINT once it has stopped; asyncio's handler then cancels the
    whole app mid-cleanup and the user gets a traceback. Stopping the server is
    enough: the dispatcher closes the session and returns normally.
    """

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        with super().capture_signals():
            try:
                yield
            finally:
                self._captured_signals.clear()


def build_app(context: CommandContext) -> FastAPI:
    app = FastAPI(title="Sensai", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(build_router(context))
    return app


def _port_in_use(host: str, port: int) -> bool:
    """True when something already listens there (same socket options as uvicorn)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return True
    return False


async def run_web(
    context: CommandContext, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> None:
    if _port_in_use(host, port):
        # uvicorn would log its own error and still let us print the address.
        print(
            f"✗ Port {port} is already in use: another Sensai is probably still "
            "running. Stop it (Ctrl+C in its terminal), then start again.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    config = uvicorn.Config(
        build_app(context), host=host, port=port, log_level="warning"
    )
    print(f"Sensai web UI: http://{host}:{port}")
    await QuietServer(config).serve()
