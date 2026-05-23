"""
Agente de soporte para Steam.

Este paquete tiene el agente que armamos con CrewAI para mandar correos de
soporte a los usuarios (confirmar tickets, avisar de problemas de seguridad,
ayudar a recuperar cuentas). Se apoya en el mismo GPT-4o de GitHub Models que
usamos en los notebooks.

Resumen de las partes:
    - config: configuracion (modelo, embeddings, rutas, .env).
    - memory: memoria de corto y largo plazo (buffer + FAISS).
    - tools:  las herramientas que el agente puede usar.
    - agents/tasks/crew: el agente en si y como se organiza el trabajo.

Lo mas facil para usarlo:
    >>> from agent.crew import resolver_caso_soporte
    >>> resolver_caso_soporte(mensaje_usuario="...", email_usuario="...")
"""

__version__ = "1.0.0"
__all__ = ["config", "memory", "tools"]
