# Informe Técnico — Agente Autónomo de Soporte para Steam
### Evaluación Parcial 2 · Proyecto *Steam-Support-Bot*

## 1. Resumen ejecutivo

Se implementó un **agente autónomo de soporte** capaz de analizar la solicitud de
un usuario de Steam y, por iniciativa propia, **enviar correos electrónicos de
soporte** (confirmación de tickets, alertas de seguridad y recuperación de
cuentas). La solución se integra de forma no intrusiva sobre la arquitectura
existente del proyecto —que ya emplea **LangChain** y **GitHub Models (GPT-4o)**—
encapsulándose en un paquete modular `agent/`. El agente se construye sobre
**CrewAI** y combina un esquema de **planificación jerárquica** de cuatro etapas,
una **memoria de dos niveles** (buffer de corto plazo + Vector Store FAISS de
largo plazo) y **tres herramientas autónomas**, una de las cuales realiza el envío
de correo con reintentos y degradación controlada.

---

## 2. Objetivos y alcance

**Objetivo general.** Dotar al *Steam-Support-Bot* de capacidad de acción
autónoma sobre el canal de correo, manteniendo coherencia de contexto a lo largo
de flujos de soporte prolongados.

**Objetivos específicos.**
1. Incorporar un framework de agentes compatible y escalable (CrewAI).
2. Diseñar una herramienta de envío de correo invocable por decisión del agente.
3. Implementar memoria de corto y largo plazo con recuperación semántica.
4. Definir un plan de tareas priorizado y demostrar decisiones adaptativas.

**Fuera de alcance.** Interfaz gráfica, autenticación real contra la API de Steam
y orquestación multiagente distribuida; se dejan como líneas de evolución.

---

## 3. Arquitectura de la solución

La arquitectura sigue un patrón de **agente orientado a tools con planificación
secuencial**. El punto de entrada `resolver_caso_soporte()` (en `crew.py`)
coordina tres subsistemas: **configuración** (LLM y embeddings sobre GitHub
Models), **memoria** (corto y largo plazo) y **crew** (agentes + tareas + tools).

| Componente | Archivo | Responsabilidad |
|------------|---------|-----------------|
| Configuración | `config.py` | LLM GPT-4o (LiteLLM→GitHub Models), embeddings, rutas, `.env` |
| Memoria | `memory.py` | Buffer conversacional + FAISS + log JSONL |
| Agentes | `agents.py` | Roles *Analista de Soporte* y *Comunicaciones* |
| Tareas | `tasks.py` | Plan jerárquico de 4 etapas encadenadas |
| Orquestación | `crew.py` | Ensamblaje, ejecución y persistencia de memoria |
| Herramientas | `tools/` | `validar_usuario`, `buscar_en_base_conocimiento`, `enviar_correo_soporte` |

El diagrama de orquestación completo se encuentra en
`agent/diagrams/orchestration.mermaid`.

---

## 4. Justificación técnica de las decisiones de diseño

### 4.1. Framework: CrewAI
Se evaluaron **LangChain Agents**, **LangGraph** y **CrewAI**. Se eligió CrewAI
por tres razones: (i) **modelado por roles**, que expresa con naturalidad la
división Analista/Comunicaciones propia de una mesa de soporte; (ii) **tools
tipadas con Pydantic**, que permiten que el LLM razone sobre cuándo invocarlas;
y (iii) **compatibilidad por LiteLLM** con el endpoint OpenAI-compatible de
GitHub Models, evitando reescribir la capa de conexión ya validada en los
notebooks 01–07. La escalabilidad queda garantizada: incorporar un nuevo rol o
una nueva herramienta es incremental.

### 4.2. Memoria semántica: FAISS
FAISS ofrece un Vector Store **local y persistente en disco** sin servicios
externos, lo que maximiza la **reproducibilidad**. El índice se construye una vez
desde `steam_support_kb.md`, se serializa en `data/faiss_index/` y se recarga en
ejecuciones posteriores. Esto proporciona **continuidad** entre sesiones: los
resúmenes de casos resueltos se reindexan (`remember_case`), de modo que el
agente "aprende" del historial.

