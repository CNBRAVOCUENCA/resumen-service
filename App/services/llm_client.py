"""Cliente para el proveedor de IA (Gemini) vía su API REST.

Se define una interfaz mínima (`LLMClient`) para poder inyectar una
implementación falsa en los tests, sin llamar a la API real ni gastar
cuota. `GeminiClient` es la implementación concreta que habla con la API
de Google Generative Language.

Incluye REINTENTOS automáticos: si Google responde 503 ("modelo saturado")
o 429 ("demasiadas peticiones"), que son errores temporales, se reintenta
con una espera creciente antes de rendirse. Así los picos de demanda
transitorios se resuelven solos, sin que el usuario tenga que reintentar.
"""

import asyncio
from typing import Protocol

import httpx

from App.exceptions import LLMError, LLMNotConfiguredError

# Códigos HTTP que valen la pena reintentar (errores temporales del proveedor)
_CODIGOS_TEMPORALES = {429, 500, 503}


class LLMClient(Protocol):
    """Interfaz mínima que debe cumplir cualquier cliente de IA."""

    async def generate(self, prompt: str) -> str:
        ...


class GeminiClient:
    """Implementación real que llama a la API REST de Gemini, con reintentos."""

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        max_reintentos: int = 3,
        espera_base_seg: float = 2.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_reintentos = max_reintentos
        self.espera_base_seg = espera_base_seg

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMNotConfiguredError("Falta GEMINI_API_KEY para llamar al proveedor de IA")

        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        params = {"key": self.api_key}

        ultimo_error = ""
        # Se intenta hasta max_reintentos+1 veces (el primer intento + los reintentos)
        for intento in range(self.max_reintentos + 1):
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http_client:
                try:
                    response = await http_client.post(url, json=payload, params=params)
                except httpx.HTTPError as exc:
                    ultimo_error = f"No se pudo contactar al proveedor de IA: {exc}"
                    await self._esperar(intento)
                    continue

            if response.status_code < 400:
                # Éxito: parsear y devolver el texto
                try:
                    data = response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except (KeyError, IndexError, ValueError) as exc:
                    raise LLMError(f"Respuesta inesperada del proveedor de IA: {exc}") from exc

            # Error: si es temporal (503/429/500) y quedan reintentos, esperar y volver a intentar
            ultimo_error = f"El proveedor de IA respondió {response.status_code}: {response.text[:200]}"
            if response.status_code in _CODIGOS_TEMPORALES and intento < self.max_reintentos:
                await self._esperar(intento)
                continue
            # Error no temporal (ej. 404 modelo inexistente) o se agotaron los reintentos
            raise LLMError(ultimo_error)

        raise LLMError(f"Se agotaron los reintentos. Último error: {ultimo_error}")

    async def _esperar(self, intento: int) -> None:
        """Espera creciente entre reintentos (backoff): 2s, 4s, 6s..."""
        await asyncio.sleep(self.espera_base_seg * (intento + 1))
