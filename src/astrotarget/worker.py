import logging
import os

from arq.connections import RedisSettings

from . import __version__, db, persist, pipeline

logger = logging.getLogger(__name__)
# ARQ configures its own logging; explicitly enable AstroTarget INFO records so
# pipeline stage timings are visible in worker container logs.
logging.getLogger("astrotarget").setLevel(logging.INFO)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


async def analyze_target(ctx, job_row_id: int, target_name: str):
    async with db.Session() as session:
        job = await db.get_job(session, job_row_id)
        if job is None:
            return
        job.status = "running"
        await session.commit()
        try:
            logger.info("job=%s target=%s pipeline started", job_row_id, target_name)
            result = await pipeline.run(target_name)
            run = await persist.persist_pipeline_result(session, result, __version__)
            job.status = "done"
            job.run_id = run.id
            job.error_message = None
            logger.info("job=%s target=%s pipeline completed run_id=%s", job_row_id, target_name, run.id)
        except LookupError:
            job.status = "error"
            job.error_message = f"'{target_name}' not found in NASA Exoplanet Archive"
        except Exception as exc:
            logger.exception("job=%s target=%s pipeline failed", job_row_id, target_name)
            job.status = "error"
            job.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        await session.commit()


async def startup(ctx):
    await db.ping()


class WorkerSettings:
    functions = [analyze_target]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    # A normal quick-mode run should finish far below this. Keep a hard ceiling so a
    # pathological CPU-bound analysis cannot occupy the worker indefinitely.
    job_timeout = int(os.environ.get("WORKER_JOB_TIMEOUT_SECONDS", "900"))
    # Do not automatically repeat a long scientific computation after timeout/failure.
    max_tries = 1
