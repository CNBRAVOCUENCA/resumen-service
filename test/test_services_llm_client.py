"""Pruebas unitarias para GeminiClient (llamada HTTP a la API de Gemini)."""

import httpx
import pytest
import respx

from App.exceptions import LLMError, LLMNotConfiguredError
from App.services.llm_client import GeminiClient

BASE = "https://fake-gemini.test"


async def test_generate_raises_if_no_api_key():
    client = GeminiClient(api_key=None, model="gemini-1.5-flash", base_url=BASE)
    with pytest.raises(LLMNotConfiguredError):
        await client.generate("hola")


@respx.mock
async def test_generate_returns_text_on_success():
    respx.post(url__regex=rf"{BASE}/v1beta/models/.*:generateContent").mock(
        return_value=httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "resumen ok"}]}}]
        })
    )
    client = GeminiClient(api_key="fake-key", model="gemini-1.5-flash", base_url=BASE)
    result = await client.generate("resumime esto")
    assert result == "resumen ok"


@respx.mock
async def test_generate_raises_llm_error_on_http_error():
    respx.post(url__regex=rf"{BASE}/v1beta/models/.*:generateContent").mock(
        return_value=httpx.Response(429, text="rate limited")
    )
    client = GeminiClient(api_key="fake-key", model="gemini-1.5-flash", base_url=BASE)
    with pytest.raises(LLMError):
        await client.generate("hola")
