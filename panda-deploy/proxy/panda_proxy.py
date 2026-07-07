"""
PANDA Proxy — Servidor seguro para el Radar de Oportunidades
Soporta: Claude + Gemini + Google Sheets + Firecrawl
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import httpx, json, os, time
from collections import defaultdict

app = FastAPI(title="PANDA Proxy", docs_url=None, redoc_url=None)

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
PANDA_SECRET = os.environ.get("PANDA_SECRET", "")
SHEETS_URL = os.environ.get("SHEETS_URL", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://cmbermudezs1-hash.github.io")

ALLOWED_MODELS = {
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
}

MAX_REQUESTS_PER_MINUTE = int(os.environ.get("MAX_RPM", "15"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, "http://localhost:8000", "http://127.0.0.1:8000", "null"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "X-Panda-Token"],
    max_age=3600,
)

request_log = defaultdict(list)

def check_rate_limit(ip):
    now = time.time()
    window = [t for t in request_log[ip] if now - t < 60]
    request_log[ip] = window
    if len(window) >= MAX_REQUESTS_PER_MINUTE:
        return False
    request_log[ip].append(now)
    return True

def validate_token(request):
    token = request.headers.get("X-Panda-Token", "")
    if PANDA_SECRET and token != PANDA_SECRET:
        raise HTTPException(status_code=403, detail="Token invalido.")

@app.get("/")
async def health():
    return {"status": "PANDA Proxy activo", "firecrawl": bool(FIRECRAWL_API_KEY), "models": list(ALLOWED_MODELS)}

# ════════════════════════════════════════
# FIRECRAWL — Extraer contenido de URLs
# ════════════════════════════════════════
@app.post("/extract")
async def extract_urls(request: Request):
    validate_token(request)
    if not FIRECRAWL_API_KEY:
        return JSONResponse({"results": [], "error": "FIRECRAWL_API_KEY no configurada."})
    try:
        body = await request.body()
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Body invalido.")
    urls = data.get("urls", [])
    if not urls:
        return JSONResponse({"results": []})
    results = []
    async with httpx.AsyncClient(timeout=30) as client:
        for url in urls[:20]:
            try:
                r = await client.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    json={"url": url, "formats": ["markdown"]},
                    headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}
                )
                rd = r.json()
                md = rd.get("data", {}).get("markdown", "")
                title = rd.get("data", {}).get("metadata", {}).get("title", "")
                results.append({"url": url, "title": title, "content": md[:6000], "success": True})
            except Exception as e:
                results.append({"url": url, "title": "", "content": "", "success": False, "error": str(e)})
    return JSONResponse({"results": results})

# ════════════════════════════════════════
# GOOGLE SHEETS
# ════════════════════════════════════════
@app.get("/sheets/load")
async def sheets_load(request: Request):
    validate_token(request)
    if not SHEETS_URL:
        return JSONResponse({"rows": [], "error": "SHEETS_URL no configurada"})
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(SHEETS_URL)
            return JSONResponse(r.json())
    except Exception as e:
        return JSONResponse({"rows": [], "error": str(e)})

@app.post("/sheets/save")
async def sheets_save(request: Request):
    validate_token(request)
    if not SHEETS_URL:
        return JSONResponse({"ok": False, "error": "SHEETS_URL no configurada"})
    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.post(SHEETS_URL, content=body, headers={"Content-Type": "application/json"})
            return JSONResponse(r.json())
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

# ════════════════════════════════════════
# ANTHROPIC (Claude) — streaming
# ════════════════════════════════════════
async def handle_anthropic(data):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada.")
    data["stream"] = True
    client = httpx.AsyncClient(timeout=600)
    try:
        req = client.build_request(
            "POST", "https://api.anthropic.com/v1/messages",
            content=json.dumps(data).encode(),
            headers={"Content-Type": "application/json", "x-api-key": API_KEY, "anthropic-version": "2023-06-01"},
        )
        resp = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Error Anthropic: {str(e)}")
    async def stream():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()
    return StreamingResponse(stream(), status_code=resp.status_code, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ════════════════════════════════════════
# GOOGLE GEMINI
# ════════════════════════════════════════
async def handle_gemini(data, model):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY no configurada.")
    system_text = data.get("system", "")
    messages = data.get("messages", [])
    user_msg = ""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_msg += content + "\n"
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        user_msg += part.get("text", "") + "\n"
                    elif isinstance(part, str):
                        user_msg += part + "\n"
    gemini_body = {
        "contents": [{"role": "user", "parts": [{"text": user_msg.strip()}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"maxOutputTokens": min(data.get("max_tokens", 8000), 65536), "temperature": 0.7},
    }
    if system_text:
        gemini_body["system_instruction"] = {"parts": [{"text": system_text}]}
    async with httpx.AsyncClient(timeout=300) as client:
        try:
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GOOGLE_API_KEY}",
                json=gemini_body, headers={"Content-Type": "application/json"},
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Error Google: {str(e)}")
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=f"Google API: {r.text[:300]}")
        result = r.json()
    full_text = ""
    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            full_text += part.get("text", "")
    if not full_text:
        full_text = "No se encontraron resultados."
    async def fake_stream():
        events = [
            f'event: message_start\ndata: {{"type":"message_start","message":{{"id":"msg_gemini","type":"message","role":"assistant","content":[],"model":"{model}","stop_reason":null}}}}\n\n',
            f'event: content_block_start\ndata: {{"type":"content_block_start","index":0,"content_block":{{"type":"text","text":""}}}}\n\n',
        ]
        chunk_size = 200
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i:i + chunk_size]
            escaped = json.dumps(chunk)
            events.append(f'event: content_block_delta\ndata: {{"type":"content_block_delta","index":0,"delta":{{"type":"text_delta","text":{escaped}}}}}\n\n')
        events.extend([
            f'event: content_block_stop\ndata: {{"type":"content_block_stop","index":0}}\n\n',
            f'event: message_delta\ndata: {{"type":"message_delta","delta":{{"stop_reason":"end_turn"}}}}\n\n',
            f'event: message_stop\ndata: {{"type":"message_stop"}}\n\n',
        ])
        for event in events:
            yield event.encode()
    return StreamingResponse(fake_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ════════════════════════════════════════
# ENDPOINT PRINCIPAL
# ════════════════════════════════════════
@app.post("/v1/messages")
async def proxy(request: Request):
    validate_token(request)
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiadas peticiones.")
    try:
        body = await request.body()
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Body invalido.")
    model = data.get("model", "")
    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Modelo '{model}' no permitido.")
    if data.get("max_tokens", 0) > 16000:
        data["max_tokens"] = 16000
    if model.startswith("gemini"):
        return await handle_gemini(data, model)
    else:
        return await handle_anthropic(data)
