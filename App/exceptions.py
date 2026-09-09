"""Excepciones de dominio del microservicio de Resumen con IA."""


class ResumenException(Exception):
    """Excepción base para errores de negocio de este servicio."""


class EmptyTextError(ResumenException):
    """El texto a resumir está vacío."""


class LLMError(ResumenException):
    """Error al llamar al proveedor de IA (Gemini)."""


class LLMNotConfiguredError(ResumenException):
    """Falta la API key del proveedor de IA."""
