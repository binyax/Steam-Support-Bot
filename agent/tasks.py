"""
Definición de las tareas (el plan jerárquico) del agente.
"""
from crewai import Task
from agent.agents import get_analyst_agent, get_communications_agent

def create_tasks(context_str: str) -> list[Task]:
    analyst = get_analyst_agent()
    comms = get_communications_agent()

    t1_validate = Task(
        description=(
            f"Analiza la siguiente información inicial del caso:\n{context_str}\n\n"
            "Utiliza la herramienta 'validar_usuario' para generar un ticket y asignar prioridad. "
            "Asegúrate de pasar los argumentos correctos a la tool basándote en la información recibida."
        ),
        expected_output="Un JSON con el ticket generado y el resultado de la validación.",
        agent=analyst
    )

    t2_search = Task(
        description=(
            "Con base en el problema identificado en la validación, utiliza la tool 'buscar_en_base_conocimiento' "
            "para buscar el procedimiento oficial a aplicar."
        ),
        expected_output="El texto exacto del procedimiento o política aplicable de Steam recuperado de la base de conocimiento.",
        agent=analyst
    )

    t3_draft = Task(
        description=(
            "Usando la información de la política encontrada, redacta el asunto y el cuerpo "
            "de un correo de soporte en español. Debe incluir el número de ticket generado. Sé empático y claro."
        ),
        expected_output="El asunto y el cuerpo del correo redactado, listo para ser enviado.",
        agent=comms
    )

    t4_send = Task(
        description=(
            "Utiliza la herramienta 'enviar_correo_soporte' para enviar el correo que acabas de redactar al usuario. "
            "La categoría debe reflejar el tipo de problema (por ejemplo 'alerta_seguridad' o 'ticket')."
        ),
        expected_output="El estado final del envío que devuelve la tool (sent, simulated, o failed).",
        agent=comms
    )

    return [t1_validate, t2_search, t3_draft, t4_send]