### 4.3. Diseño defensivo de la herramienta de correo
La tool `enviar_correo_soporte` prioriza la **robustez operativa**. Intenta el
envío real por SMTP con **STARTTLS y reintentos**; si no existen credenciales o
el envío falla de forma persistente, **no interrumpe el flujo**: persiste el
mensaje como archivo `.eml` (modo simulado) y devuelve un `status` estructurado
(`sent` / `simulated` / `failed`). Esa señal es la base de la toma de decisiones
adaptativa del agente.

---

## 5. Memoria y gestión de contexto (IE3, IE4)

**Corto plazo (`ShortTermMemory`).** Buffer de ventana deslizante que conserva los
últimos turnos y un *estado del caso* (ticket, prioridad, email, validación,
campos faltantes, bandera de escalamiento). Garantiza coherencia intra-sesión.

**Largo plazo (`LongTermMemory`).** FAISS + `OpenAIEmbeddings`
(`text-embedding-3-small`). Fragmenta la base de conocimiento con
`RecursiveCharacterTextSplitter` (chunk 600 / overlap 80) y expone
`retrieve(query, k)` para **recuperación semántica**. La función `build_context()`
fusiona ambos niveles en el bloque de contexto que se inyecta al agente,
evitando que el bot "pierda el hilo".

---

## 6. Planificación y toma de decisiones (IE5, IE6)

### 6.1. Plan jerárquico
El proceso `Process.sequential` de CrewAI ejecuta cuatro tareas en orden de
prioridad, encadenadas mediante `context`:

```
1. Validar usuario  →  2. Buscar solución en KB  →  3. Redactar correo  →  4. Enviar correo
```

La etapa de validación tiene prioridad máxima: sin datos válidos el agente
solicita información en lugar de actuar a ciegas.

### 6.2. Decisiones adaptativas (evidencia)
El script `tests/test_agent_flows.py` documenta cinco escenarios verificables sin
red ni credenciales:

| Escenario | Condición del entorno | Reacción esperada del agente |
|-----------|-----------------------|------------------------------|
| A | Falta información del usuario | Reporta `missing_fields`, no genera ticket, pide datos |
| B | El envío de correo falla | `status=failed` + respaldo simulado → marca escalamiento |
| C | Chargeback/fraude | `requires_manual_escalation=true` (handoff obligatorio) |
| D | Caso válido | Genera `STM-XXXXXX` y prioridad coherente |
| E | Sesión multi-turno | La memoria de corto plazo conserva el contexto |

---

## 7. Ejemplos de flujos de soporte de Steam

**Flujo 1 — Cuenta comprometida (alerta de seguridad).**
El usuario reporta inicios de sesión desconocidos. El agente valida (prioridad
ALTA), recupera la política de seguridad de la KB, redacta un correo con el
ticket, instrucciones de Steam Guard y enlace oficial, y lo envía con
`category="seguridad"`.

**Flujo 2 — Recuperación de cuenta.**
Usuario sin acceso. Tras validar identidad, el agente confirma por correo la
apertura del caso de recuperación y los pasos de verificación, recordando que
nunca se solicita la contraseña completa.

**Flujo 3 — Facturación con chargeback (escalamiento).**
El validador detecta "chargeback" → escalamiento manual obligatorio. El agente
redacta un correo informando la derivación a un agente humano y registra el caso.

---

## 8. Limitaciones y trabajo futuro

La base de conocimiento es un corpus reducido y didáctico; en producción se
nutriría de la documentación oficial de Steam mediante ingesta periódica. La
validación de identidad es heurística (no consulta la API real de Steam). Como
evolución se contempla un **proceso jerárquico con agente *manager***, un Vector
Store gestionado para alto volumen, y métricas de calidad de respuesta con
LangSmith (ya configurado en el `.env` del proyecto).

---

## 9. Conclusiones

El agente cumple el objetivo de **envío autónomo de correos de soporte**
integrándose limpiamente sobre la base LangChain/GitHub Models existente. El
diseño —CrewAI por roles, memoria de dos niveles con FAISS, plan secuencial
priorizado y una herramienta de correo defensiva con decisiones adaptativas—
satisface los indicadores IE1–IE10 y ofrece una ruta de escalamiento clara hacia
un sistema de soporte productivo.
