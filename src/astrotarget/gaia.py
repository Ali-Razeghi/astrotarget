from .http import get_json

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
SOURCE_COLUMNS = (
    "source_id, ra, dec, parallax, parallax_error, pmra, pmdec, "
    "phot_g_mean_mag, bp_rp, radial_velocity, radial_velocity_error, ruwe"
)

def build_cone_query(ra: float, dec: float, radius_arcsec: float) -> str:
    ra, dec, radius_arcsec = float(ra), float(dec), float(radius_arcsec)
    r = radius_arcsec / 3600.0
    return (
        f"SELECT TOP 20 {SOURCE_COLUMNS}, "
        f"DISTANCE(POINT('ICRS',ra,dec),POINT('ICRS',{ra},{dec})) AS sep_deg "
        "FROM gaiadr3.gaia_source "
        f"WHERE 1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra},{dec},{r})) ORDER BY sep_deg"
    )

def build_dr2_neighbourhood_query(dr2_id: int) -> str:
    dr2_id = int(dr2_id)
    return (
        "SELECT n.dr3_source_id, n.angular_distance, n.magnitude_difference, n.proper_motion_propagation "
        "FROM gaiadr3.dr2_neighbourhood AS n "
        f"WHERE n.dr2_source_id = {dr2_id} ORDER BY ABS(n.magnitude_difference) ASC"
    )

def build_source_by_id_query(source_id: int) -> str:
    return f"SELECT {SOURCE_COLUMNS} FROM gaiadr3.gaia_source WHERE source_id = {int(source_id)}"

def _g(c):
    v = c.get("phot_g_mean_mag")
    return float(v) if v is not None else 99.0

def select_cone_match(candidates: list[dict], g_mag: float | None) -> dict:
    if not candidates:
        return {"match": None, "n_candidates": 0, "ambiguous": False}
    key = (lambda c: (abs(_g(c) - float(g_mag)), c["sep_deg"])) if g_mag is not None else (lambda c: c["sep_deg"])
    scored = sorted(candidates, key=key)
    best = scored[0]
    # Ambiguity is deliberately conservative: a second source with similar G magnitude
    # means the automated identification should be reviewed by a researcher.
    ambiguous = any(abs(_g(c) - _g(best)) < 1.0 for c in scored[1:])
    return {"match": best, "n_candidates": len(candidates), "ambiguous": ambiguous}

async def _query(client, sql: str):
    data = await get_json(client, GAIA_TAP, {"REQUEST":"doQuery","LANG":"ADQL","FORMAT":"json","QUERY":sql})
    cols = [m["name"] for m in data["metadata"]]
    return [dict(zip(cols, r)) for r in data["data"]]

async def crossmatch(client, ra, dec, g_mag, dr3_id: int | None = None,
                     dr2_id: int | None = None, radius_arcsec: float = 10.0) -> dict:
    # Best case: NASA already supplies Gaia DR3, so do not cross-match heuristically at all.
    if dr3_id is not None:
        rows = await _query(client, build_source_by_id_query(dr3_id))
        if rows:
            return _add_distance({"match": rows[0], "n_candidates": 1, "ambiguous": False,
                                  "match_method": "nasa_gaia_dr3_id", "dr3_source_id": dr3_id})
    if dr2_id is not None:
        neighbours = await _query(client, build_dr2_neighbourhood_query(dr2_id))
        if neighbours:
            best = neighbours[0]
            rows = await _query(client, build_source_by_id_query(best["dr3_source_id"]))
            if rows:
                return _add_distance({"match": rows[0], "n_candidates": len(neighbours),
                    "ambiguous": len(neighbours) > 1 and abs(float(neighbours[1].get("magnitude_difference") or 99)) < 1,
                    "match_method": "dr2_neighbourhood_crossmatch", "dr2_source_id": dr2_id,
                    "crossmatch_angular_distance_mas": best.get("angular_distance")})
    rows = await _query(client, build_cone_query(ra, dec, radius_arcsec))
    out = select_cone_match(rows, g_mag)
    out["match_method"] = "cone_search_heuristic"
    return _add_distance(out)

def _add_distance(out: dict) -> dict:
    m = out.get("match")
    if m and m.get("parallax") and m["parallax"] > 0:
        out["distance_pc_naive"] = 1000.0 / m["parallax"]
        out["distance_warning"] = "Inverse-parallax estimate; not a Bayesian distance posterior."
    return out
