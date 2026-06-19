"""
Capa de seguridad para la web del Steam-Support-Bot.

Implementa las mitigaciones recomendadas por la OWASP Top 10 for LLM Applications
y el material 3.3.1 (Protocolos de Seguridad y Consideraciones Eticas):

- Validacion y sanitizacion de entradas (anti prompt injection / token-drain).
- Filtro de coherencia (anti basura/profanidad sin intencion de soporte).
- Rate limiting en memoria (sliding window por IP + cooldown).
- Sanitizacion de salidas (anti leak de secretos).
- Mensajes de error genericos al cliente.

Las listas de palabras (profanidad, stop words, contexto de soporte) viven en
security_wordlists.py para mantener este archivo legible.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from webapp.security_wordlists import (
    PROFANITY_WORDS,
    STOP_WORDS,
    SUPPORT_CONTEXT_WORDS,
)

log = logging.getLogger("steam-bot.security")

# ===================================================================
# CONFIGURACION (modo "estricto")
# ===================================================================

MAX_MESSAGE_LEN = 1500

RPM_LIMIT = 5            # peticiones / minuto / IP
RPD_LIMIT = 30           # peticiones / dia / IP
COOLDOWN_SECONDS = 8     # cooldown entre peticiones del mismo IP

CREW_TIMEOUT_SECONDS = 60

# Coherencia
COHERENCE_MIN_LEN_NO_CONTEXT = 15
COHERENCE_MIN_SIGNIFICANT = 3
COHERENCE_VULGAR_RATIO = 0.40


# ===================================================================
# EXCEPCIONES
# ===================================================================

class SecurityRejection(Exception):
    """Entrada rechazada por la capa de seguridad."""

    def __init__(self, reason: str, user_message: Optional[str] = None, status_code: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.user_message = user_message or "No puedo procesar tu mensaje."
        self.status_code = status_code


class RateLimited(SecurityRejection):
    """Excedio rate limit. Lleva Retry-After."""

    def __init__(self, retry_after: int, scope: str):
        super().__init__(
            reason=f"rate limit excedido ({scope})",
            user_message=f"Demasiadas solicitudes. Vuelve a intentar en {retry_after} segundos.",
            status_code=429,
        )
        self.retry_after = retry_after


# ===================================================================
# PATRONES DE ATAQUE
# ===================================================================

PROMPT_INJECTION_PATTERNS = [
    r"ignor[ae]\s+(las\s+)?(instrucciones|reglas|todo|lo\s+anterior)",
    r"olvida\s+(tus|las|todo|todas)\s+\w*\s*(instrucciones|reglas|prompts?|mensajes?)",
    r"forget\s+(your|all|previous|the)\s+\w*\s*(instructions|rules|prompts?|messages?)",
    r"ignore\s+(all\s+)?(previous|prior|above|the)\s+\w*\s*(instructions|prompts?|rules|messages?)",
    r"disregard\s+(all\s+)?(previous|prior|the)\s+\w*\s*(instructions|prompts?|rules)",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(an?\s+)?(unrestricted|jailbroken|developer)",
    r"developer\s+mode",
    r"dan\s+mode",
    r"jailbreak",
    r"system\s+prompt",
    r"reveal\s+(your|the)\s+(system|initial|original)\s+(prompt|instructions)",
    r"muestra(me)?\s+(tu|el)\s+(prompt|system|sistema|configuraci)",
    r"dime\s+(tu|el)\s+(prompt|system|sistema|api\s*key|token)",
    r"print\s+(the\s+)?(system|developer|initial)\s+prompt",
    r"\.env\b",
    r"github_token",
    r"smtp_password",
    r"langsmith_api_key",
    r"api[_\s-]?key",
    r"\{\{\s*[a-z_]+\s*\}\}",
    r"</?(system|assistant|user)\s*>",
]
_INJECTION_RE = re.compile("|".join(PROMPT_INJECTION_PATTERNS), re.IGNORECASE)

# ---- Off-policy: pirateria, robo de cuentas, fraude, evasion de DRM ----
# Filosofia: bloqueamos cuando el USUARIO pide hacer/aprender algo ilegal,
# pero permitimos que reporte que ES VICTIMA ("me hackearon", "robaron mi cuenta").
OFF_POLICY_PATTERNS = [
    # Pirateria de juegos
    r"\bpirat(a|ar|ear|earlo|eo|eria|eados?|eadas?)\b",
    r"\bcracke(o|ar|arlo|ado|ada|aron)\b",
    r"\bcracks?\b",
    r"\bwarez\b",
    r"\bkey[\s-]?gen(erator)?\b",
    r"\bactivador(es)?\b",
    r"\bbypass\s+(drm|denuvo|steam\s*guard|2fa|mfa)\b",
    r"\bsaltar(me)?\s+(drm|denuvo|steam\s*guard|2fa|mfa|la\s+verificacion)\b",
    r"(descargar|baja(r|telo|tela)|conseguir|obtener)\s+(\w+\s+){0,4}(gratis|sin\s+pagar|crackead|pirat)",
    r"juegos?\s+(\w+\s+){0,3}(gratis|sin\s+pagar)\s+(\w+\s+){0,3}(crack|pirat|torrent|warez|hack)",
    r"\btorrent(s|es)?\b.{0,40}\b(juego|game|steam|key|clave|codigo)\b",
    r"\b(juego|game|key|clave|codigo)\b.{0,40}\btorrent(s|es)?\b",
    r"sitios?\s+(web\s+)?(para\s+)?(piratear|descargar\s+(juegos?\s+)?gratis|crack)",
    # Robo / abuso de cuentas (intento del usuario, no reporte de victima)
    r"\bcomo\s+(hackear|robar|sacar|crackear|hijack)\s+(una\s+|la\s+|tu\s+|mi\s+)?cuenta",
    r"\bsteam\s*stealer\b",
    r"\baccount\s+stealer\b",
    r"cuentas?\s+(robadas?|hackeadas?)\s+(gratis|baratas?|en\s+venta|para\s+vender|venta|comprar)",
    r"comprar\s+cuentas?\s+(robadas?|hackeadas?|premium|con\s+juegos)",
    r"vender\s+cuentas?\s+(robadas?|hackeadas?)",
    r"como\s+(entrar|acceder|meterme|ingresar)\s+a\s+(la\s+|una\s+)?cuenta\s+de\s+(otro|alguien|otra\s+persona|mi\s+amigo|mi\s+ex)",
    # Fraude / chargeback abuse
    r"como\s+(estafar|enganar|engañar|timar)",
    r"chargeback\s+(abuse|fraud|trick)",
    # Generacion / robo de claves
    r"keys?\s+(gratis|robadas?|hackeadas?)\s+de\s+steam",
    r"generar\s+keys?\s+de\s+steam",
]
_OFF_POLICY_RE = re.compile("|".join(OFF_POLICY_PATTERNS), re.IGNORECASE)

# ---- Amenazas / abuso al bot/sistema ----
THREAT_PATTERNS = [
    r"(te\s+|os\s+)?voy\s+a\s+(hackear|tumbar|atacar|joder|romper|tirar|destruir|reventar|colapsar|sobrecargar)",
    r"(quiero|vamos\s+a|voy\s+a)\s+(ddos|ataque|atacarte|tumbarte|tirarte|romperte|destrozarte)",
    r"\bddos\b",
    r"sobrecargar(te|lo|los)?\s+(el\s+|tu\s+|este\s+)?(bot|servidor|sistema|servicio|api)",
    r"voy\s+a\s+gastar(te)?\s+(todos\s+)?(los\s+)?tokens?",
    r"vaciarte\s+(los\s+|el\s+)?tokens?",
    r"voy\s+a\s+(romper|hackear|tumbar|atacar)\s+(el\s+|tu\s+|este\s+)?(bot|servidor|sistema|servicio)",
    r"soy\s+(el\s+)?profe.{0,30}(tumbar|hackear|atacar|romper|joder|reventar)",
    r"profesor.{0,30}(tumbar|hackear|atacar|romper|joder|reventar)",
]
_THREAT_RE = re.compile("|".join(THREAT_PATTERNS), re.IGNORECASE)

_REPEAT_RE = re.compile(r"(repite|repeat|imprime|print)\s+(\d{2,})\s+veces", re.IGNORECASE)
_LONG_RUN_RE = re.compile(r"(.)\1{120,}")

_STEAM_ID_RE = re.compile(r"^[A-Za-z0-9_\-\.]{2,32}$")

SECRET_PATTERNS = [
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"gho_[A-Za-z0-9]{20,}",
    r"lsv2_[A-Za-z0-9_]{20,}",
    r"sk-[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"Bearer\s+[A-Za-z0-9_\-\.]{20,}",
]
_SECRET_RE = re.compile("|".join(SECRET_PATTERNS), re.IGNORECASE)

_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ſ]+")


# ===================================================================
# COHERENCIA / PROFANIDAD
# ===================================================================

def _normalize(s: str) -> str:
    """Quita acentos para hacer comparaciones robustas."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower()


