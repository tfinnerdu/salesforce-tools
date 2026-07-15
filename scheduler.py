"""APScheduler setup for background jobs."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _daily_readiness_run(app) -> None:
    with app.app_context():
        try:
            from services import readiness_validator
            from config import Config
            result = readiness_validator.run_full_readiness_check(Config.DEFAULT_ORG)
            readiness_validator.save_run(Config.DEFAULT_ORG, result)
            logger.info('"Daily readiness run complete","overall_pct":%s', result.get('overall_pct'))
        except Exception:
            logger.exception('"Daily readiness run failed"')


def _nightly_backup_run(app) -> None:
    with app.app_context():
        try:
            from services import data_backup
            from config import Config
            result = data_backup.run_backup(Config.DEFAULT_ORG, trigger='scheduled')
            logger.info('"Nightly backup complete","run_id":%s,"records":%s',
                        result.get('run_id'), result.get('total_records'))
        except Exception:
            logger.exception('"Nightly backup failed"')


def init_scheduler(app) -> None:
    global _scheduler
    from config import Config
    _scheduler = BackgroundScheduler(timezone=Config.SCHEDULER_TIMEZONE)
    _scheduler.add_job(
        _daily_readiness_run,
        trigger='cron',
        hour=6,
        minute=0,
        args=[app],
        id='daily_readiness',
        replace_existing=True,
    )
    if Config.BACKUP_ENABLED:
        _scheduler.add_job(
            _nightly_backup_run,
            trigger='cron',
            hour=2,
            minute=0,
            args=[app],
            id='nightly_backup',
            replace_existing=True,
        )
        logger.info('"Nightly backup job registered at 02:00 CT"')
    _scheduler.start()
    logger.info('"APScheduler started, daily readiness job registered at 06:00 CT"')


def shutdown_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
