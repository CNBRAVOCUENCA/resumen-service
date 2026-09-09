"""Pruebas de integración de la API de Resumen, mockeando la API de Gemini."""

import importlib

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

GEMINI_BASE = "https://fake-gemini.test"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_BASE_URL", GEMINI_BASE)
    # Recargar settings y los módulos que lo capturan, para que tomen las env vars del test
    import App.config.settings as settings_module
    importlib.reload(settings_module)
    import App.api.Routes.summary as summary_module
    importlib.reload(summary_module)
    import App.main as main_module
    importlib.reload(main_module)
    return TestClient(main_module.app)


@respx.mock
def test_summarize_success(client):
    respx.post(url__regex=rf"{GEMINI_BASE}/v1beta/models/.*:generateContent").mock(
        return_value=httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "resumen de prueba"}]}}]
        })
    )
    response = client.post("/api/v1/summarize", json={"text": "un texto para resumir", "max_words": 50})
    assert response.status_code == 200, response.text
    assert response.json()["summary"] == "resumen de prueba"


def test_summarize_empty_text_returns_400(client):
    response = client.post("/api/v1/summarize", json={"text": "   "})
    assert response.status_code == 400


def test_health_check(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["llm_configured"] is True
