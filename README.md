# 🎬 CineCadiz

Plataforma de streaming personal de código abierto para organizar y reproducir contenido desde listas M3U/IPTV y fuentes RSS.

> **⚠️ AVISO LEGAL — DISCLAIMER**
>
> Este proyecto **no alberga, almacena, distribuye ni enlaza a ningún contenido multimedia**.
> Es únicamente una interfaz frontend que lee listas M3U/M3U8 e importa feeds RSS
> que el propio usuario introduce en el panel de administración.
> El autor no se hace responsable del uso que cada usuario haga de la aplicación
> ni de los contenidos a los que apunten las listas que configure.
> **Úsalo exclusivamente con contenido que tengas derecho a reproducir.**

---

## Características

- 🎬 Organización automática de películas y series
- 📡 Importación de listas M3U/M3U8 (IPTV, VOD)
- 📰 Importación de fuentes RSS (cinemacity.cc y otras)
- 🔍 Búsqueda y filtros por tipo, año y género
- ▶️ Reproductor integrado con soporte HLS.js
- 📱 Diseño responsive (desktop y móvil)
- 🔄 Deduplicación automática de contenido
- 🛡️ Filtro automático de canales en directo

## Tecnologías

| Capa | Stack |
|------|-------|
| Backend | Python · Flask · SQLAlchemy · SQLite |
| Frontend | HTML5 · CSS3 · JavaScript vanilla |
| Streaming | HLS.js |
| Iconos | Bootstrap Icons |

## Instalación

### Requisitos
- Python 3.10+
- pip

### Pasos

```bash
# Clonar el repositorio
git clone https://github.com/Raulcadiz/cinemacity-web.git
cd cinemacity-web/backend

# Instalar dependencias
pip install -r requirements.txt

# Arrancar en desarrollo
python app.py
```

La aplicación estará disponible en `http://localhost:8000`.

## Configuración

Variables de entorno (o valores por defecto):

| Variable | Defecto | Descripción |
|----------|---------|-------------|
| `SECRET_KEY` | `cinemacity-cambia-esta-clave` | Clave secreta Flask |
| `ADMIN_USER` | `admin` | Usuario del panel admin |
| `ADMIN_PASSWORD` | `admin1234` | Contraseña del panel admin |
| `DOWNLOAD_TIMEOUT` | `300` | Segundos máximos para descargar una lista M3U |
| `AUTO_SCAN` | `0` | `1` para escaneo automático de links caídos |
| `SCAN_INTERVAL_HOURS` | `24` | Intervalo entre escaneos automáticos |
| `SCAN_BATCH_SIZE` | `100` | Links por lote en cada escaneo |

> **Cambia `ADMIN_PASSWORD` antes de desplegarlo en producción.**

## Panel de administración

Accede en `/admin` con las credenciales configuradas.

Desde el panel puedes:
- Añadir / eliminar listas M3U
- Añadir / eliminar fuentes RSS
- Re-importar listas manualmente
- Escanear links caídos (manual)
- Ver estadísticas de contenido

## Despliegue en producción (PythonAnywhere)

Consulta `backend/DEPLOY_PYTHONANYWHERE.md` para instrucciones detalladas.

## Estructura del proyecto

```
cinemacity-web/
├── backend/
│   ├── app.py              # Factory Flask
│   ├── config.py           # Configuración
│   ├── models.py           # Modelos SQLAlchemy
│   ├── routes_api.py       # API REST pública /api/
│   ├── routes_admin.py     # Panel de administración /admin/
│   ├── m3u_parser.py       # Parser M3U con filtros
│   ├── rss_importer.py     # Importador RSS
│   ├── link_checker.py     # Verificador de links
│   ├── scheduler.py        # Tareas en background
│   ├── static/             # CSS, JS, imágenes
│   └── templates/          # Plantillas HTML
└── README.md
```

## Licencia

MIT — libre para uso personal y privado.

---

*Este proyecto no alberga ningún contenido multimedia. Toda la responsabilidad del contenido reproducido recae sobre el usuario que configura las listas M3U.*
