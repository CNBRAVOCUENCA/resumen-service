"""Tests de los reintentos automáticos del cliente de IA."""

import httpx
import pytest
import respx
from App.exceptions import LLMError
from App.services.llm_client import GeminiClient

BASE = "https://fake-gemini.test"


@respx.mock
async def test_reintenta_ante_503_y_luego_tiene_exito():
    """Si Google da 503 (saturado) y después responde bien, el cliente
    reintenta solo y devuelve el resultado — sin que falle."""
    ruta = respx.post(url__regex=rf"{BASE}/v1beta/models/.*:generateContent")
    # Primera llamada: 503. Segunda: éxito.
    ruta.side_effect = [
        httpx.Response(503, text="high demand"),
        httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "resumen ok"}]}}]}),
    ]
    # espera_base muy chica para que el test sea rápido
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0.01)
    resultado = await client.generate("hola")
    assert resultado == "resumen ok"


@respx.mock
async def test_se_rinde_tras_agotar_reintentos():
    """Si Google da 503 siempre, tras agotar los reintentos lanza LLMError."""
    respx.post(url__regex=rf"{BASE}/v1beta/models/.*:generateContent").mock(
        return_value=httpx.Response(503, text="high demand")
    )
    client = GeminiClient(api_key="k", model="m", base_url=BASE, max_reintentos=2, espera_base_seg=0.01)
    with pytest.raises(LLMError):
        await client.generate("hola")


@respx.mock
async def test_no_reintenta_ante_404():
    """Un 404 (modelo inexistente) NO es temporal: falla de una, sin reintentar."""
    ruta = respx.post(url__regex=rf"{BASE}/v1beta/models/.*:generateContent").mock(
        return_value=httpx.Response(404, text="model not found")
    )
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0.01)
    with pytest.raises(LLMError):
        await client.generate("hola")
    # Se llamó una sola vez (no reintentó)
    assert ruta.call_count == 1


# --- Prompt 12: política de Retry sin duplicar operaciones facturables ---

URL = rf"{BASE}/v1beta/models/.*:generateContent"
OK = {"candidates": [{"content": {"parts": [{"text": "resumen ok"}]}}]}


@respx.mock
async def test_reintenta_ante_429_respetando_retry_after():
    ruta = respx.post(url__regex=URL)
    ruta.side_effect = [httpx.Response(429, headers={"retry-after": "0"}), httpx.Response(200, json=OK)]
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=5)
    assert await client.generate("hola") == "resumen ok"
    assert ruta.call_count == 2


@respx.mock
async def test_no_reintenta_ante_500_para_no_duplicar_la_generacion():
    ruta = respx.post(url__regex=URL).mock(return_value=httpx.Response(500, text="internal"))
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0.01)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_reintenta_si_no_se_pudo_conectar():
    ruta = respx.post(url__regex=URL)
    ruta.side_effect = [httpx.ConnectError("sin red"), httpx.Response(200, json=OK)]
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0.01)
    assert await client.generate("hola") == "resumen ok"
    assert ruta.call_count == 2


@respx.mock
async def test_no_reintenta_timeout_de_lectura():
    ruta = respx.post(url__regex=URL).mock(side_effect=httpx.ReadTimeout("lento"))
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0.01)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_maximo_cuatro_intentos():
    ruta = respx.post(url__regex=URL).mock(return_value=httpx.Response(503, text="saturado"))
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=0.01)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 4


@respx.mock
async def test_respeta_el_presupuesto_total():
    ruta = respx.post(url__regex=URL).mock(return_value=httpx.Response(503, text="saturado"))
    client = GeminiClient(api_key="k", model="m", base_url=BASE, espera_base_seg=5, presupuesto_total_seg=1)
    with pytest.raises(LLMError):
        await client.generate("hola")
    assert ruta.call_count == 1


@respx.mock
async def test_une_todas_las_partes_de_la_respuesta():
    respx.post(url__regex=URL).mock(
        return_value=httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "Primera parte, "}, {"text": "segunda."}]}}]}
        )
    )
    client = GeminiClient(api_key="k", model="m", base_url=BASE)
    assert await client.generate("hola") == "Primera parte, segunda."
