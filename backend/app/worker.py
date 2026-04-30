"""
RQ Worker for LIDAR Processing.

This module runs as a separate process to handle heavy LiDAR processing jobs.
It connects to Redis and processes jobs from the 'lidar-processing' queue.

Usage:
    # Run worker
    python -m app.worker

    # Or via rq command
    rq worker lidar-processing --url redis://redis:6379/0
"""

import logging
import sys
from typing import Optional, Tuple

from redis import Redis
from rq import Connection, Queue, Worker
from rq.job import Job
from rq.registry import FailedJobRegistry

from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def _extract_job_context(job: Job) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract Orion job entity id and tenant from RQ Job metadata/args.

    Priority:
    1) job.meta values set at enqueue time
    2) positional args fallback
    """
    job_entity_id = None
    tenant_id = None

    if isinstance(job.meta, dict):
        job_entity_id = job.meta.get("job_entity_id")
        tenant_id = job.meta.get("tenant_id")

    # Fallback to positional args used by process_lidar_job/process_uploaded_file
    if not job_entity_id and job.args:
        first = job.args[0]
        if isinstance(first, str) and first.startswith("urn:ngsi-ld:DataProcessingJob:"):
            job_entity_id = first
    if not tenant_id and len(job.args) > 1:
        second = job.args[1]
        if isinstance(second, str):
            tenant_id = second

    return job_entity_id, tenant_id


def _mark_orion_job_failed(job_entity_id: str, tenant_id: str, error_message: str) -> None:
    """
    Mark Orion DataProcessingJob as failed with terminal metadata.
    """
    from datetime import datetime
    from app.services.orion_client import get_orion_client

    client = get_orion_client(tenant_id)
    updates = {
        "status": "failed",
        "progress": 100,
        "statusMessage": "Worker failure",
        "errorMessage": error_message[:4000],  # avoid huge payloads
        "completedAt": datetime.utcnow().isoformat() + "Z",
    }
    client.update_job_sync(job_entity_id, **updates)


def _sync_orion_failure(job: Job, reason: str) -> None:
    """
    Best-effort synchronization from RQ failure state -> Orion failed state.
    """
    job_entity_id, tenant_id = _extract_job_context(job)
    if not job_entity_id or not tenant_id:
        logger.warning(
            "Cannot sync Orion failure: missing context for RQ job %s (entity=%s tenant=%s)",
            job.id,
            job_entity_id,
            tenant_id,
        )
        return

    try:
        _mark_orion_job_failed(job_entity_id, tenant_id, reason)
        logger.info(
            "Synced Orion failure for RQ job %s -> %s (tenant=%s)",
            job.id,
            job_entity_id,
            tenant_id,
        )
    except Exception:
        logger.exception(
            "Failed to sync Orion failure for RQ job %s (%s)", job.id, reason
        )


def _rq_exception_handler(job: Job, exc_type, exc_value, traceback) -> bool:
    """
    RQ exception handler for Python exceptions raised inside jobs.
    Return True to continue with default failure handling.
    """
    reason = f"{exc_type.__name__}: {exc_value}"
    _sync_orion_failure(job, reason)
    return True


def _work_horse_killed_handler(job: Job, retpid: int, ret_val: int, rusage) -> None:
    """
    Handle work-horse hard terminations (e.g. SIGKILL/OOM).
    """
    reason = (
        "Work-horse terminated unexpectedly "
        f"(retpid={retpid}, ret_val={ret_val}, rusage={rusage})"
    )
    _sync_orion_failure(job, reason)


def reconcile_failed_jobs(redis_conn: Redis, queue_name: str) -> None:
    """
    On worker startup, reconcile already-failed RQ jobs with Orion.
    Prevents stale Orion jobs stuck in 'processing' after abrupt terminations.
    """
    failed_registry = FailedJobRegistry(name=queue_name, connection=redis_conn)
    failed_job_ids = failed_registry.get_job_ids()
    if not failed_job_ids:
        logger.info("No failed jobs pending reconciliation in queue '%s'", queue_name)
        return

    logger.info(
        "Reconciling %d failed jobs from queue '%s'", len(failed_job_ids), queue_name
    )
    for job_id in failed_job_ids:
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            reason = (job.exc_info or "RQ failed job (no exc_info)")[:4000]
            _sync_orion_failure(job, reason)
        except Exception:
            logger.exception("Failed to reconcile RQ job %s", job_id)


def create_redis_connection() -> Redis:
    """Create Redis connection from settings."""
    return Redis.from_url(settings.REDIS_URL)


def run_worker():
    """Start the RQ worker."""
    logger.info("Starting LIDAR processing worker...")
    logger.info(f"Redis URL: {settings.REDIS_URL}")
    logger.info(f"Queue: {settings.WORKER_QUEUE_NAME}")

    redis_conn = create_redis_connection()
    reconcile_failed_jobs(redis_conn, settings.WORKER_QUEUE_NAME)

    with Connection(redis_conn):
        queues = [Queue(settings.WORKER_QUEUE_NAME)]

        worker = Worker(
            queues,
            name=f"lidar-worker-{settings.WORKER_QUEUE_NAME}",
            default_worker_ttl=settings.WORKER_TIMEOUT,
            exception_handlers=[_rq_exception_handler],
            work_horse_killed_handler=_work_horse_killed_handler,
        )

        logger.info("Worker ready. Waiting for jobs...")
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    run_worker()
