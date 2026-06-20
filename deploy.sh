#!/usr/bin/env bash
# ----------------------------------------------------------------------
# deploy.sh - Despliegue/actualizacion con Docker Compose en EC2.
#
# Que hace:
#   1) Sincroniza el codigo (git pull si es un repo).
#   2) Verifica que existe .env y docker/compose disponibles.
#   3) Construye la imagen y levanta los servicios (app + nginx).
#   4) Espera healthcheck y muestra estado.
#
# Uso:
#   chmod +x deploy.sh
#   ./deploy.sh              # build + up
#   ./deploy.sh --no-build   # solo recrear contenedores
#   ./deploy.sh --logs       # muestra logs en vivo tras levantar
# ----------------------------------------------------------------------
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")" && pwd)}"
cd "$APP_DIR"

NO_BUILD=0
SHOW_LOGS=0
for arg in "$@"; do
  case "$arg" in
    --no-build) NO_BUILD=1 ;;
    --logs)     SHOW_LOGS=1 ;;
    -h|--help)  sed -n '2,17p' "$0"; exit 0 ;;
  esac
done

log() { printf "\033[1;36m[deploy]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[deploy] %s\033[0m\n" "$*" >&2; }

# ---------- Comprobaciones ----------
if ! command -v docker >/dev/null 2>&1; then
  err "Docker no esta instalado. Sigue AWS_README.md (paso 1)."
  exit 1
fi

# Selecciona "docker compose" v2 o "docker-compose" v1
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  err "Falta docker compose / docker-compose. Instala el plugin: 'sudo apt install docker-compose-plugin'."
  exit 1
fi

if [[ ! -f .env ]]; then
  err "Falta .env. Copia .env.example y rellena GITHUB_TOKEN antes de continuar."
  exit 1
fi

# ---------- Git pull (si aplica) ----------
if [[ -d .git ]]; then
  log "git pull --ff-only"
  git pull --ff-only || log "no pude hacer pull (puede ser repo local) - continuo"
fi

# ---------- Build + up ----------
if [[ $NO_BUILD -eq 0 ]]; then
  log "Construyendo imagen…"
  $DC build --pull
fi

log "Levantando servicios…"
$DC up -d --remove-orphans

# ---------- Esperar healthcheck ----------
log "Esperando que el backend este saludable…"
for i in {1..30}; do
  if curl -fsS http://127.0.0.1/api/health >/dev/null 2>&1; then
    log "OK: /api/health responde."
    log "Abre http://<IP-publica-EC2>/ en tu navegador."
    if [[ $SHOW_LOGS -eq 1 ]]; then
      log "Mostrando logs (Ctrl+C para salir, los servicios siguen)…"
      $DC logs -f
    fi
    exit 0
  fi
  sleep 2
done

err "El backend no respondio. Revisa los logs:  $DC logs --tail=120"
exit 1
