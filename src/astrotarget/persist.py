import io

import numpy as np
from sqlalchemy import select

from . import db


async def upsert_star(s, hostname: str, planet_row: dict, gaia: dict | None) -> db.Star:
    star = (await s.execute(select(db.Star).where(db.Star.hostname == hostname))).scalar_one_or_none()
    if star is None:
        star = db.Star(hostname=hostname)
        s.add(star)
    star.ra = planet_row.get("ra")
    star.dec = planet_row.get("dec")
    star.distance_pc = planet_row.get("sy_dist")
    if gaia and gaia.get("match"):
        m = gaia["match"]
        star.gaia_dr3_source_id = str(m.get("source_id"))
        star.gaia_match_method = gaia.get("match_method")
        if gaia.get("dr2_source_id") is not None:
            star.gaia_dr2_source_id = str(gaia["dr2_source_id"])
        star.gaia_g_mag = m.get("phot_g_mean_mag")
        star.gaia_parallax = m.get("parallax")
        star.gaia_pmra = m.get("pmra")
        star.gaia_pmdec = m.get("pmdec")
    await s.flush()
    return star


async def upsert_planet(s, star: db.Star, planet_row: dict, raw_result: dict) -> db.Planet:
    pl = (await s.execute(select(db.Planet).where(db.Planet.pl_name == planet_row["pl_name"]))).scalar_one_or_none()
    if pl is None:
        pl = db.Planet(pl_name=planet_row["pl_name"], star_id=star.id)
        s.add(pl)
    pl.star_id = star.id
    pl.orbital_period_d = planet_row.get("pl_orbper")
    pl.transit_epoch_bjd = planet_row.get("pl_tranmid")
    pl.radius_re = planet_row.get("pl_rade")
    pl.mass_me = planet_row.get("pl_bmasse")
    pl.eq_temp_k = planet_row.get("pl_eqt")
    pl.discovery_method = planet_row.get("discoverymethod")
    pl.tic_id = planet_row.get("tic_id")
    # PSCompPars has per-parameter reference links rather than PS pl_refname.
    # Keep this legacy nullable field unset instead of storing a semantically different reference.
    pl.catalog_ref = None
    pl.raw_catalog_json = raw_result["catalog"]
    await s.flush()
    return pl


def _pack_npz(time, flux, flux_err) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, time=np.asarray(time), flux=np.asarray(flux), flux_err=np.asarray(flux_err))
    return buf.getvalue()


def unpack_npz(blob: bytes) -> dict:
    with np.load(io.BytesIO(blob)) as z:
        return {"time": z["time"], "flux": z["flux"], "flux_err": z["flux_err"]}


async def store_light_curve(s, planet: db.Planet, tess_result: dict, arrays: dict) -> db.LightCurve:
    lc = db.LightCurve(
        planet_id=planet.id, mission="TESS", sectors=tess_result.get("sectors", []),
        cadence_s=tess_result.get("cadence_s"), n_points=len(arrays["time"]),
        n_outliers_removed=tess_result.get("n_outliers_removed"),
        flatten_used_known_ephemeris=tess_result.get("flatten_used_known_ephemeris", False),
        npz_blob=_pack_npz(arrays["time"], arrays["flux"], arrays["flux_err"]),
        source="MAST TESS SPOC 2-min via lightkurve",
    )
    s.add(lc)
    await s.flush()
    return lc


async def store_run(s, planet: db.Planet, light_curve: db.LightCurve | None,
                    pipeline_version: str, full_result: dict) -> db.AnalysisRun:
    fit = full_result.get("tess", {}).get("analysis", {}) if isinstance(full_result.get("tess"), dict) else {}
    # Every execution is a distinct scientific run. Do not overwrite an older run merely
    # because it used the same software version.
    run = db.AnalysisRun(planet_id=planet.id, pipeline_version=pipeline_version)
    run.light_curve_id = light_curve.id if light_curve else None
    run.recovered_period_d = fit.get("recovered_period_d")
    run.t0_btjd = fit.get("t0_btjd")
    run.duration_d = fit.get("duration_d")
    run.depth_frac = fit.get("depth_frac")
    run.depth_snr = fit.get("depth_snr")
    run.period_diff_pct = fit.get("period_diff_pct")
    # NumPy arrays are binary science products and cannot be written to JSONB.
    public_result = dict(full_result)
    if isinstance(full_result.get("tess"), dict):
        public_result["tess"] = {k: v for k, v in full_result["tess"].items() if k != "_arrays"}
    run.result_json = public_result
    s.add(run)
    await s.flush()
    return run


async def persist_pipeline_result(s, full_result: dict, pipeline_version: str) -> db.AnalysisRun:
    planet_row = full_result["catalog"]["data"]
    gaia = full_result.get("gaia_dr3")
    star = await upsert_star(s, planet_row["hostname"], planet_row, gaia)
    planet = await upsert_planet(s, star, planet_row, full_result)
    light_curve = None
    tess = full_result.get("tess")
    if isinstance(tess, dict) and tess.get("available") and "_arrays" in tess:
        light_curve = await store_light_curve(s, planet, tess, tess["_arrays"])
    run = await store_run(s, planet, light_curve, pipeline_version, full_result)
    await s.commit()
    return run
