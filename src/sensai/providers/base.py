import httpx


class BaseHTTPProvider:
    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )

    async def _check_response_status(self, response: httpx.Response) -> None:
        if response.is_error:
            await response.aread()
            raise RuntimeError(
                f"HTTP Provider Error [{response.status_code}]: {response.text}"
            )
