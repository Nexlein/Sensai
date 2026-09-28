import httpx
import pytest

from sensai.providers.base import BaseHTTPProvider


def test_init_strips_trailing_slash():
    provider = BaseHTTPProvider(base_url="http://localhost:11434/", timeout=5.0)
    assert provider.base_url == "http://localhost:11434"
    assert provider.timeout == 5.0


def test_get_client_uses_base_url_and_timeout():
    provider = BaseHTTPProvider(base_url="http://localhost:11434", timeout=5.0)
    client = provider._get_client()
    assert str(client.base_url) == "http://localhost:11434"
    assert client.timeout.connect == 5.0


async def test_check_response_status_ok_does_not_raise():
    provider = BaseHTTPProvider(base_url="http://localhost:11434")
    request = httpx.Request("GET", "http://localhost:11434/api/chat")
    response = httpx.Response(200, request=request)
    await provider._check_response_status(response)


async def test_check_response_status_error_raises_with_body():
    provider = BaseHTTPProvider(base_url="http://localhost:11434")
    request = httpx.Request("GET", "http://localhost:11434/api/chat")
    response = httpx.Response(500, request=request, text="boom")
    with pytest.raises(RuntimeError, match="500.*boom"):
        await provider._check_response_status(response)
