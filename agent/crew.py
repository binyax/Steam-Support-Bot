"""
Orquestación del CrewAI para soporte de Steam.
"""
from crewai import Crew, Process
from agent.tasks import create_tasks
from agent.memory import memory_manager

def resolver_caso_soporte(mensaje_usuario: str, email_usuario: str, steam_id: str = "") -> str:
    """
    Punto de entrada principal. Ejecuta el crew completo basándose en un mensaje inicial del usuario.
    """
    # 1. Armar contexto inicial que verán los agentes
    contexto = (
        f"Mensaje del usuario: {mensaje_usuario}\n"
        f"Email: {email_usuario}\n"
        f"Steam ID: {steam_id}\n\n"
        f"Contexto adicional desde la memoria:\n{memory_manager.build_context(mensaje_usuario)}"
    )

    # 2. Crear las tareas (que instancian a los agentes internamente)
    tasks = create_tasks(contexto)
    analyst = tasks[0].agent
    comms = tasks[2].agent

    # 3. Orquestar el crew secuencial
    crew = Crew(
        agents=[analyst, comms],
        tasks=tasks,
        process=Process.sequential,
        verbose=True
    )

    # 4. Ejecutar el flujo de trabajo
    # Jupyter Notebooks corren un event loop por defecto. CrewAI lanza un error si
    # intentamos usar kickoff() normal dentro de un event loop.
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        is_async = loop.is_running()
    except RuntimeError:
        is_async = False

    if is_async:
        import nest_asyncio
        nest_asyncio.apply()
        # Usamos la version asíncrona pero bloqueamos hasta que termine
        # para no romper el código original del usuario.
        resultado = loop.run_until_complete(crew.kickoff_async())
    else:
        resultado = crew.kickoff()

    return str(resultado)
