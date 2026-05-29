# Despliegue en AWS EC2 (Ubuntu 22.04)

Guía paso a paso para servir **Steam-Support-Bot** con su interfaz web en una
instancia EC2. La arquitectura es:

```
Internet → :80 Nginx → estáticos (HTML/CSS/JS)
                    → /api/* → Uvicorn :8000 (FastAPI) → agente CrewAI
```

No usa Docker: todo corre con `systemd` + `nginx` nativos.

---

## 0. Prerrequisitos

- Una instancia EC2 **Ubuntu 22.04 LTS** (t3.small o superior recomendado: el
  agente carga FAISS + embeddings).
- Acceso por SSH como usuario `ubuntu`.
- En el **Security Group** de la instancia abrir:
  - `22/tcp` (SSH) desde tu IP.
  - `80/tcp` (HTTP) desde `0.0.0.0/0`.
  - *Opcional:* `443/tcp` si más adelante añades HTTPS con Certbot.

> No es necesario abrir el puerto 8000: Uvicorn escucha solo en `127.0.0.1` y
> Nginx hace de proxy.

---

## 1. Conectarse e instalar paquetes del sistema

```bash
ssh -i tu-clave.pem ubuntu@<IP-PUBLICA-EC2>

sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx curl
```

---

## 2. Clonar el proyecto en `/opt`

```bash
sudo mkdir -p /opt
sudo chown ubuntu:ubuntu /opt
cd /opt
git clone https://github.com/binyax/Steam-Support-Bot.git steam-support-bot
cd steam-support-bot
```

> Si el repo es privado, usa un *deploy key* o un PAT.

---

## 3. Crear el archivo `.env`

```bash
cp .env.example .env
nano .env
```

Rellena al menos:

```ini
GITHUB_TOKEN="ghp_xxx..."
GITHUB_BASE_URL="https://models.inference.ai.azure.com"
LANGSMITH_TRACING="true"
LANGSMITH_API_KEY="ls_..."
LANGSMITH_PROJECT="steam_support_bot"

# Opcional: para envío real de correos (si no, el bot guarda .eml en data/email_outbox)
SMTP_HOST="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USER="tu-correo@gmail.com"
SMTP_PASSWORD="app_password_de_16_chars"
SMTP_FROM="tu-correo@gmail.com"
```

Asegura permisos:

```bash
chmod 600 .env
```

---

## 4. Despliegue automático

El script hace todo: venv, dependencias, Nginx, systemd, healthcheck.

```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

Al terminar deberías ver: `OK: el servicio responde en :80/api/health`.

Abre en tu navegador:

```
http://<IP-PUBLICA-EC2>/
```

---

## 5. Pasos equivalentes manuales (si prefieres no usar el script)

### 5.1 Crear el venv e instalar dependencias

```bash
cd /opt/steam-support-bot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
pip install -r agent/requirements-agent.txt
pip install -r webapp/requirements-web.txt
deactivate
```

### 5.2 Configurar Nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/steam-bot
sudo ln -sf /etc/nginx/sites-available/steam-bot /etc/nginx/sites-enabled/steam-bot
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 5.3 Configurar systemd

```bash
sudo cp deploy/steam-bot.service /etc/systemd/system/steam-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now steam-bot
```

### 5.4 Verificar

```bash
curl -i http://127.0.0.1/api/health
# debería responder {"status":"ok",...}

sudo systemctl status steam-bot --no-pager
sudo journalctl -u steam-bot -f         # logs en vivo
```

---

## 6. Actualizar el código en futuras versiones

```bash
cd /opt/steam-support-bot
sudo ./deploy.sh                  # vuelve a hacer pull + reinstalar + reiniciar
# o, si no cambió nada del sistema:
./deploy.sh --skip-system
```

---

## 7. Habilitar HTTPS (opcional, recomendado)

Si tienes un dominio apuntando a la IP de la instancia:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tu-dominio.com
```

Certbot reescribe `/etc/nginx/sites-available/steam-bot` para escuchar también
en `:443`. El frontend no necesita cambios (usa rutas relativas).

---

## 8. Troubleshooting rápido

| Síntoma | Qué revisar |
|---|---|
| `502 Bad Gateway` en `/api/...` | `sudo systemctl status steam-bot` — el proceso no está corriendo. Logs: `journalctl -u steam-bot -n 100`. |
| `nginx -t` falla | Revisa que `deploy/nginx.conf` fue copiado y que no hay otro site con `listen 80 default_server`. |
| `EnvironmentError: GITHUB_TOKEN` | Falta `.env` o falta la variable. |
| El frontend carga pero `/api/health` da `Failed to fetch` | El Security Group no tiene el puerto 80 abierto. |
| SSE se corta tras unos segundos | Si pones un Load Balancer delante, sube `idle_timeout` a >300s y asegúrate de que pasa el header `X-Accel-Buffering: no`. |

---

## 9. Comandos útiles del día a día

```bash
# Reiniciar solo el backend (sin tocar Nginx)
sudo systemctl restart steam-bot

# Ver logs en vivo
sudo journalctl -u steam-bot -f

# Recargar Nginx tras editar la config
sudo nginx -t && sudo systemctl reload nginx

# Probar el endpoint sin abrir el navegador
curl -N "http://127.0.0.1/api/support/stream?mensaje=hola&email=test@example.com&steam_id=demo"
```
