import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sensai.domain.models import now_utc

DEFAULT_LOG_PATH = Path("logs/turns.jsonl")


class TurnLogger:
    def __init__(
        self, path: str | Path = DEFAULT_LOG_PATH, enabled: bool = False
    ) -> None:
        self.path = Path(path)
        self.enabled = enabled

    def log(
        self,
        model: str,
        latency_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        if not self.enabled:
            return

        entry: dict[str, object] = {
            "timestamp": now_utc().isoformat(),
            "model": model,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        if error is not None:
            entry["error"] = error

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    @contextmanager
    def track(self, model: str) -> Iterator[dict[str, int]]:
        usage: dict[str, int] = {}
        start = time.monotonic()
        try:
            yield usage
        except Exception as exc:
            self.log(model, (time.monotonic() - start) * 1000, error=str(exc))
            raise
        else:
            self.log(
                model,
                (time.monotonic() - start) * 1000,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