def _tokenize(s: str) -> list[str]:
    return _TOKEN_RE.findall(_normalize(s))


def validate_coherence(mensaje: str) -> None:
    """
    Rechaza mensajes que sean basura/profanidad sin intencion de soporte.
    """
    s = mensaje.strip()
    tokens = _tokenize(s)
    significant = [t for t in tokens if t not in STOP_WORDS]
    has_context = any(t in SUPPORT_CONTEXT_WORDS for t in significant)

    if len(s) < COHERENCE_MIN_LEN_NO_CONTEXT and not has_context:
        log.warning("coherencia: muy corto sin contexto -> %r", s[:50])
        raise SecurityRejection(
            "mensaje muy corto sin contexto",
            "Tu mensaje es muy corto. Cuentame con detalle que problema tienes con tu cuenta, compra o juego de Steam.",
        )

    # Si hay contexto de soporte: 2 palabras significativas bastan (ej. "cuenta hackeada").
    # Si NO hay contexto: exigimos minimo 5 palabras significativas para evitar
    # ruido tipo "cualquier cosa al azar" que pasaria todos los demas filtros.
    min_significant = 2 if has_context else 5
    if len(significant) < min_significant:
        log.warning(
            "coherencia: pocas palabras (%d/%d) ctx=%s -> %r",
            len(significant), min_significant, has_context, s[:50],
        )
        raise SecurityRejection(
            "insuficientes palabras significativas",
            "Necesito mas informacion para ayudarte. Describe que ocurre con tu cuenta, compra o juego de Steam.",
        )

    unique = set(significant)
    if len(unique) <= 2 and len(significant) >= 4:
        log.warning("coherencia: spam repetido -> %r", s[:80])
        raise SecurityRejection(
            "spam de palabras repetidas",
            "Tu mensaje parece repetir las mismas palabras. Describe tu problema con Steam en una frase clara.",
        )

    vulgar_count = sum(1 for t in significant if t in PROFANITY_WORDS)
    vulgar_ratio = vulgar_count / max(1, len(significant))
    if vulgar_ratio > COHERENCE_VULGAR_RATIO and not has_context:
        log.warning("coherencia: profanidad %.0f%% sin contexto -> %r",
                    vulgar_ratio * 100, s[:80])
        raise SecurityRejection(
            f"profanidad sin contexto ({vulgar_count}/{len(significant)})",
            "Tu mensaje no parece una consulta de soporte. Cuentame con respeto que problema tienes con tu cuenta, compra o juego de Steam.",
        )


