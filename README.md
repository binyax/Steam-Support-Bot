# Steam-Support-Bot

🛠️ Guia de configuracion inicial
Se deben seguir estos pasos para replicar el entorno de desarrollo y ejecutar el Steam Support Bot en local

---

1. Clonar el repositorio
Primero se debe obtener una copia local del proyecto, copiando el link del repo. En la bash se debera pegar lo siguiente:

git clone https://github.com/binyax/Steam-Support-Bot.git
cd Steam-Support-Bot

---

2. Crear el entorno virtual
Para aislar las dependencias del proyecto y evitar conflictos de sistema, creamos un entorno virtual. En la bash se debera pegar lo siguiente:

* python -m venv .venv

* (Linux) python3 -m venv .venv
---

3. Activar el entorno
Activa el entorno de trabajo segun tu terminal (en este proyecto usamos Git Bash):

* source .venv/Scripts/activate
* (Linux) source .venv/bin/activate

Sabrás que está activo porque aparecerá (.venv) al inicio de tu línea de comandos.

---

4. Instalacion de dependencias
Instala todas las librerias necesarias utilizando el archivo llamado requirements.txt:

pip install -r requirements.txt


4.1  Instalacion de dependencias (Linux)

Actualizar pip (Opcional)

* pip install --upgrade pip

Instalacion de dependencias

* pip install -r requirements.txt

(Si este da errores con langsmith se puede probar limpiando la cache del pip)

* pip install --no-cache-dir -r requirements.txt

---

5. Configuración de Variables de Entorno (.env)
El sistema requiere llaves de acceso para funcionar, las cuales se gestionan de forma segura localmente:

Crea un archivo llamado .env en la carpeta raiz.

Copia el contenido del archivo .env.example y pegalo en tu nuevo archivo .env

Remplaza los valores de ejemplo por tus credenciales reales (GITHUB_TOKEN y LANGSMITH_API_KEY).

Nota de Seguridad: El archivo .env está incluido en el .gitignore, por lo que las credenciales nunca se subiran al repositorio publico.

---

# 📁 Estructura del proyecto

```
Steam-Support-Bot/
├── README.md                 # Esta guía
├── requirements.txt          # Dependencias de los notebooks
├── .env.example              # Plantilla de variables de entorno
│
├── notebooks/                # Notebooks didácticos (paso a paso) + bot integrado
│   ├── 01_conexion_github_models.ipynb
│   ├── 02_langchain_model_api.ipynb
│   ├── 02.1_langchain_streaming.ipynb
│   ├── 03_zero_shot.ipynb
│   ├── 04_few_shot.ipynb
│   ├── 05_chain_of_thought.ipynb
│   ├── 06_rag.ipynb
│   ├── 07_evaluacion_rag.ipynb
│   ├── 08_bot_integrado.ipynb   # Bot final que integra todo
│   ├── 09_agente_demo.ipynb     # Demo: importa y ejecuta el agente del módulo agent/
│   └── reglas_steam.txt         # Base de conocimiento para el RAG (notebook 06)
│
├── agent/                    # Agente autónomo de soporte (CrewAI) — ver sección siguiente
├── tests/                    # Pruebas de decisión adaptativa del agente
└── docs/                     # Informe técnico
```

## Notebooks didácticos (carpeta `notebooks/`)

Recorren la construcción del bot de forma incremental:

| Notebook | Tema |
|----------|------|
| 01 | Conexión con GitHub Models (GPT-4o) |
| 02 | LangChain Model API (abstracción, temperatura, mensajes) |
| 02.1 | Streaming de respuestas en tiempo real |
| 03 | Clasificación de tickets *Zero-Shot* |
| 04 | Clasificación *Few-Shot* (casos ambiguos) |
| 05 | Razonamiento *Chain of Thought* |
| 06 | Arquitectura RAG (FAISS sobre `reglas_steam.txt`) |
| 07 | Evaluación del sistema RAG (fidelidad / anti-alucinaciones) |
| 08 | **Bot integrado**: RAG + clasificación + CoT + juez + memoria + streaming |
| 09 | **Demo del agente autónomo**: importa el paquete `agent/` y lo ejecuta paso a paso |

Los notebooks se ejecutan desde la carpeta `notebooks/` (el notebook 06 carga
`reglas_steam.txt` desde ese mismo directorio).

---

# 🤖 Agente Autónomo de Soporte (módulo `agent/`)

Además de los notebooks didácticos (`notebooks/01..08`), el proyecto incluye un
**agente autónomo** capaz de **enviar correos de soporte de Steam por decisión
propia**: confirmaciones de ticket, alertas de seguridad y recuperación de
cuentas. Está construido con **CrewAI** sobre el mismo backend del proyecto
(GitHub Models / GPT-4o), usa **FAISS** como memoria semántica de largo plazo y
envía correos por **SMTP con respaldo simulado**.

## 6. ¿Qué hace el agente?

Cuando recibe el mensaje de un usuario, ejecuta por sí mismo un plan jerárquico
de cuatro etapas, en orden de prioridad:

1. **Validar usuario** → comprueba que hay datos mínimos y genera un ticket `STM-XXXXXX` con prioridad.
2. **Buscar solución** → recupera el procedimiento oficial desde la base de conocimiento (RAG/FAISS).
3. **Redactar correo** → escribe un correo claro, empático y accionable.
4. **Enviar correo** → lo envía y **reacciona** al resultado (reintenta o escala a un humano si falla).

## 7. Estructura del módulo y función de cada archivo

