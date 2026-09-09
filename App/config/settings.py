"""Configuración del microservicio, vía variables de entorno."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "resumen-service"
    app_version: str = "0.1.0"
    debug: bool = False

    # Configuración del proveedor de IA (Gemini)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"

    # Límites del resumen
    max_input_chars: int = 30000
    api_v1_prefix: str = "/api/v1"


settings = Settings()
