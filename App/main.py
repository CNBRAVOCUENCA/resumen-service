"""Entrypoint del microservicio de Resumen con IA."""

from fastapi import FastAPI

from App.api import summary_router
from App.api.exception_handlers import register_exception_handlers
from App.config.settings import settings

app = FastAPI(title=settings.app_name, version=settings.app_version, debug=settings.debug)

register_exception_handlers(app)
app.include_router(summary_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health() -> dict:
    """Health check. Reporta si el proveedor de IA está configurado."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "llm_configured": settings.gemini_api_key is not None,
    }
