"""Cliente para el proveedor de IA (Gemini) vía su API REST."""

import asyncio
import time
from math import isfinite
from typing import Protocol

import httpx

from App.exceptions import LLMError, LLMNotConfiguredError

_CODIGOS_REINTENTABLES = {429, 503}
_RETRY_AFTER_MAX_SEG = 10.0


class LLMClient(Protocol):
    """Interfaz mínima que debe cumplir cualquier cliente de IA."""

    async def generate(self, prompt: str) -> str:
        ...


class GeminiClient:
    """Implementación real que realiza llamadas HTTP con reintentos acotados."""

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_reintentos: int = 3,
        espera_base_seg: float = 2.0,
        presupuesto_total_seg: float = 80.0,
    ):
        if timeout_seconds <= 0 or max_reintentos < 0 or espera_base_seg < 0 or presupuesto_total_seg <= 0:
            raise ValueError("La configuración de timeout, reintentos y presupuesto no es válida")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_reintentos = max_reintentos
        self.espera_base_seg = espera_base_seg
        self.presupuesto_total_seg = presupuesto_total_seg

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMNotConfiguredError("Falta GEMINI_API_KEY para llamar al proveedor de IA")

        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        # La clave va en un header y no en la URL: las URLs quedan registradas en
        # los logs (httpx, proxies), y así la clave nunca aparece en ellos.
        headers = {"x-goog-api-key": self.api_key}

        inicio = time.monotonic()
        ultimo_error = "Se agotó el presupuesto total antes de completar la solicitud"
        for intento in range(self.max_reintentos + 1):
            restante = self.presupuesto_total_seg - (time.monotonic() - inicio)
            if restante <= 0:
                break

            espera: float | None = None
            try:
                async with httpx.AsyncClient(timeout=min(self.timeout_seconds, restante)) as http_client:
                    async with asyncio.timeout(restante):
                        response = await http_client.post(url, json=payload, headers=headers)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                ultimo_error = f"No se pudo establecer conexión con el proveedor de IA: {exc}"
                espera = self._espera(intento, None)
            except TimeoutError as exc:
                mensaje = "Se agotó el presupuesto durante la solicitud; no se repetirá un resultado ambiguo"
                raise LLMError(mensaje) from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"Error al contactar al proveedor de IA: {exc}") from exc

            if espera is None:
                if response.status_code < 400:
                    return self._extraer_texto(response)
                ultimo_error = f"El proveedor de IA respondió {response.status_code}: {response.text[:200]}"
                if response.status_code not in _CODIGOS_REINTENTABLES:
                    raise LLMError(ultimo_error)
                espera = self._espera(intento, response.headers.get("retry-after"))

            restante = self.presupuesto_total_seg - (time.monotonic() - inicio)
            if intento >= self.max_reintentos or espera >= restante:
                break
            await asyncio.sleep(espera)

        raise LLMError(f"Se agotaron los reintentos o el presupuesto total. Último error: {ultimo_error}")

    @staticmethod
    def _extraer_texto(response: httpx.Response) -> str:
        """Une todas las partes de texto del primer candidato."""
        try:
            partes = response.json()["candidates"][0]["content"]["parts"]
            texto = "".join(parte.get("text", "") for parte in partes).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"Respuesta inesperada del proveedor de IA: {exc}") from exc
        if not texto:
            raise LLMError("El proveedor de IA devolvió una respuesta sin texto")
        return texto

    def _espera(self, intento: int, retry_after: str | None) -> float:
        """Usa Retry-After numérico o backoff creciente, con un tope de 10 s."""
        if retry_after:
            try:
                segundos = float(retry_after)
                if isfinite(segundos):
                    return min(max(segundos, 0.0), _RETRY_AFTER_MAX_SEG)
            except ValueError:
                pass
        return min(self.espera_base_seg * (intento + 1), _RETRY_AFTER_MAX_SEG)

    @staticmethod
    def _extraer_texto(response: httpx.Response) -> str:
        """Une todas las partes de texto del primer candidato."""
        try:
            partes = response.json()["candidates"][0]["content"]["parts"]
            texto = "".join(parte.get("text", "") for parte in partes).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"Respuesta inesperada del proveedor de IA: {exc}") from exc
        if not texto:
            raise LLMError("El proveedor de IA devolvió una respuesta sin texto")
        return texto
