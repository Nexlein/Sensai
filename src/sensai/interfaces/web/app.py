"""Web frontend for a shared Sensai session."""

import uvicorn
from fastapi import FastAPI

from sensai.core.commands import CommandContext
from sensai.interfaces.web.routes import build_router

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def build_app(context: CommandContext) -> FastAPI:
    app = FastAPI(title="Sensai", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(build_router(context))
    return app


async def run_web(
    context: CommandContext, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> None:
    config = uvicorn.Config(
        build_app(context), host=host, port=port, log_level="warning"
    )
    print(f"Sensai web UI: http://{host}:{port}")
    await uvicorn.Server(config).serve()
