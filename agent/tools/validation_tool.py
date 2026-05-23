"""
Tool de validación de usuario.

Valida los datos que manda el usuario (correo, Steam ID, tipo de problema) y
genera un ticket con prioridad. La lógica funciona 100% offline (no llama a
ninguna API), así que se puede probar sin credenciales.

Reglas de prioridad (basadas en la base de conocimiento):
    - ALTA:  seguridad / robo de cuenta / acceso comprometido.
    - MEDIA: facturación, reembolsos, problemas de compra, instalación.
    - BAJA:  consultas generales, preguntas sobre Steam Guard, etc.

Escalamiento manual obligatorio:
    - Chargebacks / disputas de cargo.
    - Identidad no verificable.
    - Posible violación de ToS (baneo VAC, etc.).
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Optional, Type

from pydantic import BaseModel, Field

try:
    from crewai.tools import BaseTool
except ImportError:
    # Fallback para poder probar la tool sin tener CrewAI instalado.
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]


# ──────────────────────────────────────────────────────────────────────
#  Schema de argumentos (lo que el LLM ve para saber qué parámetros pide)
# ──────────────────────────────────────────────────────────────────────
class _ValidateUserSchema(BaseModel):
    """Parámetros que recibe la tool de validación."""

    email: str = Field(..., description="Correo electrónico del usuario.")
    steam_id_or_username: Optional[str] = Field(
        None, description="Steam ID o nombre de usuario (opcional)."
    )
    issue_type: Optional[str] = Field(
        None,
        description=(
            "Tipo de problema: 'seguridad', 'facturacion', 'reembolso', "
            "'instalacion', 'general', u otro texto libre."
        ),
    )
    issue_description: str = Field(
        "", description="Descripción del problema del usuario."
    )


# ──────────────────────────────────────────────────────────────────────
#  Constantes internas
# ──────────────────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Palabras clave para detectar el tipo de problema si no se indica.
_SECURITY_KEYWORDS = [
    "hackea", "robar", "robaron", "comprometida", "comprometido",
    "sesión desde otro", "acceso no autorizado", "otro país",
    "no reconozco", "steam guard", "phishing", "suplantación",
]
_BILLING_KEYWORDS = [
    "chargeback", "cargo duplicado", "disputa", "reembolso",
    "factur", "cobro", "pago rechazado",
]
_ESCALATION_KEYWORDS = [
    "chargeback", "disputa de cargo", "baneo vac", "ban vac",
    "violación de los términos", "tos violation",
]


# ──────────────────────────────────────────────────────────────────────
#  La tool propiamente dicha
# ──────────────────────────────────────────────────────────────────────
class ValidateUserTool(BaseTool):
    """
    Valida los datos del usuario y genera un ticket de soporte con prioridad.

    Devuelve un JSON con: valid, ticket_id, priority, missing_fields,
    requires_manual_escalation, escalation_reason y message.
    """

    name: str = "validar_usuario"
    description: str = (
        "Valida los datos del usuario (correo, Steam ID, tipo de problema), "
        "genera un número de ticket (STM-XXXXXX) y asigna una prioridad "
        "(ALTA / MEDIA / BAJA). Devuelve un JSON."
    )
    args_schema: Type[BaseModel] = _ValidateUserSchema

    # ---- helpers ----
    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        """True si el texto contiene alguna de las palabras clave (case-insensitive)."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    @staticmethod
    def _generate_ticket_id() -> str:
        """Genera un ID de ticket con formato STM-XXXXXX."""
        return f"STM-{uuid.uuid4().hex[:6].upper()}"

    # ---- clasificación ----
    def _classify(self, issue_type: str | None, description: str) -> str:
        """Devuelve un tipo normalizado: 'seguridad', 'facturacion' o 'general'."""
        if issue_type:
            it = issue_type.strip().lower()
            if it in ("seguridad", "security"):
                return "seguridad"
            if it in ("facturacion", "facturación", "billing", "reembolso", "refund"):
                return "facturacion"
            if it in ("instalacion", "instalación", "installation"):
                return "instalacion"
        # Fallback: inferir del texto de la descripción.
        if self._contains_any(description, _SECURITY_KEYWORDS):
            return "seguridad"
        if self._contains_any(description, _BILLING_KEYWORDS):
            return "facturacion"
        return "general"

    def _assign_priority(self, category: str) -> str:
        """Asigna prioridad según la categoría (alineado con la KB § 3)."""
        if category == "seguridad":
            return "ALTA"
        if category in ("facturacion", "instalacion"):
            return "MEDIA"
        return "BAJA"

    def _needs_escalation(self, description: str) -> tuple[bool, str | None]:
        """Determina si el caso requiere escalamiento manual obligatorio."""
        if self._contains_any(description, _ESCALATION_KEYWORDS):
            return True, (
                "El caso contiene indicadores de disputa de cargo, fraude o "
                "posible violación de ToS; requiere revisión de un humano."
            )
        return False, None

    # ---- ejecución ----
    def _run(
        self,
        email: str = "",
        steam_id_or_username: str | None = None,
        issue_type: str | None = None,
        issue_description: str = "",
    ) -> str:
        """Ejecuta la validación y devuelve un JSON."""
        missing: list[str] = []

        # 1. Validar email.
        if not email or not _EMAIL_RE.match(email):
            missing.append("email (inválido o faltante)")

        # 2. Validar descripción.
        if not issue_description or len(issue_description.strip()) < 5:
            missing.append("issue_description (la descripción del problema es obligatoria)")

        # Si falta algo, devolvemos un resultado parcial pidiéndole al agente
        # que solicite la info faltante.
        if missing:
            return json.dumps(
                {
                    "valid": False,
                    "ticket_id": None,
                    "priority": None,
                    "missing_fields": missing,
                    "requires_manual_escalation": False,
                    "escalation_reason": None,
                    "message": (
                        "Faltan datos para abrir el ticket. Por favor solicita "
                        f"al usuario: {', '.join(missing)}."
                    ),
                },
                ensure_ascii=False,
            )

        # 3. Clasificar y asignar prioridad.
        category = self._classify(issue_type, issue_description)
        priority = self._assign_priority(category)
        ticket_id = self._generate_ticket_id()

        # 4. ¿Necesita escalamiento manual?
        escalate, reason = self._needs_escalation(issue_description)

        return json.dumps(
            {
                "valid": True,
                "ticket_id": ticket_id,
                "priority": priority,
                "category": category,
                "missing_fields": [],
                "requires_manual_escalation": escalate,
                "escalation_reason": reason,
                "user_data": {
                    "email": email,
                    "steam_id_or_username": steam_id_or_username,
                },
                "message": (
                    f"Ticket {ticket_id} abierto con prioridad {priority} "
                    f"(categoría: {category})."
                ),
            },
            ensure_ascii=False,
        )
