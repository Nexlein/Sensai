import httpx


class BaseHTTPProvider:
    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
        wait_forever: bool = False,
    ) -> None:
        """`timeout` bounds connecting and sending; with `wait_forever` the wait for
        the answer itself is unbounded (a slow local model is not a failure)."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.wait_forever = wait_forever

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout, read=None)
            if self.wait_forever
            else self.timeout,
        )

    async def _check_response_status(self, response: httpx.Response) -> None:
        if response.is_error:
            await response.aread()
            raise RuntimeError(
                f"HTTP Provider Error [{response.status_code}]: {response.text}"
            )
