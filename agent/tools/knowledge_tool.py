"""
Tool de búsqueda semántica en la base de conocimiento.

Consulta la memoria de largo plazo (FAISS) construida a partir de
``agent/data/steam_support_kb.md`` y devuelve los fragmentos más
relevantes para la consulta del agente.

Requiere ``GITHUB_TOKEN`` configurado para generar los embeddings
(text-embedding-3-small via GitHub Models).
"""

from __future__ import annotations

from typing import Type

from pydantic import BaseModel, Field

from agent.memory import LongTermMemory

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]


# ──────────────────────────────────────────────────────────────────────
#  Schema de argumentos
# ──────────────────────────────────────────────────────────────────────
class _KBSearchSchema(BaseModel):
    """Parámetros para la búsqueda en la base de conocimiento."""

    query: str = Field(
        ..., description="Pregunta o texto de búsqueda en la base de conocimiento."
    )


# ──────────────────────────────────────────────────────────────────────
#  La tool
# ──────────────────────────────────────────────────────────────────────
class KnowledgeBaseSearchTool(BaseTool):
    """
    Busca en la base de conocimiento de Steam (FAISS) y devuelve los
    fragmentos más relevantes como texto plano.
    """

    name: str = "buscar_en_base_conocimiento"
    description: str = (
        "Busca información relevante en la base de conocimiento de Steam "
        "(políticas, procedimientos, guías). Devuelve los fragmentos más "
        "parecidos a la consulta."
    )
    args_schema: Type[BaseModel] = _KBSearchSchema

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ltm = LongTermMemory()

    def _run(self, query: str = "") -> str:
        """Ejecuta la búsqueda y devuelve los fragmentos concatenados."""
        if not query.strip():
            return "(No se proporcionó una consulta de búsqueda.)"

        fragments = self._ltm.retrieve(query)
        if not fragments:
            return "(No se encontraron resultados relevantes en la base de conocimiento.)"

        separator = "\n\n---\n\n"
        return separator.join(fragments)
