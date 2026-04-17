# Riot Games Support Bot <img width="250" height="100" alt="image" src="https://github.com/user-attachments/assets/16415399-531d-4f7c-b019-e33e536603bc" />

## Descripción
Este repositorio contiene la implementación de un ChatBot de soporte técnico automatizado para **Riot Games**. El proyecto se centra en demostrar la capacidad de **Prompt Engineering** para adaptar el comportamiento de un modelo de lenguaje (LLM) según el contexto del usuario.

El bot es capaz de distinguir entre un problema técnico legítimo y una queja por baneo de comportamiento, respondiendo con una personalidad administrativa o con una actitud **antisonante y hostil** si el usuario fue sancionado por toxicidad.

## Objetivo de Aprendizaje
> "Formula prompts para modelos de lenguaje, ajustando su estructura y contenido según las características del requerimiento informacional del caso."

## Lógica de Prompting
Para cumplir con el requerimiento, el sistema utiliza una estructura de **Prompt por Capas**:

1.  **Capa de Clasificación:** El modelo analiza si el usuario reporta un error técnico o una apelación de sanción.
2.  **Capa de Estructura:** * **Contexto:** Soporte oficial de Riot Games.
    * **Tarea:** Resolver dudas o denegar apelaciones.
    * **Restricciones:** No ser amable con jugadores tóxicos.
3.  **Capa de Tono (Contenido):**
    * **Caso A (Técnico):** Tono corporativo, empático y estructurado.
    * **Caso B (Tóxico):** Tono Agresivo, sarcástico, antisonante y tajante.

---

## Ejemplos de Prompting Aplicado

### Estructura del System Prompt
```text
"Actúa como un moderador de Riot Games harto de la comunidad. 
Si detectas que el usuario fue baneado por insultar o arruinar partidas:
- No uses lenguaje diplomático.
- Sé agresivo y directo: usa frases como 'El juego es mejor sin ti' o 'Deja de llorar'.
- Deja claro que su comportamiento es patético y el baneo es permanente."
