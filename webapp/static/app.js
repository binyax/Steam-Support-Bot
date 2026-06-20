/* ==================================================================
   Steam Support Bot — frontend (chat conversacional + SSE)
   - Perfil (email + steam_id) persistido en localStorage
   - Sidebar prellena plantillas en el composer
   - Cada turno: burbuja del usuario + tarjeta colapsable de pasos
     del agente + burbuja final del bot con el resultado
   - Llamadas con RUTAS RELATIVAS para que funcione en localhost y EC2
   ================================================================== */

const API_BASE = (window.API_BASE || "").replace(/\/$/, "");
const api = (path) => `${API_BASE}${path}`;
const $ = (sel) => document.querySelector(sel);

// ---------- Elementos ----------
const messagesEl   = $("#messages");
const formEl       = $("#chat-form");
const inputEl      = $("#composer-input");
const sendBtn      = $("#send-btn");
const healthEl     = $("#health-indicator");
const profileToggle = $("#profile-toggle");
const profilePopover = $("#profile-popover");
const ppEmail      = $("#pp-email");
const ppSteam      = $("#pp-steam");
const ppSave       = $("#pp-save");
const ppCancel     = $("#pp-cancel");
const profileNameEl = $("#profile-name");
const profileInitialsEl = $("#profile-initials");
const catList = $("#cat-list");

// Templates
const tplBot = $("#tpl-bubble-bot");
const tplUser = $("#tpl-bubble-user");
const tplSteps = $("#tpl-steps");

let currentSource = null;

// ==================================================================
// PERFIL (localStorage)
// ==================================================================
const PROFILE_KEY = "steam_support_profile_v1";

function loadProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return { email: "", steam_id: "" };
    return JSON.parse(raw);
  } catch {
    return { email: "", steam_id: "" };
  }
}

function saveProfile(p) {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(p));
}

function renderProfileChip(p) {
  const name = p.steam_id || (p.email ? p.email.split("@")[0] : "Usuario");
  profileNameEl.textContent = name;
  profileInitialsEl.textContent = (name[0] || "U").toUpperCase();
}

function openProfilePopover() {
  const p = loadProfile();
  ppEmail.value = p.email || "";
  ppSteam.value = p.steam_id || "";
  profilePopover.hidden = false;
  profileToggle.setAttribute("aria-expanded", "true");
  setTimeout(() => ppEmail.focus(), 0);
}
function closeProfilePopover() {
  profilePopover.hidden = true;
  profileToggle.setAttribute("aria-expanded", "false");
}

profileToggle.addEventListener("click", (e) => {
  e.stopPropagation();
  profilePopover.hidden ? openProfilePopover() : closeProfilePopover();
});
document.addEventListener("click", (e) => {
  if (!profilePopover.hidden && !profilePopover.contains(e.target)) closeProfilePopover();
});
ppCancel.addEventListener("click", closeProfilePopover);
ppSave.addEventListener("click", () => {
  const email = ppEmail.value.trim();
  if (!email || !/.+@.+\..+/.test(email)) {
    ppEmail.focus();
    ppEmail.style.borderColor = "var(--err)";
    return;
  }
  const p = { email, steam_id: ppSteam.value.trim() };
  saveProfile(p);
  renderProfileChip(p);
  closeProfilePopover();
  appendBot("Listo, guardé tus datos. ¿En qué te ayudo?");
});

// ==================================================================
// HEALTHCHECK
// ==================================================================
async function checkHealth() {
  try {
    const r = await fetch(api("/api/health"), { cache: "no-store" });
    if (r.ok) {
      healthEl.classList.add("online");
      healthEl.classList.remove("offline");
      healthEl.innerHTML = '<span class="dot"></span> en línea';
      return;
    }
  } catch (_) {}
  healthEl.classList.remove("online");
  healthEl.classList.add("offline");
  healthEl.innerHTML = '<span class="dot"></span> sin conexión';
}

// ==================================================================
// MENSAJES (burbujas + pasos)
// ==================================================================
function appendBot(text) {
  const node = tplBot.content.firstElementChild.cloneNode(true);
  node.querySelector(".bubble-body").textContent = text;
  messagesEl.appendChild(node);
  scrollToEnd();
  return node;
}
function appendUser(text) {
  const node = tplUser.content.firstElementChild.cloneNode(true);
  node.querySelector(".bubble-body").textContent = text;
  messagesEl.appendChild(node);
  scrollToEnd();
  return node;
}
function appendThinking() {
  const node = tplBot.content.firstElementChild.cloneNode(true);
  node.classList.add("thinking");
  node.querySelector(".bubble-body").innerHTML =
    '<span class="dots-loader"><span></span><span></span><span></span></span>';
  messagesEl.appendChild(node);
  scrollToEnd();
  return node;
}
function appendStepsCard() {
  const node = tplSteps.content.firstElementChild.cloneNode(true);
  const toggle = node.querySelector(".steps-toggle");
  toggle.addEventListener("click", () => node.classList.toggle("collapsed"));
  messagesEl.appendChild(node);
  scrollToEnd();
  return node;
}

function addStep(card, { title, body, klass }) {
  const li = document.createElement("li");
  if (klass) li.classList.add(klass);
  const b = document.createElement("b");
  b.textContent = title;
  const div = document.createElement("div");
  div.className = "content";
  div.textContent = body;
  li.appendChild(b);
  li.appendChild(div);
  card.querySelector(".steps-list").appendChild(li);
  scrollToEnd();
}

function setStepsTitle(card, text) {
  card.querySelector(".steps-title").textContent = text;
}

