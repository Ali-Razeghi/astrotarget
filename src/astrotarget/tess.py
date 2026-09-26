import logging
import re

import numpy as np

SECTOR_RE = re.compile(r"Sector\s+(\d+)", re.I)
logger = logging.getLogger(__name__)

def _sector_numbers(sr):
    out = []
    table = sr.table
    if "sequence_number" in table.colnames:
        for x in table["sequence_number"]:
            if x is not None:
                try: out.append(int(x))
                except (TypeError, ValueError): pass
    if not out and "mission" in table.colnames:
        for x in table["mission"]:
            m = SECTOR_RE.search(str(x))
            if m: out.append(int(m.group(1)))
    return sorted(set(out))

def fetch_lightcurve(tic_id, hostname: str, catalog_period=None, catalog_t0_btjd=None,
                     max_sectors: int = 2) -> dict:
    """Blocking MAST/Lightkurve I/O; execute in a worker thread."""
    import lightkurve as lk
    from .analysis import flatten_with_known_transits

    query = tic_id or hostname
    # 'short' is future-friendlier than hard-coding 120 s: Lightkurve defines it as
    # official 1-min/2-min short-cadence products.
    sr = lk.search_lightcurve(query, mission="TESS", author="SPOC", exptime="short")
    if len(sr) == 0:
        # Some targets only have other official SPOC cadences. Search all SPOC products.
        sr = lk.search_lightcurve(query, mission="TESS", author="SPOC")
    if len(sr) == 0:
        return {"available": False, "query": str(query), "reason": "No TESS SPOC light curve found"}

    sr = sr[:max_sectors]
    collection = sr.download_all(quality_bitmask="default", flux_column="pdcsap_flux")
    if collection is None or len(collection) == 0:
        return {"available": False, "query": str(query), "reason": "MAST products found but download returned none"}
    lc = collection.stitch().remove_nans().normalize()
    n_raw = len(lc)
    lc = lc.remove_outliers(sigma_upper=4, sigma_lower=20)
    n_clipped = n_raw - len(lc)
    t = np.asarray(lc.time.value, dtype=float)
    f = np.asarray(lc.flux.value, dtype=float)
    ferr = np.asarray(lc.flux_err.value, dtype=float)
    flat_flux = flatten_with_known_transits(t, f, window_length=721,
        period=catalog_period, t0=catalog_t0_btjd)
    exptimes = []
    try:
        exptimes = sorted({int(round(float(x))) for x in sr.exptime.value})
    except (AttributeError, TypeError, ValueError) as exc:
        # Product metadata can differ between TESS data products. A missing or
        # malformed exposure-time field should not invalidate an otherwise
        # usable light curve; retain cadence=None and make the fallback visible.
        logger.warning('Could not determine TESS exposure time from search metadata: %s', exc)
    cadence = int(np.median(exptimes)) if exptimes else None
    return {"available": True, "query": str(query), "sectors": _sector_numbers(sr), "products_selected": int(len(sr)),
        "cadence_s": cadence, "cadences_s": exptimes, "n_raw": int(n_raw),
        "n_outliers_removed": int(n_clipped), "time": t, "flux": np.asarray(flat_flux),
        "flux_err": ferr, "flux_column": "PDCSAP_FLUX", "quality_bitmask": "default",
        "flatten_used_known_ephemeris": bool(catalog_period and catalog_t0_btjd)}
