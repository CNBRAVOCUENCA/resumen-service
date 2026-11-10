"""Tests de la política de una sola llamada del cliente de IA."""

import httpx
import pytest
import respx
from App.exceptions import LLMError
from App.services.llm_client import GeminiClient

BASE = "https://fake-gemini.test"


@respx.mock
async def test_no_reintenta_ante_respuesta_temporal_503():
    """Un 503 falla sin repetir el POST de generación."""
    ruta = respx.post(url__regex=rf"{BASE}/v1beta/models/.*:generateContent").mock(
        return_value=httpx.Response(503, text="high demand")
    )
    client = GeminiClient(api_key="k", model="m", base_url=BASE)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_no_reintenta_ante_429_ni_404():
    """Los errores HTTP fallan con un solo POST, incluso si parecen temporales."""
    ruta = respx.post(url__regex=rf"{BASE}/v1beta/models/.*:generateContent").mock(
        return_value=httpx.Response(429, text="rate limited")
    )
    client = GeminiClient(api_key="k", model="m", base_url=BASE)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_no_reintenta_ante_error_de_transporte():
    ruta = respx.post(url__regex=rf"{BASE}/v1beta/models/.*:generateContent").mock(
        side_effect=httpx.ConnectError("connection lost")
    )
    client = GeminiClient(api_key="k", model="m", base_url=BASE)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1