```
agent/
├── __init__.py               # Marca el paquete e indica el punto de entrada (resolver_caso_soporte)
├── config.py                 # Configuración central: carga .env, construye el LLM (GPT-4o vía
│                             #   GitHub Models) y los embeddings, y define todas las rutas
├── memory.py                 # Memoria del agente:
│                             #   - ShortTermMemory: buffer de la conversación + estado del caso
│                             #   - LongTermMemory: Vector Store FAISS + log JSONL (recuperación semántica)
│                             #   - MemoryManager: une ambas y arma el contexto que se inyecta al agente
├── agents.py                 # Define los 2 agentes CrewAI: "Analista de Soporte" y
│                             #   "Especialista en Comunicaciones" (rol, objetivo, tools y LLM)
├── tasks.py                  # Define el plan de 4 tareas encadenadas (Validar→Buscar→Redactar→Enviar)
├── crew.py                   # Orquesta agentes + tareas en un Crew secuencial y expone la función
│                             #   resolver_caso_soporte() (entrypoint de alto nivel + integración de memoria)
├── main.py                   # Interfaz de línea de comandos (CLI) para ejecutar un caso
├── requirements-agent.txt    # Dependencias extra del agente (crewai, faiss-cpu, langchain-community...)
│
├── tools/                    # Herramientas autónomas que el agente decide invocar
│   ├── __init__.py           #   Reexporta las tres tools
│   ├── email_tool.py         #   enviar_correo_soporte: SMTP real (STARTTLS + reintentos) con
│   │                         #     fallback simulado (.eml); devuelve status sent/simulated/failed
│   ├── knowledge_tool.py     #   buscar_en_base_conocimiento: búsqueda semántica en FAISS
│   └── validation_tool.py    #   validar_usuario: valida datos, crea ticket y asigna prioridad
│
├── diagrams/
│   └── orchestration.mermaid # Diagrama de orquestación de componentes (Mermaid)
│
└── data/
    ├── steam_support_kb.md   # Base de conocimiento de soporte (alimenta la memoria de largo plazo)
    ├── faiss_index/          # Índice vectorial persistido (se genera automáticamente)
    ├── email_outbox/         # Correos guardados en modo simulado (.eml) (se genera automáticamente)
    └── long_term_memory.jsonl# Log de casos resueltos (se genera automáticamente)

tests/
└── test_agent_flows.py       # Pruebas de decisión adaptativa (funcionan sin red ni credenciales)

docs/
└── Informe_Tecnico_EP2.md    # Informe técnico del agente (justificación de diseño, flujos, IE)
```

## 8. Instalación de dependencias del agente

Con el entorno virtual ya activado (ver pasos 2–4), instala las dependencias
adicionales del agente:

```bash
pip install -r agent/requirements-agent.txt
```

## 9. Variables de entorno del agente (envío de correo)

El agente reutiliza tu `GITHUB_TOKEN` ya configurado. Para el **envío real de
correos** añade además estas variables a tu `.env` (son **opcionales**: si no las
pones, el agente funciona en **modo simulado** y guarda los correos como `.eml`
en `agent/data/email_outbox/`):

```ini
SMTP_HOST="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USER="tu_correo@gmail.com"
SMTP_PASSWORD="tu_app_password_de_16_digitos"   # App Password de Gmail (requiere 2FA), NO tu contraseña normal
SMTP_FROM="tu_correo@gmail.com"
```

> 💡 En Gmail debes generar un *App Password* desde tu cuenta de Google (con la
> verificación en dos pasos activada). Nunca uses tu contraseña habitual.

## 10. Cómo ejecutar el agente

Ejecuta **siempre desde la raíz del proyecto** (la carpeta que contiene `agent/`),
usando la sintaxis de módulo `-m`:

```bash
# Opción A — caso demo precargado (simula una cuenta posiblemente comprometida)
python -m agent.main

# Opción B — caso personalizado
python -m agent.main \
  --email usuario@ejemplo.com \
  --mensaje "No puedo iniciar sesion y vi cargos que no reconozco" \
  --steam-id miUsuario
```

También puedes usarlo desde tu propio código o un notebook:

```python
from agent.crew import resolver_caso_soporte

resultado = resolver_caso_soporte(
    mensaje_usuario="Creo que me robaron la cuenta, hay inicios de sesion raros",
    email_usuario="usuario@ejemplo.com",
    steam_id="miUsuario",
)
print(resultado)
```

## 11. Ejecutar las pruebas (decisiones adaptativas)

Estas pruebas demuestran cómo reacciona el agente ante condiciones cambiantes
(falta de datos, fallo de envío, escalamiento manual) y **no requieren red ni
credenciales**:

```bash
python -m tests.test_agent_flows      # imprime PASS/FAIL por escenario
# o, con pytest instalado:
pytest tests/test_agent_flows.py -v
```

## 12. Justificación técnica (resumen)

- **CrewAI** se eligió por su modelado por roles, sus tools tipadas (el LLM decide
  cuándo invocarlas) y su compatibilidad vía LiteLLM con el endpoint de GitHub
  Models, sin cambiar el backend ya validado en los notebooks.
- **FAISS** aporta una memoria semántica local y persistente (sin servicios
  externos), ideal para reproducibilidad y para dar continuidad entre sesiones.
- La **tool de correo** es defensiva: nunca rompe el flujo; ante un fallo deja
  respaldo `.eml` y emite una señal que el agente usa para escalar a un humano.

> La documentación ampliada del agente está en `agent/README.md` y el informe
> técnico completo en `docs/Informe_Tecnico_EP2.md`.