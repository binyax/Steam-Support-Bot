# Despliegue en AWS EC2 con Docker

Guía paso a paso para servir el **Steam-Support-Bot** (interfaz web + agente
CrewAI) en una instancia EC2 Ubuntu usando **Docker Compose**. La arquitectura
es:

```
Internet → :80 Nginx (contenedor) → estáticos (HTML/CSS/JS)
                                  → /api/* → FastAPI :8000 (contenedor)
                                                  → agente CrewAI
```

Hardening aplicado: usuario non-root dentro de la imagen, capabilities
removidas, límites de CPU/memoria, rate limit en Nginx y en el backend,
headers de seguridad, sanitización de inputs/outputs.

---

## 0. Prerrequisitos

- Una instancia EC2 **Ubuntu 22.04 LTS** (al menos t3.small — el agente carga
  FAISS + embeddings).
- Acceso por SSH como usuario `ubuntu`.
- En el **Security Group** abrir:
  - `22/tcp` (SSH) desde tu IP.
  - `80/tcp` (HTTP) desde `0.0.0.0/0`.
  - *Opcional* `443/tcp` si añades HTTPS más adelante.

---

## 1. Conectarse e instalar Docker

```bash
ssh -i tu-clave.pem ubuntu@<IP-PUBLICA-EC2>

# Actualizar paquetes
sudo apt update && sudo apt upgrade -y

# Instalar Docker Engine + Docker Compose plugin (oficial Docker)
sudo apt install -y ca-certificates curl gnupg git

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Permitir a "ubuntu" usar docker sin sudo (relogin después)
sudo usermod -aG docker ubuntu
```

Cierra la sesión SSH y vuelve a entrar para que el grupo `docker` aplique:

```bash
exit
ssh -i tu-clave.pem ubuntu@<IP-PUBLICA-EC2>
docker version       # debe mostrar Client + Server
docker compose version
```

---

## 2. Clonar el proyecto

```bash
sudo mkdir -p /opt
sudo chown ubuntu:ubuntu /opt
cd /opt
git clone https://github.com/binyax/Steam-Support-Bot.git steam-support-bot
cd steam-support-bot
```

> Si el repo es privado, usa un deploy key o un PAT con scope `repo:read`.

---

## 3. Crear el archivo `.env`

```bash
cp .env.example .env
nano .env
```

Mínimo necesario:

```ini
GITHUB_TOKEN="github_pat_xxx..."           # PAT con permiso models:read
GITHUB_BASE_URL="https://models.inference.ai.azure.com"
LANGSMITH_TRACING="true"
LANGSMITH_API_KEY="lsv2_..."
LANGSMITH_PROJECT="steam_support_bot"

# Opcional (envío real de correos)
SMTP_HOST="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USER="tu-correo@gmail.com"
SMTP_PASSWORD="app_password_16_chars"
SMTP_FROM="tu-correo@gmail.com"
```

Permisos restringidos:

```bash
chmod 600 .env
```

---

## 4. Despliegue automático

```bash
chmod +x deploy.sh
./deploy.sh
```

El script:

1. Hace `git pull` (si aplica).
2. Verifica que existe `.env` y que Docker funciona.
3. Construye la imagen (`docker compose build`).
4. Levanta los contenedores en segundo plano (`docker compose up -d`).
5. Espera el healthcheck en `http://127.0.0.1/api/health`.

Al terminar:

```
http://<IP-PUBLICA-EC2>/
```

---

## 5. Equivalente manual (sin el script)

```bash
cd /opt/steam-support-bot
docker compose build --pull
docker compose up -d
docker compose ps                 # ver estado
docker compose logs -f app        # logs del backend
docker compose logs -f nginx      # logs del proxy
curl -i http://127.0.0.1/api/health
```

---

## 6. Operaciones del día a día

```bash
# Actualizar tras un git pull:
cd /opt/steam-support-bot
./deploy.sh

# Recrear contenedores sin reconstruir imagen:
./deploy.sh --no-build

# Logs en vivo:
docker compose logs -f app
docker compose logs -f nginx

# Reiniciar solo el backend:
docker compose restart app

# Detener todo:
docker compose down

# Ver consumo de recursos:
docker stats steam-bot-app steam-bot-nginx
```

---

## 7. HTTPS opcional con Certbot

Si tienes un dominio apuntando a la IP de la instancia, el camino más fácil
es ejecutar Certbot **fuera** del contenedor (en el host) y montar los certs
en Nginx. Para una demo rápida, lo más simple es:

```bash
sudo docker run -it --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -p 80:80 \
  certbot/certbot certonly --standalone -d tu-dominio.com
```

Después montas `/etc/letsencrypt` en el contenedor Nginx y añades un block
`listen 443 ssl;` en `deploy/nginx-docker.conf`. Para producción real,
considera Traefik o AWS Certificate Manager + ALB.

---

## 8. Seguridad implementada

El bot incluye estas mitigaciones de fábrica (mira `webapp/security.py` y
`deploy/nginx-docker.conf`):

| Capa | Mitigación | Donde |
|---|---|---|
| Nginx | `limit_req` 10 req/s burst 20 por IP | `nginx-docker.conf` |
| Nginx | `limit_conn` 10 conexiones simultáneas por IP | `nginx-docker.conf` |
| Nginx | `client_max_body_size 256k`, timeouts cortos | `nginx-docker.conf` |
| Nginx | Bloqueo de `/.env`, `/.git` | `nginx-docker.conf` |
| App | Rate limit: 5 req/min, 30 req/día, cooldown 8s por IP | `security.py` |
| App | Filtro de prompt injection (patrones OWASP LLM01) | `security.py` |
| App | Filtro de "token-drain" (repeticiones, loops) | `security.py` |
| App | Sanitización de salidas (redacta secretos antes de enviar) | `security.py` |
| App | Timeout duro del crew = 60s | `server.py` |
| App | `max_iter=8`, `max_rpm=20`, `max_tokens=1024` | `agents.py` / `config.py` |
| App | Mensajes de error genéricos al cliente (sin stack traces) | `server.py` |
| App | Headers HTTP de seguridad (CSP, XFO, nosniff…) | `server.py` |
| Docker | Usuario non-root, `no-new-privileges`, `cap_drop: ALL` | `docker-compose.yml` |
| Docker | Límites de CPU/RAM | `docker-compose.yml` |

---

## 9. Troubleshooting

| Síntoma | Qué revisar |
|---|---|
| `Cannot connect to the Docker daemon` | Falta el `usermod -aG docker ubuntu` + relogin. |
| `502 Bad Gateway` en `/api/...` | `docker compose logs app` para ver la excepción real. |
| `401 Bad credentials` del LLM | `.env` mal o `GITHUB_TOKEN` sin scope `models:read`. |
| El frontend carga pero `/api/health` no responde | El Security Group no tiene el puerto 80 abierto. |
| SSE se corta a los pocos segundos | Si pones un ALB delante, sube `idle_timeout` a >300s. |
| Build falla por falta de memoria | Usa al menos t3.small; t2.micro a veces no compila `faiss-cpu`. |
| 429 "Demasiadas solicitudes" durante demo | Es lo esperado: rate limit estricto. Ajusta valores en `security.py` si necesitas. |
