"""
Backup de la base de datos SQLite.
- Copia la BD a un directorio de backups con timestamp.
- Mantiene solo los últimos MAX_BACKUPS archivos.
- Puede enviar el backup por Telegram como documento.
"""
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio de backups: ../backups/ relativo al backend
_BACKEND_DIR = Path(__file__).parent
BACKUP_DIR   = _BACKEND_DIR.parent / 'backups'
MAX_BACKUPS  = 7   # días de retención


def _db_path(app) -> Path:
    """Devuelve la ruta al fichero SQLite de la app."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    # sqlite:////ruta/absoluta o sqlite:///ruta/relativa
    if uri.startswith('sqlite:///'):
        path = uri[len('sqlite:///'):]
        if not os.path.isabs(path):
            path = os.path.join(app.root_path, path)
        return Path(path)
    # Fallback al path por convención
    return _BACKEND_DIR / 'instance' / 'cinemacity.db'


def create_backup(app) -> Path:
    """
    Crea una copia de la BD con timestamp.
    Elimina los backups más antiguos si se supera MAX_BACKUPS.
    Devuelve la ruta del fichero de backup creado.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    db_path = _db_path(app)
    if not db_path.exists():
        raise FileNotFoundError(f'BD no encontrada: {db_path}')

    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = BACKUP_DIR / f'cinemacity_{ts}.db'

    shutil.copy2(db_path, out_path)
    logger.info(f'[Backup] Creado: {out_path} ({out_path.stat().st_size // 1024} KB)')

    # Rotación: eliminar backups más antiguos
    backups = sorted(BACKUP_DIR.glob('cinemacity_*.db'))
    while len(backups) > MAX_BACKUPS:
        old = backups.pop(0)
        old.unlink()
        logger.info(f'[Backup] Eliminado backup antiguo: {old.name}')

    return out_path


def send_backup_telegram(app, backup_path: Path) -> tuple[bool, str]:
    """
    Envía el fichero de backup como documento a todos los chat_ids configurados.
    Devuelve (ok, mensaje).
    """
    import requests as _req
    from telegram_bot import _get_config

    token, chat_ids = _get_config(app)
    if not token or not chat_ids:
        return False, 'Bot no configurado o desactivado.'

    size_kb = backup_path.stat().st_size // 1024
    caption = (
        f'💾 <b>Backup CineCadiz</b>\n'
        f'📅 {datetime.now().strftime("%d/%m/%Y %H:%M")}\n'
        f'📦 {backup_path.name} ({size_kb} KB)'
    )

    ok_count = 0
    for chat_id in chat_ids:
        try:
            with open(backup_path, 'rb') as f:
                r = _req.post(
                    f'https://api.telegram.org/bot{token}/sendDocument',
                    data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'},
                    files={'document': (backup_path.name, f, 'application/octet-stream')},
                    timeout=60,
                )
            if r.ok:
                ok_count += 1
            else:
                logger.warning(f'[Backup] Telegram error {r.status_code} → {chat_id}: {r.text[:200]}')
        except Exception as e:
            logger.error(f'[Backup] Error enviando a {chat_id}: {e}')

    if ok_count == len(chat_ids):
        return True, f'Backup enviado correctamente a {ok_count} destino(s).'
    elif ok_count > 0:
        return True, f'Backup enviado a {ok_count}/{len(chat_ids)} destinos.'
    else:
        return False, 'No se pudo enviar el backup a ningún destino.'


def list_backups() -> list[dict]:
    """Lista los backups disponibles ordenados del más reciente al más antiguo."""
    if not BACKUP_DIR.exists():
        return []
    backups = sorted(BACKUP_DIR.glob('cinemacity_*.db'), reverse=True)
    return [
        {
            'name':     b.name,
            'size_kb':  b.stat().st_size // 1024,
            'created':  datetime.fromtimestamp(b.stat().st_mtime).strftime('%d/%m/%Y %H:%M'),
        }
        for b in backups
    ]
