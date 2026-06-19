"""
FastAPI server que expone el agente de soporte de Steam por HTTP.

Rutas:
  GET  /                       -> sirve webapp/static/index.html
  GET  /api/health             -> healthcheck simple
  POST /api/support            -> ejecuta el caso de soporte y devuelve JSON
  GET  /api/support/stream     -> Server-Sent Events con el progreso del crew

Las llamadas al frontend usan rutas relativas ("/api/..."), por lo que el mismo
HTML funciona en localhost, en una IP publica de EC2 o detras de un dominio,
sin tocar codigo. Nginx (en produccion) sirve los estaticos y hace proxy de
/api/* hacia este proceso uvicorn en el puerto 8000.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import re
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from webapp.security import (
    CREW_TIMEOUT_SECONDS,
    MAX_MESSAGE_LEN,
    RateLimited,
    SecurityRejection,
    client_ip_from_request,
    rate_limiter,
    sanitize_output,
    validate_email,
    validate_message,
    validate_steam_id,
)

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("steam-bot.webapp")

# -------------------------------------------------------------------
# Rutas de estaticos
# -------------------------------------------------------------------
WEBAPP_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEBAPP_DIR / "static"

# -------------------------------------------------------------------
# App
# -------------------------------------------------------------------
app = FastAPI(
    title="Steam Support Bot - Web",
    version="1.0.0",
    description="Interfaz web para el agente autonomo de soporte de Steam.",
)

# CORS abierto solo si esta habilitado por env (util en desarrollo).
# En produccion Nginx sirve todo desde el mismo origen y no hace falta.
if os.getenv("ENABLE_CORS", "0") == "1":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


# -------------------------------------------------------------------
# Middleware: cabeceras de seguridad (defensa en profundidad)
# -------------------------------------------------------------------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # Cabeceras estandar de hardening (OWASP)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    # CSP: solo nuestros propios assets, sin scripts externos
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'",
    )
    return response


# -------------------------------------------------------------------
# Manejo global de excepciones: NUNCA exponer internals
# -------------------------------------------------------------------
@app.exception_handler(SecurityRejection)
async def _security_handler(request: Request, exc: SecurityRejection):
    headers = {}
    if isinstance(exc, RateLimited):
        headers["Retry-After"] = str(exc.retry_after)
    log.warning("security reject [%s] %s -> %s",
                client_ip_from_request(request), exc.status_code, exc.reason)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.user_message},
        headers=headers,
    )


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    # Log completo del lado servidor, mensaje generico al cliente.
    log.exception("error no controlado")
    return JSONResponse(
        status_code=500,
        content={"detail": "Ocurrio un error procesando tu caso. Intentalo de nuevo."},
    )


# -------------------------------------------------------------------
# Modelos
# -------------------------------------------------------------------
class SupportRequest(BaseModel):
    # Limite alineado con la capa de seguridad (Pydantic = primera barrera).
    mensaje: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LEN)
    email: EmailStr
    steam_id: str = Field(default="", max_length=32)


# -------------------------------------------------------------------
# Healthcheck
# -------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "steam-support-bot"}


# -------------------------------------------------------------------
# Endpoint sincrono (sin streaming) - fallback simple
# -------------------------------------------------------------------
@app.post("/api/support")
async def support(req: SupportRequest, request: Request):
    """
    Ejecuta el crew completo y devuelve el resultado final como JSON.
    No emite progreso; usar /api/support/stream para SSE.
    Aplica validacion + rate limit + timeout duro.
    """
    # 1) Seguridad: rate limit + filtros
    ip = client_ip_from_request(request)
    rate_limiter.check(ip)

    mensaje  = validate_message(req.mensaje)
    email    = validate_email(req.email)
    steam_id = validate_steam_id(req.steam_id)

    # 2) Carga perezosa del agente
    try:
        from agent.crew import resolver_caso_soporte
    except Exception:
        log.exception("No se pudo importar el agente")
        raise HTTPException(
            status_code=503,
            detail="El agente no esta disponible en este momento.",
        )

    # 3) Ejecutar con timeout duro (anti DoS interno)
    try:
        resultado = await asyncio.wait_for(
            asyncio.to_thread(resolver_caso_soporte, mensaje, email, steam_id),
            timeout=CREW_TIMEOUT_SECONDS,
        )
        return {"ok": True, "resultado": sanitize_output(str(resultado))}
    except asyncio.TimeoutError:
        log.warning("crew timeout (%ss) ip=%s", CREW_TIMEOUT_SECONDS, ip)
        raise HTTPException(
            status_code=504,
            detail="El procesamiento del caso tardo demasiado. Intentalo de nuevo.",
        )
    except Exception:
        log.exception("error resolviendo caso ip=%s", ip)
        # Mensaje generico, sin detalles internos
        raise HTTPException(
            status_code=500,
            detail="No pudimos procesar tu caso. Intentalo de nuevo.",
        )


# -------------------------------------------------------------------
# Endpoint con SSE (progreso del crew + resultado final)
# -------------------------------------------------------------------
def _sse_event(event: str, data: dict | str) -> str:
    """Formatea un evento SSE."""
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


# -------------------------------------------------------------------
# Humanizador del resultado del crew
# -------------------------------------------------------------------
TICKET_RE = re.compile(r"\bSTM-[A-Z0-9]{4,10}\b")


def _extract_json(text: str) -> Optional[dict]:
    """Intenta extraer el primer objeto JSON dentro de un texto."""
    if not text:
        return None
    s = text.strip()
    # Caso 1: el texto entero es JSON
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except Exception:
            pass
    # Caso 2: JSON embebido en un texto más largo
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def humanize_result(
    raw_result: str,
    email: str,
    task_outputs: list[str],
) -> str:
    """
    Convierte la salida cruda del crew en un mensaje claro y empatico para el
    usuario final. El crew suele terminar devolviendo el JSON del tool de
    envio de correo; aqui lo reescribimos como un mensaje en espanol.

    - Si encontramos un ticket STM-XXXXXX en cualquier output, lo citamos.
    - Si el JSON final indica `status` (sent/simulated/failed), respondemos
      acorde.
    - Si no es JSON, devolvemos el texto original (probablemente ya legible).
    """
    raw = (raw_result or "").strip()
    haystack = "\n".join([*task_outputs, raw])

    # 1) Ticket
    ticket = None
    m = TICKET_RE.search(haystack)
    if m:
        ticket = m.group(0)

    # 2) Status del envio
    parsed = _extract_json(raw)
    status = (parsed or {}).get("status") if isinstance(parsed, dict) else None

    # Si no hay JSON ni status, devolvemos lo crudo (puede ser ya legible)
    if not parsed and not ticket:
        return raw or "Listo. Procese tu caso correctamente."

    parts: list[str] = []

    # Apertura calida
    parts.append("Listo, ya procesé tu caso.")

    if ticket:
        parts.append(f"Quedó registrado con el número de ticket **{ticket}**, así puedes hacerle seguimiento.")

    if status == "sent":
        parts.append(
            f"Acabo de enviarte un correo a **{email}** con los próximos pasos y la información oficial de Steam. "
            "Échale un vistazo (revisa también la carpeta de spam por si acaso)."
        )
    elif status == "simulated":
        parts.append(
            f"Generé un correo de respuesta dirigido a **{email}** con los próximos pasos. "
            "Como el envío real de correos no está configurado en este entorno, lo dejé guardado para revisión interna."
        )
    elif status == "failed":
        parts.append(
            f"Intenté enviarte un correo a **{email}**, pero el envío falló tras varios reintentos. "
            "Voy a escalar tu caso a un agente humano para que te contacte lo antes posible."
        )
    elif parsed:
        # JSON sin status conocido: damos un cierre neutro
        parts.append(
            f"Te enviaré la información de seguimiento al correo **{email}**."
        )

    parts.append("¿Necesitas algo más? Escríbeme aquí mismo y seguimos.")
    return "\n\n".join(parts)


@app.get("/api/support/stream")
async def support_stream(
    request: Request,
    mensaje: str,
    email: str,
    steam_id: str = "",
):
    """
    Server-Sent Events. Eventos emitidos:
      - start        : caso iniciado
      - step         : un paso del agente (pensamiento/uso de tool)
      - task         : una tarea del crew se completo
      - chunk        : fragmento del resultado final (streaming visual)
      - done         : caso terminado, payload con el resultado completo
      - error        : algo fallo

    Aplica seguridad: rate limit + filtros + timeout de 60s.
    """
    # ---------- Seguridad ----------
    # En el endpoint SSE no podemos devolver 400/429 con detalle: el navegador
    # (EventSource) descarta el cuerpo si el status no es 2xx. En su lugar,
    # devolvemos un stream 200 con UN solo evento 'error' que lleva el mensaje.
    ip = client_ip_from_request(request)
    try:
        rate_limiter.check(ip)                 # 429 si excede
        mensaje  = validate_message(mensaje)   # anti prompt injection / off-policy / etc.
        email    = validate_email(email)
        steam_id = validate_steam_id(steam_id)
    except SecurityRejection as exc:
        log.warning("SSE rechazo [%s] %s", ip, exc.reason)
        # Capturamos el mensaje ANTES de definir el generador: Python elimina
        # 'exc' al salir del except y el generador se ejecuta despues (NameError).
        rejection_message = exc.user_message

        async def reject_stream():
            yield _sse_event("error", {"detail": rejection_message})
            yield _sse_event("close", {"ok": False})

        return StreamingResponse(
            reject_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    q: "queue.Queue[tuple[str, object]]" = queue.Queue()
    SENTINEL = ("__done__", None)
    # Salidas de cada tarea para poder humanizar el resultado final
    captured_task_outputs: list[str] = []

    def on_step(step):
        """Callback que CrewAI invoca en cada accion/pensamiento del agente."""
        try:
            text = getattr(step, "text", None) or getattr(step, "log", None) or str(step)
            q.put(("step", {"text": str(text)[:1200]}))
        except Exception:
            pass

    def on_task(task_output):
        """Callback que CrewAI invoca al terminar cada tarea."""
        try:
            raw = getattr(task_output, "raw", None) or str(task_output)
            desc = getattr(task_output, "description", "") or ""
            captured_task_outputs.append(str(raw))
            q.put(("task", {"description": str(desc)[:200], "output": str(raw)[:1200]}))
        except Exception:
            pass

    def run_crew():
        try:
            # Imports perezosos
            from agent.crew import resolver_caso_soporte  # noqa: F401
            from agent.tasks import create_tasks
            from agent.memory import memory_manager
            from crewai import Crew, Process

            q.put(("start", {"mensaje": mensaje, "email": email, "steam_id": steam_id}))

            contexto = (
                f"Mensaje del usuario: {mensaje}\n"
                f"Email: {email}\n"
                f"Steam ID: {steam_id}\n\n"
                f"Contexto adicional desde la memoria:\n{memory_manager.build_context(mensaje)}"
            )

            tasks = create_tasks(contexto)
            analyst = tasks[0].agent
            comms = tasks[2].agent

            # Inyectamos los callbacks sin tocar el codigo del agente
            for a in (analyst, comms):
                try:
                    a.step_callback = on_step
                except Exception:
                    pass
            for t in tasks:
                try:
                    t.callback = on_task
                except Exception:
                    pass

            crew = Crew(
                agents=[analyst, comms],
                tasks=tasks,
                process=Process.sequential,
                verbose=False,
            )
            resultado = crew.kickoff()
            raw_texto = str(resultado)

            # Convertimos el JSON crudo del tool de envio en un mensaje humano
            texto = humanize_result(
                raw_result=raw_texto,
                email=email,
                task_outputs=captured_task_outputs,
            )
            # Sanitizamos cualquier secreto que se haya colado por error
            texto = sanitize_output(texto)

            # Emitimos el resultado final en chunks para dar sensacion de streaming
            CHUNK = 60
            for i in range(0, len(texto), CHUNK):
                q.put(("chunk", {"text": texto[i : i + CHUNK]}))

            q.put(("done", {"resultado": texto}))
        except Exception as e:
            log.exception("Fallo en SSE")
            q.put(("error", {"detail": str(e)}))
        finally:
            q.put(SENTINEL)

    async def event_generator():
        loop = asyncio.get_running_loop()
        t = threading.Thread(target=run_crew, daemon=True)
        t.start()
        deadline = time.monotonic() + CREW_TIMEOUT_SECONDS
        timed_out = False
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    item = await asyncio.wait_for(
                        loop.run_in_executor(None, q.get),
                        timeout=remaining,
                    )
                except asyncio.TimeoutError:
                    timed_out = True
                    break
                if item == SENTINEL:
                    break
                event, payload = item
                yield _sse_event(event, payload)
        finally:
            if timed_out:
                log.warning("SSE timeout (%ss) ip=%s", CREW_TIMEOUT_SECONDS, ip)
                yield _sse_event(
                    "error",
                    {"detail": f"El procesamiento tardo mas de {CREW_TIMEOUT_SECONDS}s. Reformula tu mensaje y vuelve a intentarlo."},
                )
            # cierre limpio
            yield _sse_event("close", {"ok": True})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # importante para Nginx: NO bufferear SSE
            "Connection": "keep-alive",
        },
    )


# -------------------------------------------------------------------
# Estaticos: se montan AL FINAL para no pisar /api/*
# -------------------------------------------------------------------
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    async def index_missing():
        return {
            "ok": False,
            "detail": f"No se encontro {STATIC_DIR}. Genera el frontend antes de servir.",
        }
