"""Tests de la política acotada de reintentos del cliente de IA."""

import asyncio

import httpx
import pytest
import respx
from App.exceptions import LLMError
from App.services.llm_client import GeminiClient

BASE = "https://fake-gemini.test"
URL = rf"{BASE}/v1beta/models/.*:generateContent"
OK = {"candidates": [{"content": {"parts": [{"text": "resumen ok"}]}}]}


@respx.mock
async def test_reintenta_ante_503_y_luego_tiene_exito():
    ruta = respx.post(url__regex=URL)
    ruta.side_effect = [httpx.Response(503, text="high demand"), httpx.Response(200, json=OK)]
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0)
    assert await client.generate("hola") == "resumen ok"
    assert ruta.call_count == 2


@respx.mock
async def test_reintenta_ante_429_respetando_retry_after():
    ruta = respx.post(url__regex=URL)
    ruta.side_effect = [
        httpx.Response(429, headers={"retry-after": "0"}),
        httpx.Response(200, json=OK),
    ]
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=5)
    assert await client.generate("hola") == "resumen ok"
    assert ruta.call_count == 2


@respx.mock
async def test_no_reintenta_ante_404():
    ruta = respx.post(url__regex=URL).mock(return_value=httpx.Response(404, text="model not found"))
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_reintenta_si_no_se_pudo_establecer_conexion():
    ruta = respx.post(url__regex=URL)
    ruta.side_effect = [httpx.ConnectError("connection lost"), httpx.Response(200, json=OK)]
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0)
    assert await client.generate("hola") == "resumen ok"
    assert ruta.call_count == 2


@respx.mock
async def test_no_reintenta_ante_500():
    ruta = respx.post(url__regex=URL).mock(return_value=httpx.Response(500, text="internal"))
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_no_reintenta_timeout_de_lectura():
    ruta = respx.post(url__regex=URL).mock(side_effect=httpx.ReadTimeout("lento"))
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_no_supera_el_presupuesto_total_de_la_solicitud():
    async def respuesta_lenta(request):
        await asyncio.sleep(1)
        return httpx.Response(503, text="high demand")

    ruta = respx.post(url__regex=URL).mock(side_effect=respuesta_lenta)
    client = GeminiClient(
        api_key="k",
        model="m",
        base_url=BASE,
        timeout_seconds=1,
        presupuesto_total_seg=0.1,
    )
    inicio = asyncio.get_running_loop().time()
    with pytest.raises(LLMError, match="presupuesto"):
        await client.generate("hola")
    assert asyncio.get_running_loop().time() - inicio < 0.5
    assert ruta.call_count <= 1


@respx.mock
async def test_no_reintenta_si_el_presupuesto_no_cubre_la_espera():
    ruta = respx.post(url__regex=URL).mock(return_value=httpx.Response(503, text="high demand"))
    client = GeminiClient(
        api_key="k",
        model="m",
        base_url=BASE,
        espera_base_seg=5,
        presupuesto_total_seg=1,
    )
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_maximo_cuatro_intentos():
    ruta = respx.post(url__regex=URL).mock(return_value=httpx.Response(503, text="saturado"))
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 4


@respx.mock
async def test_une_todas_las_partes_de_la_respuesta():
    respx.post(url__regex=URL).mock(
        return_value=httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "Primera parte, "}, {"text": "segunda."}]}}]}
        )
    )
    client = GeminiClient(api_key="k", model="m", base_url=BASE)
    assert await client.generate("hola") == "Primera parte, segunda."
