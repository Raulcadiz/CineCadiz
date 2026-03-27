"""
Notificaciones Telegram para CineCadiz.
Envía alertas al canal/grupo configurado en el panel de administración.
"""
import logging
from datetime import datetime

import requests as _requests

logger = logging.getLogger(__name__)
_TG_API  = "https://api.telegram.org/bot{token}/sendMessage"
_TG_BASE = "https://api.telegram.org/bot{token}/{method}"


# ─────────────────────────────────────────────
# Primitiva de envío
# ─────────────────────────────────────────────

def _parse_chat(chat_id: str) -> tuple[str, int | None]:
    """
    Parsea chat_id con soporte para tópicos de grupo.
    Formato normal:  "-1001234567890"  → ("-1001234567890", None)
    Formato tópico:  "-1001234567890/3014" → ("-1001234567890", 3014)
    """
    s = str(chat_id).strip()
    if '/' in s:
        parts = s.split('/', 1)
        try:
            return parts[0], int(parts[1])
        except ValueError:
            pass
    return s, None


def _send(token: str, chat_id: str, text: str) -> bool:
    """Envía un mensaje. Devuelve True si fue exitoso."""
    if not token or not chat_id or not text:
        return False
    try:
        real_chat_id, thread_id = _parse_chat(chat_id)
        payload = {
            "chat_id": real_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        r = _requests.post(
            _TG_API.format(token=token),
            json=payload,
            timeout=10,
        )
        if not r.ok:
            logger.warning(f"[Telegram] Error {r.status_code} enviando a {chat_id}: {r.text[:200]}")
        return r.ok
    except Exception as e:
        logger.error(f"[Telegram] Excepción: {e}")
        return False


def _get_config(app):
    """Devuelve (token, [chat_ids]) o (None, []) si no hay config activa."""
    import json
    from models import TelegramConfig
    with app.app_context():
        cfg = TelegramConfig.query.first()
        if not cfg or not cfg.enabled or not cfg.token:
            return None, []
        ids = []
        try:
            ids = json.loads(cfg.chat_ids_json) if cfg.chat_ids_json else []
        except Exception:
            pass
        return cfg.token, [str(i) for i in ids if i]


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def notify_all(app, text: str) -> list:
    """Envía el mensaje a todos los chat_ids configurados."""
    token, chat_ids = _get_config(app)
    if not token or not chat_ids:
        return []
    return [_send(token, cid, text) for cid in chat_ids]


def send_test(token: str, chat_id: str) -> tuple[bool, str]:
    """Test de conexión. Devuelve (ok, mensaje_detallado)."""
    text = (
        "✅ <b>CineCadiz — Conexión OK</b>\n\n"
        "🤖 El bot está configurado correctamente.\n"
        f"🕐 {_now()}"
    )
    real_chat_id, thread_id = _parse_chat(chat_id)
    payload = {
        "chat_id": real_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if thread_id is not None:
        payload["message_thread_id"] = thread_id
    try:
        r = _requests.post(_TG_API.format(token=token), json=payload, timeout=10)
        if r.ok:
            return True, "Mensaje enviado correctamente."
        try:
            err = r.json().get('description', r.text[:200])
        except Exception:
            err = r.text[:200]
        return False, f"Telegram error {r.status_code}: {err}"
    except Exception as e:
        return False, f"Error de red: {e}"


# ─────────────────────────────────────────────
# Notificaciones concretas
# ─────────────────────────────────────────────

def notify_scan_report(app, checked: int, alive: int, dead: int, purged: int = 0,
                       scan_type: str = "VOD"):
    """Reporte tras un escaneo de links."""
    if checked == 0:
        return
    pct_dead = round(dead / checked * 100, 1)
    emoji = "📡" if scan_type == "live" else "📊"
    lines = [
        f"{emoji} <b>Escaneo {scan_type} completado</b>",
        "",
        f"✅ Verificados: <b>{checked:,}</b>",
        f"🟢 Activos: <b>{alive:,}</b>",
        f"🔴 Caídos: <b>{dead:,}</b> ({pct_dead}%)",
    ]
    if purged:
        lines.append(f"🗑️ Eliminados: <b>{purged:,}</b>")
    lines.append(f"\n🕐 {_now()}")
    notify_all(app, "\n".join(lines))


def notify_server_down(app, servidor: str, dead_pct: float, dead: int, total: int):
    """Alerta: servidor supera el umbral de streams caídos."""
    text = (
        f"🚨 <b>Servidor crítico</b>\n\n"
        f"🖥️ <code>{servidor}</code>\n"
        f"📉 <b>{dead_pct}%</b> streams caídos ({dead:,}/{total:,})\n\n"
        f"⚠️ Revisar o eliminar desde el panel.\n"
        f"🕐 {_now()}"
    )
    notify_all(app, text)


def notify_server_recovered(app, servidor: str, alive: int, total: int):
    """Alerta: servidor vuelve a estar operativo."""
    pct = round(alive / total * 100, 1) if total else 0
    text = (
        f"✅ <b>Servidor recuperado</b>\n\n"
        f"🖥️ <code>{servidor}</code>\n"
        f"📈 <b>{pct}%</b> streams activos ({alive:,}/{total:,})\n\n"
        f"🎉 El servidor vuelve a estar operativo.\n"
        f"🕐 {_now()}"
    )
    notify_all(app, text)


def notify_new_content(app, movies: int, series: int, live: int, lista_nombre: str):
    """Notificación cuando se importa contenido nuevo."""
    total = movies + series + live
    if total == 0:
        return
    lines = [
        f"🆕 <b>Contenido importado</b>",
        f"📋 Lista: <b>{lista_nombre}</b>",
        "",
    ]
    if movies:
        lines.append(f"🎬 Películas: <b>{movies:,}</b>")
    if series:
        lines.append(f"📺 Series: <b>{series:,}</b>")
    if live:
        lines.append(f"📡 Directo: <b>{live:,}</b>")
    lines.append(f"\n🕐 {_now()}")
    notify_all(app, "\n".join(lines))


def notify_import_error(app, lista_nombre: str, error: str):
    """Notificación cuando falla la importación de una lista."""
    text = (
        f"❌ <b>Error de importación</b>\n\n"
        f"📋 Lista: <b>{lista_nombre}</b>\n"
        f"💬 {error[:300]}\n\n"
        f"🕐 {_now()}"
    )
    notify_all(app, text)


def notify_daily_digest(app):
    """Resumen diario de estadísticas."""
    from models import Contenido, User
    with app.app_context():
        total    = Contenido.query.filter_by(fuente='m3u').count()
        activos  = Contenido.query.filter_by(fuente='m3u', activo=True).count()
        caidos   = total - activos
        peliculas = Contenido.query.filter_by(fuente='m3u', tipo='pelicula', activo=True).count()
        series_c  = Contenido.query.filter_by(fuente='m3u', tipo='serie',    activo=True).count()
        live_c    = Contenido.query.filter_by(fuente='m3u', tipo='live',     activo=True).count()
        users     = User.query.filter_by(activo=True).count()
        pct_ok    = round(activos / total * 100, 1) if total else 0

    text = (
        f"📈 <b>Resumen diario — CineCadiz</b>\n"
        f"📅 {_now()}\n\n"
        f"🎬 Películas: <b>{peliculas:,}</b>\n"
        f"📺 Series: <b>{series_c:,}</b>\n"
        f"📡 Directo: <b>{live_c:,}</b>\n\n"
        f"✅ Activos: <b>{activos:,}</b> ({pct_ok}%)\n"
        f"🔴 Caídos: <b>{caidos:,}</b>\n\n"
        f"👥 Usuarios: <b>{users}</b>"
    )
    notify_all(app, text)


# ─────────────────────────────────────────────
# Webhook — gestión y manejo de comandos
# ─────────────────────────────────────────────

def _api(token: str, method: str, payload: dict) -> dict:
    """Llamada genérica a la Bot API."""
    try:
        r = _requests.post(
            _TG_BASE.format(token=token, method=method),
            json=payload,
            timeout=10,
        )
        return r.json()
    except Exception as e:
        logger.error(f"[Telegram] API {method} error: {e}")
        return {'ok': False, 'description': str(e)}


def _send_keyboard(token: str, chat_id: str, text: str, keyboard: dict) -> bool:
    """Envía mensaje con teclado inline."""
    real_chat_id, thread_id = _parse_chat(chat_id)
    payload = {
        "chat_id": real_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": keyboard,
    }
    if thread_id is not None:
        payload["message_thread_id"] = thread_id
    try:
        r = _requests.post(_TG_API.format(token=token), json=payload, timeout=10)
        return r.ok
    except Exception:
        return False


def set_webhook(token: str, webhook_url: str) -> tuple[bool, str]:
    """Registra el webhook en Telegram."""
    try:
        r = _requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
            timeout=10,
        )
        data = r.json()
        if data.get('ok'):
            return True, data.get('description', 'Webhook registrado.')
        return False, data.get('description', 'Error desconocido.')
    except Exception as e:
        return False, f"Error de red: {e}"


def delete_webhook(token: str) -> tuple[bool, str]:
    """Elimina el webhook de Telegram."""
    try:
        r = _requests.post(
            f"https://api.telegram.org/bot{token}/deleteWebhook",
            timeout=10,
        )
        data = r.json()
        if data.get('ok'):
            return True, 'Webhook eliminado correctamente.'
        return False, data.get('description', 'Error al eliminar webhook.')
    except Exception as e:
        return False, f"Error de red: {e}"


def get_webhook_info(token: str) -> dict:
    """Consulta el estado actual del webhook en Telegram."""
    try:
        r = _requests.get(
            f"https://api.telegram.org/bot{token}/getWebhookInfo",
            timeout=10,
        )
        data = r.json()
        return data.get('result', {}) if data.get('ok') else {}
    except Exception:
        return {}


# ── Manejadores de comandos ─────────────────────────────────

def _cmd_ayuda(token: str, chat_id: str):
    text = (
        "🤖 <b>CineCadiz Bot</b>\n\n"
        "Comandos disponibles:\n\n"
        "/estado — Estado general del sistema\n"
        "/servidores — Salud de los servidores\n"
        "/stats — Estadísticas de contenido\n"
        "/usuarios — Info de usuarios\n"
        "/backup — Crear y enviar backup\n"
        "/ayuda — Esta ayuda\n\n"
        f"🕐 {_now()}"
    )
    _send(token, chat_id, text)


def _cmd_estado(app, token: str, chat_id: str):
    from models import Contenido, User
    with app.app_context():
        total   = Contenido.query.filter_by(fuente='m3u').count()
        activos = Contenido.query.filter_by(fuente='m3u', activo=True).count()
        caidos  = total - activos
        users   = User.query.filter_by(activo=True).count()
        pct     = round(activos / total * 100, 1) if total else 0

    status = "🟢" if pct >= 80 else ("🟡" if pct >= 50 else "🔴")
    text = (
        f"{status} <b>Estado CineCadiz</b>\n"
        f"📅 {_now()}\n\n"
        f"📦 Contenido total: <b>{total:,}</b>\n"
        f"✅ Activos: <b>{activos:,}</b> ({pct}%)\n"
        f"🔴 Caídos: <b>{caidos:,}</b>\n\n"
        f"👥 Usuarios activos: <b>{users}</b>"
    )
    keyboard = {"inline_keyboard": [[
        {"text": "📊 Stats", "callback_data": "cmd_stats"},
        {"text": "🖥️ Servidores", "callback_data": "cmd_servidores"},
    ]]}
    _send_keyboard(token, chat_id, text, keyboard)


def _cmd_servidores(app, token: str, chat_id: str):
    from link_checker import server_health
    with app.app_context():
        servers = server_health(app)[:15]

    if not servers:
        _send(token, chat_id, "ℹ️ No hay datos de servidores disponibles.")
        return

    lines = [f"🖥️ <b>Estado de servidores</b>", f"📅 {_now()}", ""]
    for s in servers:
        pct = s['dead_pct']
        e = "🔴" if pct >= 80 else ("🟡" if pct >= 50 else "🟢")
        ok_pct = round(100 - pct, 0)
        lines.append(f"{e} <code>{s['servidor'][:28]}</code>")
        lines.append(f"   ✅{s['alive']:,} 🔴{s['dead']:,} ({ok_pct:.0f}% OK)")

    keyboard = {"inline_keyboard": [[
        {"text": "🔄 Actualizar", "callback_data": "cmd_servidores"},
    ]]}
    _send_keyboard(token, chat_id, "\n".join(lines), keyboard)


def _cmd_stats(app, token: str, chat_id: str):
    from models import Contenido
    with app.app_context():
        total     = Contenido.query.filter_by(fuente='m3u').count()
        activos   = Contenido.query.filter_by(fuente='m3u', activo=True).count()
        peliculas = Contenido.query.filter_by(fuente='m3u', tipo='pelicula', activo=True).count()
        series    = Contenido.query.filter_by(fuente='m3u', tipo='serie',    activo=True).count()
        live      = Contenido.query.filter_by(fuente='m3u', tipo='live',     activo=True).count()
        pct       = round(activos / total * 100, 1) if total else 0

    text = (
        f"📊 <b>Estadísticas CineCadiz</b>\n"
        f"📅 {_now()}\n\n"
        f"🎬 Películas: <b>{peliculas:,}</b>\n"
        f"📺 Series: <b>{series:,}</b>\n"
        f"📡 Directo: <b>{live:,}</b>\n\n"
        f"✅ Activos: <b>{activos:,}</b> ({pct}%)\n"
        f"📦 Total: <b>{total:,}</b>"
    )
    _send(token, chat_id, text)


def _cmd_usuarios(app, token: str, chat_id: str):
    from models import User, IptvUser
    with app.app_context():
        total_web   = User.query.filter_by(activo=True).count()
        superadmins = User.query.filter_by(role='superadmin', activo=True).count()
        premiums    = User.query.filter_by(role='premium',    activo=True).count()
        regular     = User.query.filter_by(role='user',       activo=True).count()
        iptv_active = IptvUser.query.filter_by(activo=True).count()
        iptv_total  = IptvUser.query.count()

    text = (
        f"👥 <b>Usuarios CineCadiz</b>\n"
        f"📅 {_now()}\n\n"
        f"🌐 <b>Web:</b> {total_web}\n"
        f"  👑 Superadmin: {superadmins}\n"
        f"  ⭐ Premium: {premiums}\n"
        f"  👤 Usuario: {regular}\n\n"
        f"📺 <b>IPTV:</b> {iptv_active} activos / {iptv_total} total"
    )
    _send(token, chat_id, text)


def _cmd_backup(app, token: str, chat_id: str):
    _send(token, chat_id, "⏳ Creando backup, espera...")
    try:
        from backup import create_backup, send_backup_telegram
        path = create_backup(app)
        ok, msg = send_backup_telegram(app, path)
        status = "✅ Backup creado y enviado" if ok else f"⚠️ Creado, error al enviar: {msg}"
        _send(token, chat_id, f"{status}\n📦 {path.name}")
    except Exception as e:
        _send(token, chat_id, f"❌ Error en backup: {e}")


def _handle_callback(app, token: str, callback: dict):
    """Responde a botones inline."""
    cb_id   = callback['id']
    data    = callback.get('data', '')
    chat_id = str(callback['message']['chat']['id'])

    # Confirmar recepción del callback a Telegram
    try:
        _requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": cb_id},
            timeout=5,
        )
    except Exception:
        pass

    if data == 'cmd_estado':
        _cmd_estado(app, token, chat_id)
    elif data == 'cmd_servidores':
        _cmd_servidores(app, token, chat_id)
    elif data == 'cmd_stats':
        _cmd_stats(app, token, chat_id)


