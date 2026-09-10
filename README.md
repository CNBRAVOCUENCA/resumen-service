# resumen-service

Microservicio de **resumen de texto con IA (Gemini)**, tercero de la migración del
monolito `El-Destripador-de-PDFs` hacia microservicios.

Recibe un texto (normalmente el que produjo `extraccion-service`), arma un prompt y
llama a la API de Google Gemini para generar un resumen. Devuelve el resumen y
algunas métricas.

## Arquitectura (capas)

```
App/
├── api/Routes/summary.py         # POST /summarize
├── api/exception_handlers.py     # excepciones de dominio -> HTTP
├── services/llm_client.py        # cliente de Gemini (interfaz + impl. real)
├── services/resumen_service.py   # arma prompt, valida, delega en el cliente
├── models/ · schemas/            # dominio y DTOs
└── config/settings.py            # incluye GEMINI_API_KEY, modelo, etc.
test/                              # 9 tests (unitarios + integración, sin llamar a Gemini real)
```

El cliente de IA se define como una interfaz (`LLMClient`) e implementación concreta
(`GeminiClient`), lo que permite inyectar un cliente falso en los tests y no gastar
cuota real de la API.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/summarize` | Recibe `{"text": "...", "max_words": 150}`, devuelve `{summary, input_char_count, summary_char_count}` |
| GET | `/health` | Health check (indica si la API key está configurada) |

## Errores

| Situación | HTTP |
|---|---|
| Texto vacío | 400 |
| Falta la API key de Gemini | 503 |
| Error al llamar a Gemini (rate limit, red, etc.) | 502 |

## Configuración

Copiar `.env.example` a `.env` y completar `GEMINI_API_KEY` con una clave real de
[Google AI Studio](https://aistudio.google.com/app/apikey). Sin la key, el servicio
arranca pero `/summarize` devuelve 503.

## Correr los tests

Con **uv** (recomendado, más rápido y con `uv.lock` para versiones reproducibles):

```bash
uv sync --extra dev
uv run --extra dev pytest test/ -v
```

O con pip tradicional:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest test/ -v
```

Los tests **no** llaman a la API real de Gemini: usan un cliente falso / respuestas
mockeadas con `respx`.

## Stack

Python 3.12+ · FastAPI · httpx · pytest + respx · API de Google Gemini
