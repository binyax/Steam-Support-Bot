"""
Definición de los agentes de soporte de Steam.
"""
from crewai import Agent
from agent import config
from agent.tools.validation_tool import ValidateUserTool
from agent.tools.knowledge_tool import KnowledgeBaseSearchTool
from agent.tools.email_tool import SendSupportEmailTool

def get_analyst_agent() -> Agent:
    return Agent(
        role="Analista de Soporte L1",
        goal="Analizar el caso del usuario, validar sus datos y buscar el procedimiento a seguir.",
        backstory=(
            "Eres el primer contacto de soporte de Steam. Tu trabajo es asegurar que "
            "tengamos toda la información necesaria del usuario, asignarle un ticket "
            "y buscar en la base de conocimiento interna la política oficial aplicable al caso."
        ),
        verbose=True,
        allow_delegation=False,
        llm=config.get_llm(),
        tools=[ValidateUserTool(), KnowledgeBaseSearchTool()]
    )

def get_communications_agent() -> Agent:
    return Agent(
        role="Especialista de Comunicaciones",
        goal="Redactar y enviar correos de soporte claros y empáticos basados en las políticas.",
        backstory=(
            "Eres el encargado de hablar con los usuarios de Steam. Tomas las políticas y "
            "procedimientos encontrados por el Analista y los transformas en correos útiles, "
            "amigables y orientados a la acción. Además te encargas de realizar el envío final usando las tools de correo."
        ),
        verbose=True,
        allow_delegation=False,
        llm=config.get_llm(),
        tools=[SendSupportEmailTool()]
    )
