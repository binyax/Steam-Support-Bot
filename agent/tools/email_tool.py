"""
Tool de envío de correo de soporte.

Puede funcionar en dos modos:

1. **Modo SMTP (real)**: si las variables SMTP_USER y SMTP_PASSWORD están
   configuradas en el .env, envía el correo de verdad con STARTTLS y reintentos.
2. **Modo simulado**: si no hay credenciales SMTP (o si el envío real falla),
   guarda el correo como archivo ``.eml`` en ``agent/data/email_outbox/``.

Devuelve un JSON con ``status`` = ``sent`` | ``simulated`` | ``failed`` que el
agente usa para decidir si cierra el caso o lo escala a un humano.
"""

from __future__ import annotations

import json
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, Type

from pydantic import BaseModel, Field

from agent import config

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]


# ──────────────────────────────────────────────────────────────────────
#  Schema de argumentos
# ──────────────────────────────────────────────────────────────────────
class _EmailSchema(BaseModel):
    """Parámetros para enviar un correo de soporte."""

    to_email: str = Field(..., description="Correo del destinatario.")
    subject: str = Field(..., description="Asunto del correo.")
    body: str = Field(..., description="Cuerpo del correo (texto plano).")
    category: str = Field(
        "ticket",
        description=(
            "Categoría del correo: 'ticket' (confirmación), 'alerta_seguridad', "
            "'recuperacion', u otro texto libre."
        ),
    )


# ──────────────────────────────────────────────────────────────────────
#  La tool
# ──────────────────────────────────────────────────────────────────────
class SendSupportEmailTool(BaseTool):
    """
    Envía un correo de soporte de Steam al usuario.

    Devuelve un JSON con ``status`` (``sent`` / ``simulated`` / ``failed``),
    ``backup`` (si aplica) y ``detail``.
    """

    name: str = "enviar_correo_soporte"
    description: str = (
        "Envía un correo de soporte al usuario por SMTP (si hay credenciales) "
        "o lo guarda como .eml en modo simulado. Devuelve el status del envío."
    )
    args_schema: Type[BaseModel] = _EmailSchema

    # Configurable para tests (se puede bajar a 1 para no esperar).
    max_retries: int = 2
    retry_delay: float = 1.0

    # ---- helpers ----
    def _build_message(self, to: str, subject: str, body: str) -> MIMEMultipart:
        """Arma el objeto MIMEMultipart listo para enviar."""
        msg = MIMEMultipart("alternative")
        msg["From"] = config.settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg["X-Steam-Bot"] = "automated-support"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        return msg

    def _save_eml(self, msg: MIMEMultipart, category: str) -> Path:
        """Guarda el correo como .eml en el outbox simulado."""
        config.ensure_dirs()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{ts}_{category}.eml"
        path = config.EMAIL_OUTBOX_DIR / filename
        path.write_text(msg.as_string(), encoding="utf-8")
        return path

    def _send_smtp(self, msg: MIMEMultipart) -> None:
        """Envía el correo por SMTP con STARTTLS."""
        with smtplib.SMTP(config.settings.smtp_host, config.settings.smtp_port, timeout=15) as srv:
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            srv.login(config.settings.smtp_user, config.settings.smtp_password)
            srv.send_message(msg)

    # ---- ejecución ----
    def _run(
        self,
        to_email: str = "",
        subject: str = "",
        body: str = "",
        category: str = "ticket",
    ) -> str:
        """Ejecuta el envío (o simulación) y devuelve un JSON."""
        msg = self._build_message(to_email, subject, body)

        # --- Modo simulado (sin credenciales) ---
        if not config.settings.smtp_configured:
            eml_path = self._save_eml(msg, category)
            return json.dumps(
                {
                    "status": "simulated",
                    "detail": (
                        "No hay credenciales SMTP configuradas. "
                        f"Correo guardado en {eml_path.name}"
                    ),
                    "eml_file": str(eml_path),
                    "backup": {"status": "simulated"},
                },
                ensure_ascii=False,
            )

        # --- Modo real (con reintentos) ---
        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._send_smtp(msg)
                return json.dumps(
                    {
                        "status": "sent",
                        "detail": f"Correo enviado a {to_email} en el intento {attempt}.",
                        "backup": {"status": "not_needed"},
                    },
                    ensure_ascii=False,
                )
            except Exception as exc:
                last_error = f"Intento {attempt}/{self.max_retries}: {exc}"
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

        # Si falló tras todos los reintentos, hacemos backup simulado.
        eml_path = self._save_eml(msg, category)
        return json.dumps(
            {
                "status": "failed",
                "detail": f"Fallo de envío SMTP: {last_error}",
                "backup": {
                    "status": "simulated",
                    "eml_file": str(eml_path),
                },
            },
            ensure_ascii=False,
        )
