import logging

from apscheduler.schedulers.background import BackgroundScheduler

from . import settings_store
from .services.runner import cleanup_old_analyses, run_auto_jobs


logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
JOB_ID = "daily_auto_run"
RETENTION_JOB_ID = "daily_retention"


def _current_schedule() -> tuple[int, int]:
    cfg = settings_store.get_all()
    return int(cfg["auto_run_hour"]), int(cfg["auto_run_minute"])


def _run_retention() -> None:
    cfg = settings_store.get_all()
    try:
        cleanup_old_analyses(int(cfg.get("retention_days") or 0))
    except Exception:
        logger.exception("retention cleanup failed")


def _auto_then_retention() -> None:
    try:
        run_auto_jobs()
    finally:
        _run_retention()


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    h, m = _current_schedule()
    scheduler.add_job(
        _auto_then_retention,
        trigger="cron",
        hour=h,
        minute=m,
        id=JOB_ID,
        replace_existing=True,
    )
    scheduler.add_job(
        _run_retention,
        trigger="cron",
        hour=3,
        minute=30,
        id=RETENTION_JOB_ID,
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("scheduler started: daily at %02d:%02d (retention 03:30)", h, m)
    return scheduler


def reschedule() -> tuple[int, int]:
    if _scheduler is None:
        return _current_schedule()
    h, m = _current_schedule()
    _scheduler.reschedule_job(JOB_ID, trigger="cron", hour=h, minute=m)
    logger.info("scheduler rescheduled: daily at %02d:%02d", h, m)
    return h, m


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
