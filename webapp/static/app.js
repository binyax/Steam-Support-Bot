/* ------------------------------------------------------------------
   Steam Support Bot - frontend
   Conecta a /api/* con rutas RELATIVAS, asi el mismo bundle funciona
   tanto en localhost como en una IP publica de EC2.
   Usa EventSource (SSE) para mostrar el progreso del agente en vivo.
   ------------------------------------------------------------------ */

// API base puede sobreescribirse via window.API_BASE (no necesario en AWS,
// donde Nginx sirve el HTML y proxea /api en el mismo origen).
const API_BASE = (window.API_BASE || "").replace(/\/$/, "");
const api = (path) => `${API_BASE}${path}`;

const $ = (sel) => document.querySelector(sel);

const form        = $("#support-form");
const submitBtn   = $("#submit-btn");
const submitLabel = submitBtn.querySelector(".btn-label");
const submitSpin  = submitBtn.querySelector(".btn-spinner");
const resetBtn    = $("#reset-btn");
const outputCard  = $("#output-card");
const stepsList   = $("#steps");
const finalEl     = $("#final-text");
const statusPill  = $("#status-pill");
const healthEl    = $("#health-indicator");

let currentSource = null;

// ---------- Healthcheck ----------
async function checkHealth() {
  try {
    const r = await fetch(api("/api/health"), { cache: "no-store" });
    if (r.ok) {
      healthEl.classList.add("online");
      healthEl.classList.remove("offline");
      healthEl.innerHTML = '<span class="dot"></span> en linea';
      return;
    }
  } catch (_) {}
  healthEl.classList.remove("online");
  healthEl.classList.add("offline");
  healthEl.innerHTML = '<span class="dot"></span> sin conexion';
}

// ---------- UI helpers ----------
function setRunning(running) {
  submitBtn.disabled = running;
  submitSpin.hidden = !running;
  submitLabel.textContent = running ? "Procesando…" : "Enviar caso";
}

function setStatus(text, klass) {
  statusPill.textContent = text;
  statusPill.classList.remove("running", "done", "error");
  if (klass) statusPill.classList.add(klass);
}

function appendStep({ title, body, klass }) {
  const li = document.createElement("li");
  if (klass) li.classList.add(klass);
  const b = document.createElement("b");
  b.textContent = title;
  li.appendChild(b);
  li.appendChild(document.createTextNode(body));
  stepsList.appendChild(li);
  // autoscroll suave del panel
  li.scrollIntoView({ behavior: "smooth", block: "end" });
}

function resetOutput() {
  stepsList.innerHTML = "";
  finalEl.textContent = "";
  setStatus("en cola", null);
}

// ---------- Reset ----------
resetBtn.addEventListener("click", () => {
  if (currentSource) currentSource.close();
  currentSource = null;
  form.reset();
  outputCard.hidden = true;
  resetOutput();
  setRunning(false);
});

// ---------- Submit ----------
form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (currentSource) currentSource.close();

  const fd = new FormData(form);
  const params = new URLSearchParams({
    mensaje:  (fd.get("mensaje")  || "").toString(),
    email:    (fd.get("email")    || "").toString(),
    steam_id: (fd.get("steam_id") || "").toString(),
  });

  outputCard.hidden = false;
  resetOutput();
  setRunning(true);
  setStatus("ejecutando", "running");

  const src = new EventSource(api(`/api/support/stream?${params.toString()}`));
  currentSource = src;

  src.addEventListener("start", (ev) => {
    const data = safeParse(ev.data);
    appendStep({
      title: "Caso iniciado",
      body:  `Email: ${data.email || "-"} · Steam ID: ${data.steam_id || "-"}`,
    });
  });

  src.addEventListener("step", (ev) => {
    const data = safeParse(ev.data);
    appendStep({ title: "Paso del agente", body: data.text || "" });
  });

  src.addEventListener("task", (ev) => {
    const data = safeParse(ev.data);
    appendStep({
      title: "Tarea completada",
      body:  (data.description ? `→ ${data.description}\n\n` : "") + (data.output || ""),
      klass: "task",
    });
  });

  src.addEventListener("chunk", (ev) => {
    const data = safeParse(ev.data);
    finalEl.textContent += data.text || "";
    finalEl.scrollTop = finalEl.scrollHeight;
  });

  src.addEventListener("done", (ev) => {
    const data = safeParse(ev.data);
    if (data.resultado && !finalEl.textContent) {
      finalEl.textContent = data.resultado;
    }
    setStatus("listo", "done");
    setRunning(false);
    src.close();
    currentSource = null;
  });

  src.addEventListener("error", (ev) => {
    // El evento de error de EventSource no siempre trae payload;
    // el backend emite "error" con detalle.
    const data = safeParse(ev.data);
    if (data && data.detail) {
      appendStep({ title: "Error", body: data.detail, klass: "error" });
    }
    setStatus("error", "error");
    setRunning(false);
    src.close();
    currentSource = null;
  });

  src.addEventListener("close", () => {
    src.close();
    currentSource = null;
  });
});

function safeParse(s) {
  try { return JSON.parse(s); } catch { return {}; }
}

// ---------- Init ----------
checkHealth();
setInterval(checkHealth, 30000);
