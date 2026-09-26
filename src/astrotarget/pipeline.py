import asyncio
import logging
import os
import platform
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from time import perf_counter

import httpx

from . import __version__, analysis, gaia, nasa, tess

logger = logging.getLogger(__name__)


def _v(pkg):
    try:
        return version(pkg)
    except PackageNotFoundError:
        return None


def _elapsed(start):
    return round(perf_counter() - start, 3)


async def run(name: str) -> dict:
    run_started = perf_counter()
    now = datetime.now(UTC).isoformat()
    prov = lambda source: {"source": source, "retrieved_utc": now}
    timings = {}
    timeout = httpx.Timeout(90.0, connect=20.0)
    max_sectors = int(os.environ.get("TESS_MAX_SECTORS", "2"))
    max_points = int(os.environ.get("ANALYSIS_MAX_POINTS", "30000"))
    period_window_pct = float(os.environ.get("CATALOG_PERIOD_WINDOW_PCT", "2.0"))

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": f"AstroTarget/{__version__} research-software"},
    ) as client:
        started = perf_counter()
        logger.info("stage=nasa target=%s started", name)
        planet = await nasa.fetch_planet(client, name)
        timings["nasa_s"] = _elapsed(started)
        logger.info("stage=nasa target=%s completed seconds=%.3f", name, timings["nasa_s"])
        if planet is None:
            raise LookupError(name)

        dr2_id = nasa.extract_gaia_id(planet.get("gaia_dr2_id"))
        dr3_id = nasa.extract_gaia_id(planet.get("gaia_dr3_id"))
        t0_btjd = nasa.transit_midpoint_btjd(planet.get("pl_tranmid"))

        async def timed_gaia():
            started = perf_counter()
            logger.info("stage=gaia target=%s started", name)
            try:
                return await gaia.crossmatch(
                    client,
                    planet["ra"],
                    planet["dec"],
                    planet.get("sy_gaiamag"),
                    dr3_id=dr3_id,
                    dr2_id=dr2_id,
                )
            finally:
                timings["gaia_s"] = _elapsed(started)
                logger.info("stage=gaia target=%s finished seconds=%.3f", name, timings["gaia_s"])

        async def timed_tess():
            started = perf_counter()
            logger.info("stage=tess target=%s started max_sectors=%d", name, max_sectors)
            try:
                return await asyncio.to_thread(
                    tess.fetch_lightcurve,
                    planet.get("tic_id"),
                    planet["hostname"],
                    planet.get("pl_orbper"),
                    t0_btjd,
                    max_sectors,
                )
            finally:
                timings["tess_s"] = _elapsed(started)
                logger.info("stage=tess target=%s finished seconds=%.3f", name, timings["tess_s"])

        gaia_res, tess_res = await asyncio.gather(
            timed_gaia(), timed_tess(), return_exceptions=True
        )

    result = {
        "target": planet["pl_name"],
        "catalog": {
            "data": planet,
            "transit_midpoint_btjd_for_tess": t0_btjd,
            **prov("NASA Exoplanet Archive (pscomppars via TAP)"),
        },
        "errors": {},
    }
    if isinstance(gaia_res, Exception):
        result["errors"]["gaia"] = str(gaia_res)
    else:
        result["gaia_dr3"] = {**gaia_res, **prov("ESA Gaia DR3 TAP")}

    if isinstance(tess_res, Exception):
        result["errors"]["tess"] = str(tess_res)
    elif not tess_res["available"]:
        result["tess"] = tess_res
    else:
        arrays = {key: tess_res.pop(key) for key in ("time", "flux", "flux_err")}
        started = perf_counter()
        logger.info(
            "stage=analysis target=%s started input_points=%d max_points=%d catalog_period=%s",
            name,
            len(arrays["time"]),
            max_points,
            planet.get("pl_orbper"),
        )
        try:
            fit = await asyncio.to_thread(
                analysis.analyze_transits,
                arrays["time"],
                arrays["flux"],
                arrays["flux_err"],
                planet.get("pl_orbper"),
                0.5,
                None,
                max_points,
                period_window_pct,
            )
        except Exception as exc:
            logger.exception("stage=analysis target=%s failed", name)
            fit = {"error": f"{type(exc).__name__}: {exc}"}
        timings["analysis_s"] = _elapsed(started)
        logger.info(
            "stage=analysis target=%s finished seconds=%.3f",
            name,
            timings["analysis_s"],
        )
        result["tess"] = {
            **tess_res,
            "analysis": fit,
            "_arrays": arrays,
            **prov("MAST TESS SPOC via Lightkurve"),
        }

    timings["total_pipeline_s"] = _elapsed(run_started)
    result["performance"] = {
        **timings,
        "tess_max_sectors": max_sectors,
        "analysis_max_points": max_points,
        "catalog_period_window_pct": period_window_pct,
    }
    result["reproducibility"] = {
        "pipeline_version": __version__,
        "run_utc": now,
        "python": platform.python_version(),
        "packages": {
            package: _v(package)
            for package in (
                "numpy",
                "astropy",
                "lightkurve",
                "httpx",
                "sqlalchemy",
                "asyncpg",
                "arq",
                "matplotlib",
            )
        },
    }
    logger.info("stage=pipeline target=%s completed seconds=%.3f", name, timings["total_pipeline_s"])
    return result
