# Despliegue en PythonAnywhere

## 1. Sube el proyecto

Desde la consola Bash de PythonAnywhere:

```bash
# Clona o sube por ZIP. Si usas ZIP, extrae en:
mkdir -p ~/cinemacity
# Sube el contenido de /backend/ a ~/cinemacity/
```

## 2. Instala dependencias

```bash
cd ~/cinemacity
pip3 install --user -r requirements.txt
```

## 3. Configura variables de entorno (opcional pero recomendado)

Añade en tu `.bashrc` o en la configuración de la web app:

```bash
export SECRET_KEY="pon-aqui-una-clave-larga-y-aleatoria"
export ADMIN_USER="tu_usuario"
export ADMIN_PASSWORD="tu_contraseña_segura"
```

## 4. Configura la Web App en PythonAnywhere

- Ve a **Web** → **Add a new web app**
- Elige **Manual configuration** → **Python 3.11**
- En **Source code**: `/home/TU_USUARIO/cinemacity`
- En **Working directory**: `/home/TU_USUARIO/cinemacity`

## 5. Edita el fichero WSGI de PythonAnywhere

Ve a la sección **WSGI configuration file** y reemplaza todo el contenido con:

```python
import sys
import os

# Añadir el directorio al path
sys.path.insert(0, '/home/TU_USUARIO/cinemacity')

# Variables de entorno (alternativa a .bashrc)
os.environ['SECRET_KEY'] = 'pon-aqui-una-clave-larga-y-aleatoria'
os.environ['ADMIN_USER'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'tu_contraseña_segura'

from wsgi import application
```

## 6. Archivos estáticos

En la sección **Static files** de tu web app:
- URL: `/static/`  →  Directorio: `/home/TU_USUARIO/cinemacity/static`

## 7. Tareas programadas (Plan Hacker o superior)

En **Tasks** → **Scheduled tasks**, agrega:

```
# Cada 24 horas — escanear links caídos
python3 /home/TU_USUARIO/cinemacity/scan_task.py
```

Crea el archivo `scan_task.py`:

```python
import sys
sys.path.insert(0, '/home/TU_USUARIO/cinemacity')
from app import create_app
from link_checker import scan_dead_links

app = create_app()
result = scan_dead_links(app, batch_size=200)
print(result)
```

## 8. Reload y probar

- Haz click en **Reload** en la sección Web
- Accede a: `https://TU_USUARIO.pythonanywhere.com/`
- Panel admin: `https://TU_USUARIO.pythonanywhere.com/admin/`

## Estructura de archivos esperada

```
~/cinemacity/
├── app.py
├── config.py
├── models.py
├── routes_api.py
├── routes_admin.py
├── m3u_parser.py
├── link_checker.py
├── scheduler.py
├── wsgi.py
├── requirements.txt
├── scan_task.py          ← crear manualmente
├── instance/
│   └── cinemacity.db     ← se crea automáticamente
├── templates/
│   ├── index.html
│   └── admin/
│       ├── base.html
│       ├── login.html
│       ├── dashboard.html
│       ├── lists.html
│       └── content.html
└── static/
    ├── css/style.css
    ├── js/script.js
    ├── js/service-worker.js
    └── manifest.json
```

## Cambiar contraseña admin

Edita `config.py` o usa variables de entorno:

```python
ADMIN_USER = 'tu_usuario'
ADMIN_PASSWORD = 'contraseña_segura_123'
```