def handle_webhook_update(app, update: dict):
    """
    Procesa una actualización entrante del webhook de Telegram.
    Llama a los handlers de comando o callback_query según corresponda.
    """
    from models import TelegramConfig
    with app.app_context():
        cfg = TelegramConfig.query.first()
        if not cfg or not cfg.enabled or not cfg.token:
            return
        token = cfg.token

    message  = update.get('message') or update.get('edited_message')
    callback = update.get('callback_query')

    if callback:
        _handle_callback(app, token, callback)
        return

    if not message:
        return

    chat_id = str(message['chat']['id'])
    text    = message.get('text', '')

    if not text.startswith('/'):
        return

    # Soportar /cmd@botname
    cmd = text.split('@')[0].split()[0].lower()

    if cmd in ('/start', '/ayuda', '/help'):
        _cmd_ayuda(token, chat_id)
    elif cmd == '/estado':
        _cmd_estado(app, token, chat_id)
    elif cmd == '/servidores':
        _cmd_servidores(app, token, chat_id)
    elif cmd == '/stats':
        _cmd_stats(app, token, chat_id)
    elif cmd == '/usuarios':
        _cmd_usuarios(app, token, chat_id)
    elif cmd == '/backup':
        _cmd_backup(app, token, chat_id)


def check_and_notify_server_health(app):
    """
    Compara la salud actual de servidores con el snapshot previo.
    Dispara alertas cuando un servidor cae o se recupera.
    """
    from models import db, ServerHealthSnapshot, TelegramConfig
    from link_checker import server_health

    with app.app_context():
        cfg = TelegramConfig.query.first()
        if not cfg or not cfg.enabled:
            return

        threshold = cfg.alert_threshold or 80
        current = {s['servidor']: s for s in server_health(app)}

        for servidor, data in current.items():
            snap = ServerHealthSnapshot.query.filter_by(servidor=servidor).first()
            dead_pct = data['dead_pct']

            if snap is None:
                snap = ServerHealthSnapshot(
                    servidor=servidor,
                    dead_pct=dead_pct,
                    alerted=dead_pct >= threshold,
                )
                db.session.add(snap)
            else:
                prev_alerted = snap.alerted
                now_critical = dead_pct >= threshold

                if now_critical and not prev_alerted:
                    # Servidor acaba de cruzar el umbral → alerta de caída
                    notify_server_down(app, servidor, dead_pct, data['dead'], data['total'])
                    snap.alerted = True

                elif not now_critical and prev_alerted:
                    # Servidor se ha recuperado
                    notify_server_recovered(app, servidor, data['alive'], data['total'])
                    snap.alerted = False

                snap.dead_pct = dead_pct
                snap.updated_at = datetime.utcnow()

        db.session.commit()
