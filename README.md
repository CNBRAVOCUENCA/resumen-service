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

### Validación de la entrada

- `text`: obligatorio; si está vacío o tiene solo espacios responde **400** y no se llama a Gemini.
- `max_words`: entero entre **10 y 500**, por defecto **150**. Fuera de rango (0, negativos, 501 o más), `null` o no numérico responde **422** y no se llama a Gemini. El límite es orientativo: se le pide al modelo "un máximo de N palabras".

### Reintentos hacia Gemini (patrón Retry)

Solo se reintenta cuando Gemini no procesó el pedido, para no duplicar generaciones facturables:

| Situación | ¿Reintenta? |
|---|---|
| 429 o 503 | Sí, hasta 3 reintentos (4 intentos), espera 2 s, 4 s y 6 s o el `Retry-After` (tope 10 s) |
| No se pudo conectar (`ConnectError`/`ConnectTimeout`) | Sí, misma política |
| 500, timeout de lectura u otros errores | No: el pedido pudo haberse procesado |
| 4xx distintos de 429 | No |

Presupuesto total: si la próxima espera supera los 80 s desde el primer intento, no se reintenta más. Cada intento tiene timeout de 30 s, así el peor caso (≈110 s) queda dentro de los 120 s que espera el Orquestador. Si Gemini parte la respuesta en varias partes, se unen todas.

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

### Usuario de ejecución en Docker

La imagen ejecuta Uvicorn con UID:GID `10001:10001`, ambos sin privilegios. El
servicio no necesita escribir en el sistema de archivos local; los logs se
envían a stdout.

### Consul y Traefik

El registro en Consul es opcional: configura `CONSUL_HTTP_ADDR` con la dirección
HTTP del agente (por ejemplo, `http://consul:8500`). Si está vacío, el registro
queda desactivado, lo que permite ejecutar el servicio de forma independiente.
`CONSUL_HTTP_TOKEN` es opcional y se envía en el encabezado `X-Consul-Token`;
nunca se incluye en los logs.

Al iniciar, la aplicación registra el servicio mediante la API del agente. El
nombre predeterminado es `APP_NAME`, el puerto predeterminado es `8000`, y
`CONSUL_SERVICE_TAGS` acepta tags separados por comas para la configuración de
Traefik. Si no se configura `CONSUL_SERVICE_ADDRESS`, se anuncia la IP local
seleccionada para llegar al agente de Consul; no se usa el nombre DNS replicado
ni un `container_name` fijo. Se puede fijar la dirección explícitamente cuando
la topología de red lo requiera.

Consul consulta `http://<dirección>:<puerto>/health` cada 10 segundos, con un
timeout de 2 segundos, y elimina la instancia si permanece crítica durante un
minuto. La aplicación intenta desregistrarla al cerrarse. Si `CONSUL_HTTP_ADDR`
está configurado y falla el registro, el inicio falla para evitar ejecutar una
instancia que no se pueda descubrir.

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

## Escaneo de seguridad

El workflow `Security scan` audita las dependencias de runtime fijadas en
`uv.lock` y construye/escanea la imagen Docker con Trivy. Se ejecuta en cada PR,
push a `main`/`master`, semanalmente (lunes 06:00 UTC) y manualmente desde
GitHub Actions. La política es: **falla el job cualquier hallazgo HIGH o CRITICAL que tenga
parche disponible** (`ignore-unfixed: true`). Los HIGH/CRITICAL sin parche de la
imagen base (paquetes de Debian en estado *affected*, sin versión corregida)
**se siguen mostrando** en la tabla del log, pero no bloquean: no hay acción
posible desde este repo hasta que Debian publique el arreglo, y en ese momento el
escaneo semanal empieza a fallar y obliga a reconstruir la imagen. No se usan
`.trivyignore` ni otros filtros. Los detalles quedan visibles en el log del workflow. También verifica que la imagen se ejecute como
un usuario distinto de root.

## Stack

Python 3.12+ · FastAPI · httpx · pytest + respx · API de Google Gemini
