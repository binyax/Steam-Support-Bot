"""
Herramientas autónomas del agente de soporte de Steam.

Cada tool hereda de ``BaseTool`` de CrewAI y puede ser invocada
por el agente cuando lo considere necesario:

    - ValidateUserTool:      valida datos del usuario, genera ticket y prioridad.
    - SendSupportEmailTool:  envía correo por SMTP (o guarda .eml si no hay creds).
    - KnowledgeBaseSearchTool: busca en la base de conocimiento (FAISS).
"""

from agent.tools.validation_tool import ValidateUserTool
from agent.tools.email_tool import SendSupportEmailTool
from agent.tools.knowledge_tool import KnowledgeBaseSearchTool

__all__ = ["ValidateUserTool", "SendSupportEmailTool", "KnowledgeBaseSearchTool"]
