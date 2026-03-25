"""
Notificaciones Telegram para CineCadiz.
Envía alertas al canal/grupo configurado en el panel de administración.
"""
import logging
from datetime import datetime

import requests as _requests

logger = logging.getLogger(__name__)
_TG_API = "https://api.telegram.org/bot{token}/sendMessage"


# ─────────────────────────────────────────────
# Primitiva de envío
# ─────────────────────────────────────────────

def _send(token: str, chat_id: str, text: str) -> bool:
    """Envía un mensaje. Devuelve True si fue exitoso."""
    if not token or not chat_id or not text:
        return False
    try:
        r = _requests.post(
            _TG_API.format(token=token),
            json={
                "chat_id": str(chat_id),
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
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
    """Test de conexión. Devuelve (ok, mensaje)."""
    text = (
        "✅ <b>CineCadiz — Conexión OK</b>\n\n"
        "🤖 El bot está configurado correctamente.\n"
        f"🕐 {_now()}"
    )
    ok = _send(token, chat_id, text)
    return ok, "Mensaje enviado correctamente." if ok else "Error al enviar. Revisa token y chat_id."


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
