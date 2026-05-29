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
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

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
# Modelos
# -------------------------------------------------------------------
class SupportRequest(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=4000)
    email: EmailStr
    steam_id: str = Field(default="", max_length=120)


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
async def support(req: SupportRequest):
    """
    Ejecuta el crew completo y devuelve el resultado final como JSON.
    No emite progreso; usar /api/support/stream para SSE.
    """
    try:
        # Import perezoso para que el servidor levante incluso sin el .env listo
        from agent.crew import resolver_caso_soporte
    except Exception as e:
        log.exception("No se pudo importar el agente")
        raise HTTPException(status_code=500, detail=f"Agente no disponible: {e}")

    try:
        # resolver_caso_soporte es bloqueante -> lo corremos en threadpool
        resultado = await asyncio.to_thread(
            resolver_caso_soporte,
            req.mensaje,
            req.email,
            req.steam_id,
        )
        return {"ok": True, "resultado": resultado}
    except Exception as e:
        log.exception("Error resolviendo caso")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
# Endpoint con SSE (progreso del crew + resultado final)
# -------------------------------------------------------------------
def _sse_event(event: str, data: dict | str) -> str:
    """Formatea un evento SSE."""
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@app.get("/api/support/stream")
async def support_stream(
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
    """
    if not mensaje.strip():
        raise HTTPException(status_code=400, detail="mensaje vacio")

    q: "queue.Queue[tuple[str, object]]" = queue.Queue()
    SENTINEL = ("__done__", None)

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
            texto = str(resultado)

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
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item == SENTINEL:
                break
            event, payload = item
            yield _sse_event(event, payload)
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
