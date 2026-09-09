"""Traduce excepciones de dominio a respuestas HTTP, en un solo lugar (DRY)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from App.exceptions import EmptyTextError, LLMError, LLMNotConfiguredError

_STATUS_MAP = {
    EmptyTextError: 400,
    LLMNotConfiguredError: 503,
    LLMError: 502,
}


def register_exception_handlers(app: FastAPI) -> None:
    for exc_class, status_code in _STATUS_MAP.items():
        app.add_exception_handler(exc_class, _make_handler(status_code))


def _make_handler(status_code: int):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})
    return handler
