"""
Memoria del agente.

Para que el agente no se pierda en conversaciones largas de soporte le pusimos
dos tipos de memoria:

1. MEMORIA DE CORTO PLAZO (ShortTermMemory)
   Es como la "memoria de la sesion actual". Guarda los ultimos mensajes entre
   el usuario y el agente, mas el estado del caso (numero de ticket, prioridad,
   datos ya validados, etc.). Sirve para que el agente sea coherente dentro de
   la misma conversacion.

2. MEMORIA DE LARGO PLAZO (LongTermMemory)
   Es una base de datos vectorial con FAISS que se guarda en disco. Adentro
   metemos la base de conocimiento de Steam y resumenes de casos viejos. Cuando
   llega un mensaje nuevo, busca por parecido los fragmentos mas utiles (politicas,
   casos similares). Asi el agente responde con informacion real y no inventa.

`MemoryManager` junta las dos y es lo que terminan usando las tools y el crew.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from agent import config


# ===========================================================================
#  MEMORIA DE CORTO PLAZO
# ===========================================================================
class ShortTermMemory:
    """Recuerda los ultimos turnos de la conversacion y el estado del caso."""

    def __init__(self, window: int = 12) -> None:
        self._turns: Deque[Dict[str, str]] = deque(maxlen=window)
        # Estado del caso que se va completando a medida que avanza el soporte.
        self.case_state: Dict[str, Any] = {
            "ticket_id": None,
            "priority": None,
            "user_email": None,
            "user_validated": False,
            "missing_fields": [],
            "needs_human_escalation": False,
        }

    def add_turn(self, role: str, content: str) -> None:
        """Guarda un turno (role = 'usuario' | 'agente' | 'sistema')."""
        self._turns.append({"role": role, "content": content})

    def update_state(self, **kwargs: Any) -> None:
        """Actualiza el estado del caso con lo que le pasemos."""
        self.case_state.update({k: v for k, v in kwargs.items() if v is not None})

    def transcript(self) -> str:
        """Devuelve los ultimos turnos como texto, para meterselos al modelo."""
        if not self._turns:
            return "(todavia no hay turnos en esta sesion)"
        return "\n".join(f"[{t['role']}] {t['content']}" for t in self._turns)

    def summary(self) -> str:
        """Un resumen cortito del estado del caso para inyectar en los prompts."""
        s = self.case_state
        return (
            f"Ticket={s['ticket_id']} | Prioridad={s['priority']} | "
            f"Email={s['user_email']} | UsuarioValidado={s['user_validated']} | "
            f"CamposFaltantes={s['missing_fields']} | "
            f"EscalarHumano={s['needs_human_escalation']}"
        )


# ===========================================================================
#  MEMORIA DE LARGO PLAZO
# ===========================================================================
class LongTermMemory:
    """
    Memoria que se guarda en disco usando FAISS.

    - Carga el indice FAISS (o lo arma la primera vez desde la base de conocimiento).
    - Permite buscar por parecido (recuperacion semantica).
    - Permite "aprender": guardar resumenes de casos resueltos para despues.
    """

    def __init__(self) -> None:
        config.ensure_dirs()
        self._embeddings = None  # los creamos recien cuando se usan
        self._store = None

    # Inicializacion perezosa: asi no llamamos a la API hasta que haga falta.
    @property
    def store(self):
        if self._store is None:
            self._store = self._load_or_build_store()
        return self._store

    def _get_embeddings(self):
        if self._embeddings is None:
            self._embeddings = config.get_embeddings()
        return self._embeddings

    def _load_or_build_store(self):
        from langchain_community.vectorstores import FAISS

        index_dir = config.FAISS_INDEX_DIR
        # Si ya guardamos el indice antes, lo cargamos de disco.
        if (index_dir / "index.faiss").exists():
            return FAISS.load_local(
                str(index_dir),
                self._get_embeddings(),
                allow_dangerous_deserialization=True,
            )
        # Si no, lo construimos desde la base de conocimiento.
        return self._build_from_knowledge_base()

    def _build_from_knowledge_base(self):
        from langchain_community.vectorstores import FAISS
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        kb_file: Path = config.KNOWLEDGE_BASE_FILE
        if not kb_file.exists():
            raise FileNotFoundError(
                f"No encontramos la base de conocimiento en {kb_file}. "
                "Hay que crear ese archivo antes de usar la memoria de largo plazo."
            )
        text = kb_file.read_text(encoding="utf-8")
        splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=80)
        chunks = splitter.split_text(text)

        store = FAISS.from_texts(
            texts=chunks,
            embedding=self._get_embeddings(),
            metadatas=[{"source": "steam_support_kb", "chunk": i} for i in range(len(chunks))],
        )
        store.save_local(str(config.FAISS_INDEX_DIR))
        return store

    # --- lo que se usa desde afuera ---
    def retrieve(self, query: str, k: Optional[int] = None) -> List[str]:
        """Trae los k fragmentos mas parecidos a la consulta."""
        k = k or config.settings.retrieval_k
        docs = self.store.similarity_search(query, k=k)
        return [d.page_content.strip() for d in docs]

    def remember_case(self, summary: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Guarda el resumen de un caso ya resuelto:
          - lo mete al indice FAISS (para poder encontrarlo despues),
          - y lo escribe en un archivo de log por si queremos revisarlo.
        """
        metadata = metadata or {}
        metadata.setdefault("source", "case_history")
        metadata.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        # 1) Lo indexamos para futuras busquedas.
        self.store.add_texts([summary], metadatas=[metadata])
        self.store.save_local(str(config.FAISS_INDEX_DIR))

        # 2) Lo dejamos tambien en un log de texto.
        with config.MEMORY_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"summary": summary, **metadata}, ensure_ascii=False) + "\n")


# ===========================================================================
#  LAS DOS JUNTAS
# ===========================================================================
class MemoryManager:
    """Junta la memoria de corto y largo plazo en una sola cosa."""

    def __init__(self, window: int = 12) -> None:
        self.short = ShortTermMemory(window=window)
        self.long = LongTermMemory()

    def build_context(self, user_message: str) -> str:
        """
        Arma el bloque de contexto que le pasamos al agente: mezcla el estado del
        caso (corto plazo) con lo que encontramos en la base de conocimiento
        (largo plazo).
        """
        try:
            knowledge = self.long.retrieve(user_message)
        except Exception as exc:  # si falla la API de embeddings, seguimos igual
            knowledge = [f"(no pudimos consultar la memoria semantica: {exc})"]

        knowledge_block = "\n---\n".join(knowledge)
        return (
            "### Estado del caso (memoria corto plazo)\n"
            f"{self.short.summary()}\n\n"
            "### Ultimos mensajes\n"
            f"{self.short.transcript()}\n\n"
            "### Info relevante (memoria largo plazo / RAG)\n"
            f"{knowledge_block}"
        )


# Una sola instancia para reutilizar desde las tools y el crew.
memory_manager = MemoryManager()
