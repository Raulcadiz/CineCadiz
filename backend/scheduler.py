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
        logger.info(f'[Scheduler] Scan automático VOD: {result}')

    def job_purge():
        from link_checker import purge_dead_links
        days = app.config.get('PURGE_DEAD_DAYS', 7)
        result = purge_dead_links(app, days=days)
        logger.info(f'[Scheduler] Purge automático: {result}')

    def job_live_scan():
        """
        Escanea canales en directo según la configuración almacenada en BD.
        Este job corre cada hora y decide si ejecutar el scan real según
        el intervalo configurado (24h / 48h / 72h) y la fecha del último scan.
        """
        from datetime import datetime, timedelta
        from models import LiveScanConfig
        from link_checker import scan_live_channels

        with app.app_context():
            config = LiveScanConfig.query.first()
            if config is None:
                # Crear config por defecto si no existe
                config = LiveScanConfig(auto_scan_enabled=True, interval_hours=24)
                from models import db
                db.session.add(config)
                db.session.commit()

            if not config.auto_scan_enabled:
                return

            # Comprobar si ha pasado suficiente tiempo desde el último scan
            if config.last_scan is not None:
                elapsed = datetime.utcnow() - config.last_scan
                if elapsed < timedelta(hours=config.interval_hours):
                    return   # Aún no toca

        result = scan_live_channels(app)
        logger.info(f'[Scheduler] Scan live: {result}')

    hours = app.config.get('SCAN_INTERVAL_HOURS', 24)

    _scheduler.add_job(
        func=job_scan,
        trigger=IntervalTrigger(hours=hours),
        id='auto_scan',
        name='Escaneo automático de links VOD',
        replace_existing=True,
    )

    # Live scan: job que corre cada hora y decide internamente si lanzar el scan real
    _scheduler.add_job(
        func=job_live_scan,
        trigger=IntervalTrigger(hours=1),
        id='auto_live_scan',
        name='Escaneo automático de canales en directo',
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
        logger.info(f'[Scheduler] Iniciado — scan VOD cada {hours}h, live cada 1h (con control interno), purge semanal')

    return _scheduler


def reschedule_live_scan():
    """
    Llamar tras cambiar LiveScanConfig para que el próximo ciclo se alinee.
    En la implementación actual el job de 1h ya lee la config desde BD,
    por lo que no es necesario reprogramar — se deja como hook para el futuro.
    """
    pass


def get_scheduler():
    return _scheduler