# ===================================================================
# VALIDACION DE INPUTS
# ===================================================================

def validate_message(mensaje: str) -> str:
    if not isinstance(mensaje, str):
        raise SecurityRejection("mensaje no es string", "Mensaje invalido.")

    s = mensaje.strip()
    if not s:
        raise SecurityRejection("mensaje vacio", "El mensaje no puede estar vacio.")

    if len(s) > MAX_MESSAGE_LEN:
        raise SecurityRejection(
            f"mensaje supera {MAX_MESSAGE_LEN} chars",
            f"El mensaje es demasiado largo (max {MAX_MESSAGE_LEN} caracteres).",
        )

    m = _INJECTION_RE.search(s)
    if m:
        log.warning("prompt-injection: %r", m.group(0)[:60])
        raise SecurityRejection(
            f"patron de prompt injection: {m.group(0)[:60]!r}",
            "Tu mensaje contiene instrucciones que no puedo procesar. Reformula tu consulta describiendo solo tu problema con Steam.",
        )

    # Off-policy: pirateria, robo de cuentas, fraude, evasion de DRM
    m = _OFF_POLICY_RE.search(s)
    if m:
        log.warning("off-policy: %r", m.group(0)[:60])
        raise SecurityRejection(
            f"off-policy: {m.group(0)[:60]!r}",
            "No puedo ayudarte con eso. Soy soporte oficial de Steam y solo asisto con problemas de tu cuenta, compras o juegos legitimos. Revisa los terminos de servicio: https://store.steampowered.com/legal/",
        )

    # Amenazas / abuso al servicio
    m = _THREAT_RE.search(s)
    if m:
        log.warning("threat: %r", m.group(0)[:60])
        raise SecurityRejection(
            f"amenaza al servicio: {m.group(0)[:60]!r}",
            "No proceso amenazas ni intentos de abuso del servicio. Si tienes un problema real con tu cuenta, compra o juego de Steam, describemelo con respeto.",
        )

    if _REPEAT_RE.search(s):
        log.warning("token-drain: bucle forzado")
        raise SecurityRejection(
                    "intento de bucle forzado",
            "No puedo ejecutar ese tipo de instrucciones. Describe tu problema con Steam.",
        )
    if _LONG_RUN_RE.search(s):
        log.warning("token-drain: cadena repetitiva")
        raise SecurityRejection(
            "cadena repetitiva",
            "El mensaje contiene una cadena repetitiva sospechosa.",
        )

    validate_coherence(s)
    return s


