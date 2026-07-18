from celery import Celery

from fincore.core.config import get_settings

settings = get_settings()
celery_app = Celery("fincore", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    beat_schedule={
        "wallet-reconciliation-hourly": {
            "task": "fincore.reconcile_wallets",
            "schedule": 3600.0,
        },
        "outbox-dispatch-every-10-seconds": {
            "task": "fincore.dispatch_outbox",
            "schedule": 10.0,
        },
        "expire-idempotency-daily": {
            "task": "fincore.cleanup_idempotency",
            "schedule": 86400.0,
        },
    },
)
celery_app.autodiscover_tasks(["fincore.worker"])
