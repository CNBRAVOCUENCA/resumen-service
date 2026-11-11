"""Entrypoint del microservicio de Resumen con IA."""

from fastapi import FastAPI

from App.api import summary_router
from App.api.exception_handlers import register_exception_handlers
from App.config.settings import settings
from App.logging_config import configurar_logging
from App.services.consul import consul_lifespan
from App.telemetry import install_telemetry
from App.tracing import configurar_trazas

# Disable API documentation in production (when debug=False)
docs_url = "/docs" if settings.debug else None
redoc_url = "/redoc" if settings.debug else None
openapi_url = "/openapi.json" if settings.debug else None

configurar_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    lifespan=consul_lifespan(settings),
)

install_telemetry(app, settings.app_name)
# Después de install_telemetry: el middleware de OpenTelemetry queda por fuera y el
# span ya está activo cuando se calculan las métricas y el x-trace-id.
configurar_trazas(app, settings.app_name)
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
