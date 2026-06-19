"""
Configuracion del agente.

Aca juntamos toda la parte de configuracion en un solo archivo para no repetirla:
cargar el .env, crear el modelo (GPT-4o a traves de GitHub Models) y los
embeddings, y dejar definidas las rutas que usa el agente. Lo hicimos asi para
que si mas adelante queremos cambiar de modelo, solo haya que tocar este archivo
y no andar buscando por todos lados.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# --- Rutas del proyecto ---
# Desde agent/config.py subimos a agent/ y de ahi a la raiz del proyecto.
AGENT_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = AGENT_DIR.parent

DATA_DIR: Path = AGENT_DIR / "data"
KNOWLEDGE_BASE_FILE: Path = DATA_DIR / "steam_support_kb.md"
FAISS_INDEX_DIR: Path = DATA_DIR / "faiss_index"            # indice de la memoria a largo plazo
MEMORY_LOG_FILE: Path = DATA_DIR / "long_term_memory.jsonl"  # historial de casos
EMAIL_OUTBOX_DIR: Path = DATA_DIR / "email_outbox"          # aca caen los correos en modo simulado

# Cargamos el .env de la raiz (las mismas llaves que usan los notebooks).
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
# Por si se ejecuta desde otra carpeta, intentamos tambien el .env por defecto.
load_dotenv()


@dataclass
class Settings:
    """Aca guardamos toda la configuracion junta para tenerla a mano."""

    # Credenciales de GitHub Models (las mismas del resto del proyecto)
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GITHUB_BASE_URL", "https://models.inference.ai.azure.com"
        )
    )

    # Modelos que usamos
    chat_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    temperature: float = 0.2  # bajo a proposito: en soporte queremos respuestas parejas

    # --- Limites defensivos contra token-drain / DoS (ver webapp/security.py) ---
    # Tope duro de tokens generados por llamada al LLM.
    llm_max_tokens: int = 1024
    # Maximas requests por minuto al endpoint del LLM.
    llm_max_rpm: int = 20
    # Iteraciones maximas por agente CrewAI (evita bucles de razonamiento).
    agent_max_iter: int = 8
    # Reintentos del cliente HTTP ante 429/5xx. Bajo a proposito: cuando GitHub
    # Models devuelve 429 (cuota diaria), reintentar solo desperdicia mas cuota.
    llm_max_retries: int = 1
    # Reintentos a nivel de tarea (CrewAI). Bajo por la misma razon.
    agent_max_retry_limit: int = 1

    # Datos del SMTP para mandar correos de verdad
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_from: str = field(
        default_factory=lambda: os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "soporte@steam-bot.local"))
    )

    # Cuantos fragmentos traemos de la memoria semantica en cada busqueda
    retrieval_k: int = 3

    @property
    def smtp_configured(self) -> bool:
        """True solo si tenemos usuario y clave de SMTP para enviar de verdad."""
        return bool(self.smtp_user and self.smtp_password)

    def validate(self) -> None:
        """Avisa si falta el token de GitHub, que es lo minimo para que funcione."""
        if not self.github_token:
            raise EnvironmentError(
                "No encontramos el GITHUB_TOKEN. Revisa tu archivo .env "
                "(hay un ejemplo en .env.example) antes de correr el agente."
            )


settings = Settings()


# Creamos el LLM y los embeddings solo cuando se necesitan (asi no llamamos
# a la API si solo queremos probar las partes que no la usan).
def get_llm():
    """
    Devuelve el modelo que usa CrewAI, apuntando a GitHub Models (GPT-4o).

    CrewAI usa LiteLLM por debajo. El prefijo ``openai/`` le dice que el endpoint
    habla el mismo "idioma" que la API de OpenAI, que es justo lo que ofrece
    GitHub Models. Asi reutilizamos el mismo GPT-4o de los notebooks.
    """
    settings.validate()
    from crewai import LLM

    return LLM(
        model=f"openai/{settings.chat_model}",
        base_url=settings.github_base_url,
        api_key=settings.github_token,
        temperature=settings.temperature,
        # Limites defensivos: previenen token-drain y respuestas infladas
        max_tokens=settings.llm_max_tokens,
        # Frente a 429 reintentar solo gasta mas cuota: cortamos en 1 intento
        max_retries=settings.llm_max_retries,
    )


def get_embeddings():
    """
    Devuelve el motor de embeddings (LangChain) para la memoria semantica.

    Usamos ``text-embedding-3-small`` por GitHub Models, igual que en el
    notebook 06 del RAG, para no mezclar tecnologias distintas.
    """
    settings.validate()
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        base_url=settings.github_base_url,
        api_key=settings.github_token,
        model=settings.embedding_model,
    )


def ensure_dirs() -> None:
    """Crea las carpetas de datos si todavia no existen (no pasa nada si ya estan)."""
    for path in (DATA_DIR, FAISS_INDEX_DIR.parent, EMAIL_OUTBOX_DIR):
        path.mkdir(parents=True, exist_ok=True)
