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

---

3. Activar el entorno
Activa el entorno de trabajo segun tu terminal (en este proyecto usamos Git Bash):

* source .venv/Scripts/activate

Sabrás que está activo porque aparecerá (.venv) al inicio de tu línea de comandos.

---

4. Instalacion de dependencias
Instala todas las librerias necesarias utilizando el archivo llamado requirements.txt:

pip install -r requirements.txt

---

5. Configuración de Variables de Entorno (.env)
El sistema requiere llaves de acceso para funcionar, las cuales se gestionan de forma segura localmente:

Crea un archivo llamado .env en la carpeta raiz.

Copia el contenido del archivo .env.example y pegalo en tu nuevo archivo .env

Remplaza los valores de ejemplo por tus credenciales reales (GITHUB_TOKEN y LANGSMITH_API_KEY).


Nota de Seguridad: El archivo .env está incluido en el .gitignore, por lo que las credenciales nunca se subiran al repositorio publico.