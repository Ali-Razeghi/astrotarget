import logging
import os
from contextlib import asynccontextmanager
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import __version__, db, persist
from .export.plot import lightcurve_png
from .export.report import build_pdf_report
from .export.tabular import to_csv_bytes, to_fits_bytes, to_json_bytes
from .nasa import normalize_name
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
API_KEY = os.environ.get('ASTROTARGET_API_KEY', '').strip()
RATE_LIMIT = int(os.environ.get('RATE_LIMIT_PER_MINUTE', '10'))
_STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'public'))
logger = logging.getLogger(__name__)

class TargetRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128, examples=['WASP-12 b'])

async def optional_api_key(x_api_key: str | None=Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, 'invalid or missing X-API-Key')

async def rate_limit(request: Request):
    host = request.client.host if request.client else 'unknown'
    key = f'rate:{host}'
    n = await request.app.state.redis.incr(key)
    if n == 1:
        await request.app.state.redis.expire(key, 60)
    if n > RATE_LIMIT:
        raise HTTPException(429, 'rate limit exceeded; try again in a minute')

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
    await db.ping()
    yield
    await app.state.redis.close()
    await db.engine.dispose()
app = FastAPI(title='AstroTarget', version=__version__, lifespan=lifespan, description='Research-oriented exoplanet target intelligence using NASA Exoplanet Archive, Gaia DR3 and TESS/MAST.')
if os.path.isdir(_STATIC_DIR):
    app.mount('/ui', StaticFiles(directory=_STATIC_DIR, html=True), name='ui')

@app.get('/health')
async def health(request: Request):
    checks = {'postgres': False, 'redis': False}
    try:
        await db.ping()
        checks['postgres'] = True
    except Exception:
        logger.warning('PostgreSQL health check failed', exc_info=True)
    try:
        checks['redis'] = bool(await request.app.state.redis.ping())
    except Exception:
        logger.warning('Redis health check failed', exc_info=True)
    ok = all(checks.values())
    return {'status': 'ok' if ok else 'degraded', 'version': __version__, 'dependencies': checks}

@app.post('/targets', dependencies=[Depends(optional_api_key), Depends(rate_limit)])
async def submit_target(payload: TargetRequest, request: Request):
    name = normalize_name(payload.name)
    async with db.Session() as s:
        job = db.Job(target_name=name)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        queued = await request.app.state.redis.enqueue_job('analyze_target', job.id, name)
        if queued is None:
            job.status = 'error'
            job.error_message = 'Could not enqueue Redis job'
            await s.commit()
            raise HTTPException(503, 'job queue unavailable')
        return {'job_id': job.id, 'status': job.status, 'target': name}

@app.get('/jobs/{job_id}')
async def job_status(job_id: int):
    async with db.Session() as s:
        job = await db.get_job(s, job_id)
        if job is None:
            raise HTTPException(404, 'job not found')
        out = {'job_id': job.id, 'status': job.status, 'target': job.target_name, 'created_at': job.created_at, 'updated_at': job.updated_at}
        if job.run_id:
            out['run_id'] = job.run_id
        if job.error_message:
            out['error'] = job.error_message
        return out

@app.get('/targets/{name}')
async def get_target(name: str):
    async with db.Session() as s:
        run = await db.latest_run_for_planet_name(s, normalize_name(name))
        if run is None:
            raise HTTPException(404, f"No stored analysis for '{name}' yet. POST /targets first.")
        return {'run_id': run.id, 'created_at': run.created_at, **run.result_json}

async def _load_run_and_arrays(s, run_id: int):
    run = await db.get_run(s, run_id)
    if run is None:
        raise HTTPException(404, 'run not found')
    arrays = None
    if run.light_curve_id:
        lc = await db.get_light_curve(s, run.light_curve_id)
        if lc:
            arrays = persist.unpack_npz(lc.npz_blob)
    return (run, arrays)

@app.get('/runs/{run_id}')
async def get_run(run_id: int):
    async with db.Session() as s:
        run, _ = await _load_run_and_arrays(s, run_id)
        return {'run_id': run.id, 'created_at': run.created_at, **run.result_json}

@app.get('/runs/{run_id}/export.csv')
async def export_csv(run_id: int):
    async with db.Session() as s:
        run, a = await _load_run_and_arrays(s, run_id)
        if not a:
            raise HTTPException(404, 'no light curve stored for this run')
        return Response(to_csv_bytes(a['time'], a['flux'], a['flux_err']), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="run_{run_id}.csv"'})

@app.get('/runs/{run_id}/export.fits')
async def export_fits(run_id: int):
    async with db.Session() as s:
        run, a = await _load_run_and_arrays(s, run_id)
        if not a:
            raise HTTPException(404, 'no light curve stored for this run')
        meta = {'target': run.result_json.get('target'), 'pipeline_v': run.pipeline_version, 'period_d': run.recovered_period_d, 'depth': run.depth_frac}
        return Response(to_fits_bytes(a['time'], a['flux'], a['flux_err'], meta), media_type='application/fits', headers={'Content-Disposition': f'attachment; filename="run_{run_id}.fits"'})

@app.get('/runs/{run_id}/export.json')
async def export_json(run_id: int):
    async with db.Session() as s:
        run, _ = await _load_run_and_arrays(s, run_id)
        return Response(to_json_bytes({'run_id': run.id, **run.result_json}), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="run_{run_id}.json"'})

@app.get('/runs/{run_id}/plot.png')
async def export_plot(run_id: int):
    async with db.Session() as s:
        run, a = await _load_run_and_arrays(s, run_id)
        if not a:
            raise HTTPException(404, 'no light curve stored for this run')
        fit = (run.result_json.get('tess') or {}).get('analysis', {})
        png = lightcurve_png(a['time'], a['flux'], run.result_json.get('target', 'target'), period=fit.get('recovered_period_d'), t0=fit.get('t0_btjd'), duration=fit.get('duration_d'))
        return Response(png, media_type='image/png')

@app.get('/runs/{run_id}/report.pdf')
async def export_report(run_id: int):
    async with db.Session() as s:
        run, a = await _load_run_and_arrays(s, run_id)
        png = None
        if a:
            fit = (run.result_json.get('tess') or {}).get('analysis', {})
            png = lightcurve_png(a['time'], a['flux'], run.result_json.get('target', 'target'), period=fit.get('recovered_period_d'), t0=fit.get('t0_btjd'), duration=fit.get('duration_d'))
        return Response(build_pdf_report(run.result_json, png), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="run_{run_id}_report.pdf"'})
