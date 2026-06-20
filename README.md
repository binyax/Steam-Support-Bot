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
Instala todas las librerias necesarias utilizando los tres archivos de requirements (nucleo + agente + interfaz web):

pip install -r requirements.txt
pip install -r agent/requirements-agent.txt
pip install -r webapp/requirements-web.txt


4.1  Instalacion de dependencias (Linux)

Actualizar pip (Opcional)

* pip install --upgrade pip

Instalacion de dependencias

* pip install -r requirements.txt
* pip install -r agent/requirements-agent.txt
* pip install -r webapp/requirements-web.txt

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
├── AWS_README.md             # Guía paso a paso para desplegar en EC2 con Docker
├── deploy.sh                 # Script de despliegue automático (docker compose)
├── Dockerfile                # Imagen Python 3.11-slim, usuario non-root
├── docker-compose.yml        # Orquesta backend + Nginx + volumen de datos
├── .dockerignore             # Excluye secretos y artefactos locales de la imagen
├── requirements.txt          # Dependencias de los notebooks y del núcleo
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
│
├── webapp/                   # Interfaz web (FastAPI + SSE) — ver sección 13
│   ├── server.py             #   FastAPI: /api/health, /api/support, /api/support/stream
│   ├── security.py           #   Defensas: rate limit, filtros, sanitización (sección 15)
│   ├── requirements-web.txt  #   Dependencias específicas (fastapi, uvicorn, pydantic)
│   └── static/               #   Frontend (HTML/CSS/JS sin build step)
│       ├── index.html        #     UI estilo Steam Big Picture (topbar + sidebar + chat)
│       ├── styles.css        #     Tema oscuro con acento cyan + responsive
│       └── app.js            #     Chat conversacional + EventSource (SSE)
│
├── deploy/                   # Configuración para despliegue en EC2
│   └── nginx-docker.conf     #   Reverse proxy + rate limit + headers + SSE-friendly
│
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

---

# 🌐 Interfaz web (módulo `webapp/`)

Además de la CLI, el proyecto incluye una **interfaz web** que envuelve
`resolver_caso_soporte` con FastAPI y un frontend conversacional (estilo Steam
Big Picture: topbar + sidebar de categorías + chat con burbujas). El backend
expone tres endpoints:

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET`  | `/api/health` | Healthcheck para Nginx/monitoreo |
| `POST` | `/api/support` | Ejecuta el crew y devuelve el resultado en JSON |
| `GET`  | `/api/support/stream` | Server-Sent Events con el progreso en vivo |

## 13. Levantar la web en local

Con el entorno virtual activado y las dependencias instaladas (incluidas las
de `webapp/requirements-web.txt`):

```bash
# desde la raíz del proyecto
uvicorn webapp.server:app --host 127.0.0.1 --port 8000 --reload
```

Abre **http://127.0.0.1:8000/** en el navegador.

> ⚠️ No abras `webapp/static/index.html` con doble clic: las rutas a
> `/static/styles.css` y `/api/*` no resuelven con `file://`. Siempre accede
> por el servidor uvicorn.

El frontend usa **rutas relativas** (`/api/...`), por lo que el mismo bundle
funciona en localhost y en la IP pública de EC2 sin cambios.

---

# ☁️ Despliegue en AWS EC2 (Docker)

Para servir la interfaz y el agente en una instancia EC2 Ubuntu 22.04 con
**Docker Compose**, la guía paso a paso está en **[`AWS_README.md`](./AWS_README.md)**.
Incluye:

- Instalación de Docker Engine + Compose plugin en EC2.
- Configuración del Security Group (puerto 80).
- Clonado del repo en `/opt/steam-support-bot` y creación del `.env`.
- Despliegue automático con `./deploy.sh` (build + up + healthcheck).
- Comandos manuales equivalentes y operaciones del día a día.
- HTTPS opcional con Certbot.
- Troubleshooting habitual (502, SSE cortado, etc.).

---

# 🛡️ Seguridad del bot (módulo `webapp/security.py`)

El bot está endurecido contra los ataques cubiertos en el material
**3.3.1 Protocolos de Seguridad y Consideraciones Éticas** (Prompt Injection,
DoS, exfiltración de secretos). Resumen de defensas:

| Capa | Defensa | Donde |
|---|---|---|
| Validación | Tope 1500 chars, filtro de prompt injection (lista OWASP LLM01), filtro de token-drain | `webapp/security.py` |
| Validación | Sanitización estricta de email y Steam ID | `webapp/security.py` |
| Rate limit | 5 req/min, 30 req/día, cooldown 8 s por IP (memoria, sliding window) | `webapp/security.py` |
| Rate limit | `limit_req` 10 req/s burst 20 + `limit_conn` 10 por IP en Nginx | `deploy/nginx-docker.conf` |
| Presupuesto LLM | `max_tokens=1024`, `max_rpm=20`, `max_iter=8` por agente | `agent/config.py` + `agent/agents.py` |
| Timeout | Crew cortado a los 60 s vía `asyncio.wait_for` | `webapp/server.py` |
| Sanitización output | Censura tokens (`ghp_`, `lsv2_`, `sk-`, AWS keys, etc.) antes de enviar | `webapp/security.py` |
| Mensajes de error | Genéricos al cliente, traza completa solo en logs internos | `webapp/server.py` |
| HTTP headers | CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy | `webapp/server.py` + Nginx |
| Docker hardening | Usuario non-root, `cap_drop: ALL`, `no-new-privileges`, límites de CPU/RAM | `Dockerfile` + `docker-compose.yml` |
| Transparencia (XAI) | Trazas de cada llamada al LLM | LangSmith (`LANGSMITH_API_KEY` en `.env`) |

Toda decisión defensiva está documentada en `webapp/security.py` con
referencia a la categoría de OWASP Top 10 for LLM Applications.