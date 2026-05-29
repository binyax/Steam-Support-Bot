#!/usr/bin/env bash
# ----------------------------------------------------------------------
# deploy.sh - Despliegue/actualizacion idempotente para EC2 Ubuntu.
#
# Que hace:
#   1) Sincroniza el codigo (git pull si es un repo).
#   2) Crea/actualiza el venv en .venv y reinstala dependencias.
#   3) Copia (o enlaza) la config de Nginx y la unit de systemd.
#   4) Recarga Nginx y reinicia el servicio steam-bot.
#
# Uso:
#   chmod +x deploy.sh
#   sudo ./deploy.sh                  # primera vez, requiere root para nginx/systemd
#   ./deploy.sh --skip-system         # solo actualiza venv + reinicia el servicio
# ----------------------------------------------------------------------
set -euo pipefail

# ---- Config ----
APP_DIR="${APP_DIR:-/opt/steam-support-bot}"
APP_USER="${APP_USER:-ubuntu}"
VENV_DIR="${APP_DIR}/.venv"
PY_BIN="${PY_BIN:-python3}"
NGINX_SITE="/etc/nginx/sites-available/steam-bot"
NGINX_LINK="/etc/nginx/sites-enabled/steam-bot"
SYSTEMD_UNIT="/etc/systemd/system/steam-bot.service"

SKIP_SYSTEM=0
for arg in "$@"; do
  case "$arg" in
    --skip-system) SKIP_SYSTEM=1 ;;
    -h|--help)
      sed -n '2,18p' "$0"; exit 0 ;;
  esac
done

log() { printf "\033[1;36m[deploy]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[deploy] %s\033[0m\n" "$*" >&2; }

need_root() {
  if [[ $EUID -ne 0 ]]; then
    err "Esta seccion requiere sudo. Re-ejecuta:  sudo ./deploy.sh"
    exit 1
  fi
}

# ---- 1) Codigo ----
if [[ ! -d "$APP_DIR" ]]; then
  err "No existe $APP_DIR. Clona el repo primero (ver AWS_README.md)."
  exit 1
fi
cd "$APP_DIR"

if [[ -d ".git" ]]; then
  log "Actualizando codigo (git pull)…"
  git pull --ff-only || log "git pull fallo (puede ser repo local) — continuando"
fi

# ---- 2) venv + dependencias ----
log "Preparando entorno virtual en ${VENV_DIR}"
if [[ ! -d "$VENV_DIR" ]]; then
  "$PY_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip wheel

log "Instalando dependencias del proyecto…"
pip install -r requirements.txt
pip install -r agent/requirements-agent.txt
pip install -r webapp/requirements-web.txt
deactivate

# Asegurar que el .env existe
if [[ ! -f "${APP_DIR}/.env" ]]; then
  err "Falta ${APP_DIR}/.env  -> crea uno (ver .env.example)."
  exit 1
fi

# Dueno correcto
chown -R "${APP_USER}:${APP_USER}" "$APP_DIR" 2>/dev/null || true

# ---- 3) System (nginx + systemd) ----
if [[ $SKIP_SYSTEM -eq 0 ]]; then
  need_root
  log "Copiando configuracion de Nginx → ${NGINX_SITE}"
  cp "${APP_DIR}/deploy/nginx.conf" "$NGINX_SITE"
  ln -sf "$NGINX_SITE" "$NGINX_LINK"
  rm -f /etc/nginx/sites-enabled/default
  log "Validando Nginx…"
  nginx -t

  log "Copiando unit systemd → ${SYSTEMD_UNIT}"
  cp "${APP_DIR}/deploy/steam-bot.service" "$SYSTEMD_UNIT"
  systemctl daemon-reload
  systemctl enable steam-bot

  log "Recargando Nginx y arrancando steam-bot…"
  systemctl reload nginx
  systemctl restart steam-bot
else
  log "Solo reiniciando el servicio (--skip-system)"
  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl restart steam-bot || true
  fi
fi

# ---- 4) Healthcheck ----
log "Verificando healthcheck…"
sleep 2
if curl -fsS http://127.0.0.1/api/health >/dev/null; then
  log "OK: el servicio responde en :80/api/health"
else
  err "El healthcheck fallo. Revisa:  journalctl -u steam-bot -n 80 --no-pager"
  exit 1
fi

log "Despliegue completo. Abre http://<IP-publica-EC2>/ en tu navegador."