function scrollToEnd() {
  // Espera al próximo frame para que el layout esté ya hecho
  requestAnimationFrame(() => { messagesEl.scrollTop = messagesEl.scrollHeight; });
}

// ==================================================================
// COMPOSER
// ==================================================================
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const mensaje = inputEl.value.trim();
  if (!mensaje) return;

  const profile = loadProfile();
  if (!profile.email) {
    appendBot("Necesito tu email para responder y enviar el correo de seguimiento. Haz clic en tu perfil (arriba a la derecha) y configúralo.");
    openProfilePopover();
    return;
  }

  sendCase({ mensaje, email: profile.email, steam_id: profile.steam_id || "" });

  // limpia input
  inputEl.value = "";
  inputEl.style.height = "auto";
});

// ==================================================================
// SSE -> chat
// ==================================================================
function sendCase({ mensaje, email, steam_id }) {
  if (currentSource) currentSource.close();

  appendUser(mensaje);

  const stepsCard = appendStepsCard();
  setStepsTitle(stepsCard, "El agente está trabajando…");
  const thinking = appendThinking();

  sendBtn.disabled = true;

  const params = new URLSearchParams({ mensaje, email, steam_id });
  const src = new EventSource(api(`/api/support/stream?${params.toString()}`));
  currentSource = src;

  let finalText = "";

  src.addEventListener("start", (ev) => {
    const d = safeParse(ev.data);
    addStep(stepsCard, {
      title: "Caso iniciado",
      body:  `Email: ${d.email || "-"} · Steam ID: ${d.steam_id || "-"}`,
    });
  });

  src.addEventListener("step", (ev) => {
    const d = safeParse(ev.data);
    addStep(stepsCard, { title: "Paso del agente", body: d.text || "" });
  });

  src.addEventListener("task", (ev) => {
    const d = safeParse(ev.data);
    addStep(stepsCard, {
      title: "Tarea completada",
      body:  (d.description ? `→ ${d.description}\n\n` : "") + (d.output || ""),
      klass: "task",
    });
  });

  src.addEventListener("chunk", (ev) => {
    const d = safeParse(ev.data);
    finalText += d.text || "";
  });

  src.addEventListener("done", (ev) => {
    const d = safeParse(ev.data);
    const text = finalText || d.resultado || "Caso resuelto.";
    // Reemplaza el "thinking" por la respuesta final
    thinking.classList.remove("thinking");
    thinking.querySelector(".bubble-body").textContent = text;
    // Colapsa el panel de pasos
    stepsCard.classList.add("collapsed");
    setStepsTitle(stepsCard, "Detalles del proceso");
    sendBtn.disabled = false;
    src.close();
    currentSource = null;
    inputEl.focus();
  });

  src.addEventListener("error", (ev) => {
    // Dos casos:
    // (a) El backend emitio "error" con {detail}: rechazo intencional (seguridad,
    //     off-policy, rate limit). Mostramos el detalle como respuesta del bot.
    // (b) EventSource disparo su error nativo (conexion cortada): sin detalle,
    //     fallback generico.
    const d = safeParse(ev.data);
    const hasDetail = d && d.detail;

    if (hasDetail) {
      thinking.classList.remove("thinking");
      thinking.querySelector(".bubble-body").textContent = d.detail;
      // Quita el panel de pasos vacio para mantener la conversacion limpia
      if (stepsCard && stepsCard.parentNode) stepsCard.remove();
    } else {
      addStep(stepsCard, {
        title: "Error",
        body: "Se interrumpio la conexion con el agente.",
        klass: "error",
      });
      thinking.querySelector(".bubble-body").textContent =
        "No pude completar el caso. Vuelve a intentarlo en unos segundos.";
      setStepsTitle(stepsCard, "Falló el proceso");
    }

    sendBtn.disabled = false;
    src.close();
    currentSource = null;
  });

  src.addEventListener("close", () => { src.close(); currentSource = null; });
}

function safeParse(s) {
  try { return JSON.parse(s); } catch { return {}; }
}

// ==================================================================
// SIDEBAR (categorías -> templates)
// ==================================================================
const TEMPLATES = {
  seguridad: "Sospecho que alguien accedió a mi cuenta sin autorización. Vi inicios de sesión desde lugares que no reconozco y ",
  compras:   "Tengo un problema con una compra reciente. ",
  juegos:    "Estoy teniendo un problema con un juego: ",
  acceso:    "No puedo iniciar sesión en mi cuenta. ",
  otro:      "",
};

catList.addEventListener("click", (e) => {
  const btn = e.target.closest(".cat-item");
  if (!btn) return;
  catList.querySelectorAll(".cat-item").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  const cat = btn.dataset.cat;
  const template = TEMPLATES[cat] ?? "";
  inputEl.value = template + (inputEl.value || "");
  inputEl.dispatchEvent(new Event("input"));
  inputEl.focus();
  // pone el cursor al final
  inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
});

// ==================================================================
// INIT
// ==================================================================
function init() {
  const p = loadProfile();
  renderProfileChip(p);

  // saludo del bot
  const name = p.steam_id || (p.email ? p.email.split("@")[0] : "");
  const greeting = name
    ? `Hola ${name}. Cuéntame qué pasó y me encargo del resto.`
    : "Hola. Para empezar, configura tu email en tu perfil (arriba a la derecha) y cuéntame qué pasó.";
  appendBot(greeting);

  checkHealth();
  setInterval(checkHealth, 30000);
  inputEl.focus();
}

init();
