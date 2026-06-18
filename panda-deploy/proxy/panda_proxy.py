"""
PANDA Proxy — Servidor seguro para el Radar de Oportunidades
Seguridad: CORS restringido + token secreto + rate limiting + whitelist de modelos
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import httpx, json, os, time
from collections import defaultdict

app = FastAPI(title="PANDA Proxy", docs_url=None, redoc_url=None)

# ════════════════════════════════════════
# CONFIGURACIÓN DE SEGURIDAD
# ════════════════════════════════════════

# API key de Anthropic (variable de entorno en Render — NUNCA en el código)
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Token secreto: solo las peticiones con este token son aceptadas
PANDA_SECRET = os.environ.get("PANDA_SECRET", "")

# Dominio permitido (tu GitHub Pages)
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://cmbermudezs1-hash.github.io")

# Modelos permitidos (evita que usen modelos caros sin tu permiso)
ALLOWED_MODELS = {
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
}

# Rate limiting: máximo de peticiones por minuto
MAX_REQUESTS_PER_MINUTE = int(os.environ.get("MAX_RPM", "15"))

# ════════════════════════════════════════
# CORS: solo acepta peticiones desde tu dominio
# ════════════════════════════════════════
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, "http://localhost:8000", "http://127.0.0.1:8000", "null"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Panda-Token"],
    max_age=3600,
)

# ════════════════════════════════════════
# RATE LIMITER (en memoria)
# ════════════════════════════════════════
request_log = defaultdict(list)

def check_rate_limit(ip: str) -> bool:
    now = time.time()
    window = [t for t in request_log[ip] if now - t < 60]
    request_log[ip] = window
    if len(window) >= MAX_REQUESTS_PER_MINUTE:
        return False
    request_log[ip].append(now)
    return True

# ════════════════════════════════════════
# HEALTH CHECK
# ════════════════════════════════════════
@app.get("/")
async def health():
    return {"status": "PANDA Proxy activo", "security": "enabled"}

# ════════════════════════════════════════
# PROXY ENDPOINT (streaming)
# ════════════════════════════════════════
@app.post("/v1/messages")
async def proxy(request: Request):
    # 1. Validar token secreto
    token = request.headers.get("X-Panda-Token", "")
    if PANDA_SECRET and token != PANDA_SECRET:
        raise HTTPException(status_code=403, detail="Token inválido. Acceso denegado.")

    # 2. Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiadas peticiones. Espera un minuto.")

    # 3. Validar API key configurada
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key no configurada en el servidor.")

    # 4. Leer y validar el body
    try:
        body = await request.body()
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Body inválido.")

    # 5. Validar modelo
    model = data.get("model", "")
    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Modelo '{model}' no permitido.")

    # 6. Forzar streaming
    data["stream"] = True

    # 7. Limitar max_tokens (evitar abuso)
    if data.get("max_tokens", 0) > 16000:
        data["max_tokens"] = 16000

    # 8. Hacer la llamada al API de Anthropic con streaming
    client = httpx.AsyncClient(timeout=600)
    try:
        req = client.build_request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            content=json.dumps(data).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
            },
        )
        resp = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Error al conectar con Anthropic: {str(e)}")

    async def stream():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=resp.status_code,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
