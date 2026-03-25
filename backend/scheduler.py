"""
Scheduler de tareas en background (APScheduler).
Se usa para escanear links caídos periódicamente.
"""
import logging
import time as _time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)
_scheduler = BackgroundScheduler(timezone='Europe/Madrid')


def init_scheduler(app):
    """Inicializa y arranca el scheduler con la app Flask."""

    def job_scan():
        """
        Escanea todos los canales VOD en lotes sucesivos hasta cubrir la BD entera.
        Con 80k canales y 40 workers puede tardar varias horas — se ejecuta en
        segundo plano sin bloquear el servidor web.
        """
        from link_checker import scan_dead_links
        from telegram_bot import notify_scan_report, check_and_notify_server_health

        batch   = app.config.get('SCAN_BATCH_SIZE', 5000)
        workers = app.config.get('SCAN_MAX_WORKERS', 40)

        total_checked = total_alive = total_dead = 0
        iteration = 0
        max_iter  = 200

        while iteration < max_iter:
            iteration += 1
            result = scan_dead_links(app, batch_size=batch, max_workers=workers)
            total_checked += result.get('checked', 0)
            total_alive   += result.get('alive',   0)
            total_dead    += result.get('dead',     0)

            logger.info(
                f'[Scheduler] Scan VOD iter {iteration}: '
                f'{result.get("checked")} verificados, '
                f'total acumulado={total_checked}'
            )

            if not result.get('has_more', False):
                break

            _time.sleep(2)

        logger.info(
            f'[Scheduler] Scan VOD completo: {total_checked} verificados, '
            f'{total_alive} vivos, {total_dead} caídos en {iteration} lote(s)'
        )
        # Notificar resumen por Telegram
        try:
            notify_scan_report(app, total_checked, total_alive, total_dead, scan_type='VOD')
            check_and_notify_server_health(app)
        except Exception as e:
            logger.warning(f'[Scheduler] Error notificación Telegram post-scan: {e}')

    def job_purge():
        from link_checker import purge_dead_links
        days   = app.config.get('PURGE_DEAD_DAYS', 7)
        result = purge_dead_links(app, days=days)
        logger.info(f'[Scheduler] Purge automático: {result}')

    def job_live_scan():
        """
        Escanea canales en directo según la configuración almacenada en BD.
        Corre cada hora y decide si lanzar el scan real según el intervalo
        configurado (24 / 48 / 72 h) y la fecha del último scan.
        """
        from datetime import datetime, timedelta
        from models import LiveScanConfig
        from link_checker import scan_live_channels
        from telegram_bot import notify_scan_report

        with app.app_context():
            config = LiveScanConfig.query.first()
            if config is None:
                config = LiveScanConfig(auto_scan_enabled=True, interval_hours=24)
                from models import db
                db.session.add(config)
                db.session.commit()

            if not config.auto_scan_enabled:
                return

            if config.last_scan is not None:
                elapsed = datetime.utcnow() - config.last_scan
                if elapsed < timedelta(hours=config.interval_hours):
                    return

        result = scan_live_channels(app)
        logger.info(f'[Scheduler] Scan live: {result}')
        try:
            alive = result.get('alive', 0)
            dead  = result.get('dead',  0)
            notify_scan_report(app, alive + dead, alive, dead, scan_type='Live')
        except Exception as e:
            logger.warning(f'[Scheduler] Error notificación Telegram post-live-scan: {e}')

    def job_daily_digest():
        """Resumen diario enviado a Telegram a la hora configurada."""
        from datetime import datetime
        from models import TelegramConfig
        from telegram_bot import notify_daily_digest

        with app.app_context():
            cfg = TelegramConfig.query.first()
            if not cfg or not cfg.enabled or not cfg.daily_digest:
                return
            current_hour = datetime.utcnow().hour
            if current_hour != (cfg.digest_hour or 8):
                return

        try:
            notify_daily_digest(app)
        except Exception as e:
            logger.warning(f'[Scheduler] Error digest diario Telegram: {e}')

    hours = app.config.get('SCAN_INTERVAL_HOURS', 24)

    _scheduler.add_job(
        func=job_scan,
        trigger=IntervalTrigger(hours=hours),
        id='auto_scan',
        name='Escaneo automático de links VOD',
        replace_existing=True,
    )

    _scheduler.add_job(
        func=job_live_scan,
        trigger=IntervalTrigger(hours=1),
        id='auto_live_scan',
        name='Escaneo automático de canales en directo',
        replace_existing=True,
    )

    _scheduler.add_job(
        func=job_purge,
        trigger=IntervalTrigger(weeks=1),
        id='auto_purge',
        name='Purge semanal de streams caídos',
        replace_existing=True,
    )

    _scheduler.add_job(
        func=job_daily_digest,
        trigger=IntervalTrigger(hours=1),
        id='daily_digest',
        name='Digest diario Telegram',
        replace_existing=True,
    )

    if not _scheduler.running:
        _scheduler.start()
        logger.info(
            f'[Scheduler] Iniciado — scan VOD cada {hours}h (lotes completos), '
            f'live cada 1h (control interno), purge semanal'
        )

    return _scheduler


def get_scheduler():
    return _scheduler
