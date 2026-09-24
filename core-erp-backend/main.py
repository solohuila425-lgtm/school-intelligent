import time
import os
import json

import redis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api import agents, auth, classrooms, grades, students, billing, privacy, academic_memory
from api.auth import try_decode_token
from observability.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    rate_limit_exceeded_total,
    metrics_response,
)
from observability.logging_config import log_event
from observability.rate_limiter import RateLimiter
from observability.tracing import setup_tracing, current_trace_id
from database.connection import engine as _db_engine

app = FastAPI(
    title="ERP Educativo Multimedia — Core Backend",
    description="ERP tradicional: usuarios, aulas, sesiones en vivo y notas.",
    version="0.1.0",
)

# Tracing distribuido (nuevo): instrumenta FastAPI (span por request) y
# SQLAlchemy (span por query) automáticamente. Se llama ANTES de agregar
# los middlewares de abajo para que el span raíz de FastAPIInstrumentor
# envuelva también al rate limiter y al middleware de métricas.
setup_tracing(app=app, engine=_db_engine)

# CORS: sin esto, el frontend (localhost:5173 en dev) no puede llamar a
# este API (localhost:8200) — el navegador bloquea la petición antes de
# que llegue aquí. CORS_ALLOWED_ORIGINS es una lista separada por comas;
# en producción debe ser el dominio real del frontend, NUNCA "*" cuando
# se usan credenciales/tokens de autenticación.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
allowed_origins = [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", _default_origins).split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate limiting (nuevo) --------------------------------------------------
# Mismo Redis que ya usa auth.py para revocación de tokens. Un solo
# cliente para todo el proceso (igual patrón que _redis_client en
# api/auth.py), reutilizado en cada request vía el middleware de abajo.
_rate_limit_redis = redis.from_url(os.getenv("ERP_REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
_rate_limiter = RateLimiter(_rate_limit_redis)

# Rutas exentas: /metrics lo consulta Prometheus con alta frecuencia por
# diseño, y / es solo un health-check trivial — limitarlas no protege
# nada y sí puede romper el scraping de métricas bajo carga.
_RATE_LIMIT_EXEMPT_PATHS = {"/metrics", "/"}
# Endpoints SIN token (aún no hay organización que identificar): se
# limitan por IP con un umbral mucho más estricto que el tráfico
# autenticado normal, específicamente para frenar fuerza bruta de
# contraseñas contra /auth/login.
_UNAUTHENTICATED_STRICT_PATHS = {"/auth/login", "/auth/register"}


def _rate_limit_config() -> dict:
    """Se lee del entorno en CADA request (no una vez al importar el
    módulo) a propósito: así los tests pueden ajustar límites y ventanas
    con `monkeypatch.setenv(...)` sin tener que forzar una recarga del
    módulo `main` — y en producción, un operador puede cambiar el límite
    y reiniciar el proceso sin tocar código."""
    return {
        "org_per_min": int(os.getenv("ERP_RATE_LIMIT_PER_ORG_PER_MIN", "300")),
        "ip_per_min": int(os.getenv("ERP_RATE_LIMIT_PER_IP_PER_MIN", "60")),
        "auth_ip_per_min": int(os.getenv("ERP_RATE_LIMIT_AUTH_PER_IP_PER_MIN", "10")),
        "window_seconds": int(os.getenv("ERP_RATE_LIMIT_WINDOW_SECONDS", "60")),
    }


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # NOTA: a diferencia de metrics_middleware (que lee request.scope["route"]
    # DESPUÉS de await call_next, cuando el router ya resolvió la ruta), este
    # middleware decide ANTES de despachar la petición — en ese punto la
    # ruta con plantilla ("/classrooms/{id}/start") todavía no existe en el
    # scope, así que se usa la ruta cruda. Es exactamente lo que se
    # necesita aquí: los paths que importan para exención y para el límite
    # estricto de auth (/metrics, /, /auth/login, /auth/register) no tienen
    # segmentos dinámicos, así que la ruta cruda y la con plantilla coinciden.
    path = request.url.path
    if path in _RATE_LIMIT_EXEMPT_PATHS:
        return await call_next(request)

    config = _rate_limit_config()

    # Si trae un token VÁLIDO, se limita por organización (tenant) — así
    # un colegio con tráfico anómalo no consume el presupuesto de los
    # demás, ni al revés un colegio pequeño se ve limitado por el tráfico
    # de uno grande.
    org_id = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        payload = try_decode_token(auth_header.removeprefix("Bearer "))
        if payload:
            org_id = payload.get("org")

    client_ip = request.client.host if request.client else "unknown"

    if org_id:
        scope, bucket_key, limit = "org", org_id, config["org_per_min"]
    elif path in _UNAUTHENTICATED_STRICT_PATHS:
        scope, bucket_key, limit = "auth_ip", client_ip, config["auth_ip_per_min"]
    else:
        scope, bucket_key, limit = "ip", client_ip, config["ip_per_min"]

    result = _rate_limiter.check(f"{scope}:{bucket_key}", limit, config["window_seconds"])

    if result.fail_open:
        log_event("rate_limit_fail_open", scope=scope, path=path,
                   detail="Redis no disponible, se dejó pasar la petición")

    if not result.allowed:
        rate_limit_exceeded_total.labels(scope).inc()
        log_event("rate_limit_exceeded", scope=scope, bucket_key=bucket_key, path=path)
        return Response(
            content=json.dumps({"detail": "Demasiadas solicitudes. Intenta de nuevo en unos segundos."}),
            status_code=429,
            media_type="application/json",
            headers={
                "Retry-After": str(result.reset_seconds),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    return response


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    # Se usa route.path (ej. "/classrooms/{classroom_id}/start") en vez de
    # request.url.path para no generar una serie de métricas distinta por
    # cada UUID de aula — si no, Prometheus explota en cardinalidad.
    route = request.scope.get("route")
    path_label = route.path if route else request.url.path

    http_requests_total.labels(request.method, path_label, response.status_code).inc()
    http_request_duration_seconds.labels(request.method, path_label).observe(duration)

    # X-Trace-Id (nuevo): expone el trace_id del span activo en la
    # respuesta. Un profesor que reporta "esta petición falló" puede
    # copiar este ID y buscarlo en logs/tracing sin tener que dar
    # timestamp aproximado ni adivinar qué request fue.
    trace_id = current_trace_id()
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return response


@app.get("/metrics", tags=["Status"], summary="Métricas Prometheus")
def metrics():
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)


app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(classrooms.router)
app.include_router(grades.router)
app.include_router(students.router)
app.include_router(billing.router)
app.include_router(privacy.router)
app.include_router(academic_memory.router)

# Compatibilidad con el portal ERP desplegado en Vercel, que consume
# /api/v1/*, conservando las rutas sin prefijo usadas por immersive-frontend.
for router in (
    auth.router,
    agents.router,
    classrooms.router,
    grades.router,
    students.router,
    billing.router,
    privacy.router,
    academic_memory.router,
):
    app.include_router(router, prefix="/api/v1", include_in_schema=False)


@app.get("/", tags=["Status"])
def root():
    return {"service": "core-erp-backend", "status": "ok"}
