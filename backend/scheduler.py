"""
Scheduler de tareas en background (APScheduler).
Se usa para escanear links caídos periódicamente.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)
_scheduler = BackgroundScheduler(timezone='Europe/Madrid')


def init_scheduler(app):
    """Inicializa y arranca el scheduler con la app Flask."""

    def job_scan():
        from link_checker import scan_dead_links
        batch = app.config.get('SCAN_BATCH_SIZE', 100)
        result = scan_dead_links(app, batch_size=batch)
        logger.info(f'[Scheduler] Scan automático: {result}')

    def job_purge():
        from link_checker import purge_dead_links
        days = app.config.get('PURGE_DEAD_DAYS', 7)
        result = purge_dead_links(app, days=days)
        logger.info(f'[Scheduler] Purge automático: {result}')

    hours = app.config.get('SCAN_INTERVAL_HOURS', 24)

    _scheduler.add_job(
        func=job_scan,
        trigger=IntervalTrigger(hours=hours),
        id='auto_scan',
        name='Escaneo automático de links',
        replace_existing=True,
    )

    # Purge semanal: elimina streams muertos > PURGE_DEAD_DAYS días (default 7)
    _scheduler.add_job(
        func=job_purge,
        trigger=IntervalTrigger(weeks=1),
        id='auto_purge',
        name='Purge semanal de streams caídos',
        replace_existing=True,
    )

    if not _scheduler.running:
        _scheduler.start()
        logger.info(f'[Scheduler] Iniciado — scan cada {hours}h, purge semanal')

    return _scheduler


def get_scheduler():
    return _scheduler