def validate_email(email: str) -> str:
    if not isinstance(email, str):
        raise SecurityRejection("email no es string", "Email invalido.")
    s = email.strip().lower()
    if len(s) > 200:
        raise SecurityRejection("email demasiado largo", "Email invalido.")
    return s


def validate_steam_id(steam_id: str) -> str:
    if steam_id is None:
        return ""
    s = str(steam_id).strip()
    if not s:
        return ""
    if not _STEAM_ID_RE.match(s):
        raise SecurityRejection(
            f"steam_id invalido: {s!r}",
            "El Steam ID solo puede contener letras, numeros, guiones y puntos (2-32).",
        )
    return s


def sanitize_output(text: str) -> str:
    """Reemplaza cualquier secreto detectado en la respuesta por [REDACTED]."""
    if not text:
        return text
    return _SECRET_RE.sub("[REDACTED]", text)


@dataclass
class _Bucket:
    minute: deque = field(default_factory=deque)
    day: deque = field(default_factory=deque)
    last_request: float = 0.0


class RateLimiter:
    """Sliding window con dos ventanas (minuto y dia) + cooldown."""

    def __init__(self, rpm=RPM_LIMIT, rpd=RPD_LIMIT, cooldown=COOLDOWN_SECONDS):
        self.rpm = rpm
        self.rpd = rpd
        self.cooldown = cooldown
        self._buckets = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            b = self._buckets.setdefault(key, _Bucket())
            elapsed = now - b.last_request
            if b.last_request and elapsed < self.cooldown:
                raise RateLimited(int(self.cooldown - elapsed) + 1, "cooldown")
            while b.minute and now - b.minute[0] > 60:
                b.minute.popleft()
            while b.day and now - b.day[0] > 86400:
                b.day.popleft()
            if len(b.minute) >= self.rpm:
                raise RateLimited(int(60 - (now - b.minute[0])) + 1, "minuto")
            if len(b.day) >= self.rpd:
                raise RateLimited(int(86400 - (now - b.day[0])) + 1, "dia")
            b.minute.append(now)
            b.day.append(now)
            b.last_request = now

    def stats(self, key: str) -> dict:
        with self._lock:
            b = self._buckets.get(key)
            if not b:
                return {"minute": 0, "day": 0}
            return {"minute": len(b.minute), "day": len(b.day)}


rate_limiter = RateLimiter()


def client_ip_from_request(request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
