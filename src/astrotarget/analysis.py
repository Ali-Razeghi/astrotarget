import numpy as np
from astropy.timeseries import BoxLeastSquares


def _phase(time: np.ndarray, period: float, t0: float) -> np.ndarray:
    return ((time - t0) + 0.5 * period) % period - 0.5 * period


def flatten_with_known_transits(
    time, raw_flux, window_length: int, period=None, t0=None, duration_guess_d: float = 0.3
):
    """Flatten a light curve while protecting catalog-predicted transits."""
    import lightkurve as lk

    lc = lk.LightCurve(time=time, flux=raw_flux)
    if period and t0:
        mask = np.abs(_phase(np.asarray(time), period, t0)) < (duration_guess_d * 1.5)
        flat = lc.flatten(window_length=window_length, mask=mask)
    else:
        flat = lc.flatten(window_length=window_length)
    return flat.flux.value


def _limit_points(time, flux, flux_err, max_points: int):
    """Deterministically thin very large light curves while retaining full time coverage."""
    n_input = int(time.size)
    if max_points <= 0 or n_input <= max_points:
        return time, flux, flux_err, n_input, 1
    stride = int(np.ceil(n_input / max_points))
    return time[::stride], flux[::stride], flux_err[::stride], n_input, stride


def analyze_transits(
    time,
    flux,
    flux_err=None,
    catalog_period=None,
    min_period=0.5,
    max_period=None,
    max_points=30_000,
    catalog_window_pct=2.0,
    catalog_period_samples=401,
) -> dict:
    """Run a bounded BLS transit search.

    If a catalog period is known, search a narrow grid around that period instead of doing an
    expensive blind all-period search. Very large light curves are deterministically thinned
    to a configurable ceiling while preserving the complete observing baseline.
    """
    time, flux = np.asarray(time, float), np.asarray(flux, float)
    mask = np.isfinite(time) & np.isfinite(flux)
    time, flux = time[mask], flux[mask]
    if flux_err is not None:
        flux_err = np.asarray(flux_err, float)[mask]
    if time.size < 500:
        raise ValueError("Too few valid points for a transit search")

    if flux_err is None or not np.all(np.isfinite(flux_err)):
        robust_sigma = 1.4826 * np.median(np.abs(flux - np.median(flux)))
        if not np.isfinite(robust_sigma) or robust_sigma <= 0:
            robust_sigma = float(np.std(flux)) or 1e-6
        flux_err = np.full_like(flux, robust_sigma)

    time, flux, flux_err, n_input, stride = _limit_points(
        time, flux, flux_err, int(max_points)
    )
    baseline = float(time.max() - time.min())
    durations = np.array([0.04, 0.06, 0.08, 0.12, 0.16, 0.24])
    bls = BoxLeastSquares(time, flux, dy=flux_err)

    if catalog_period and np.isfinite(catalog_period) and catalog_period > 0:
        catalog_period = float(catalog_period)
        frac = max(float(catalog_window_pct), 0.1) / 100.0
        lo = max(float(min_period), catalog_period * (1.0 - frac))
        hi = catalog_period * (1.0 + frac)
        if max_period is not None:
            hi = min(hi, float(max_period))
        if hi <= lo:
            lo, hi = catalog_period * 0.995, catalog_period * 1.005
        periods = np.linspace(lo, hi, max(int(catalog_period_samples), 51))
        search_mode = "catalog_guided"
    else:
        max_period = max_period or min(20.0, baseline / 2)
        periods = bls.autoperiod(
            durations,
            minimum_period=min_period,
            maximum_period=max_period,
            frequency_factor=10.0,
        )
        search_mode = "blind_bls"

    res = bls.power(periods, durations, objective="snr")
    i = int(np.argmax(res.power))
    out = {
        "recovered_period_d": float(res.period[i]),
        "t0_btjd": float(res.transit_time[i]),
        "duration_d": float(res.duration[i]),
        "depth_frac": float(res.depth[i]),
        "depth_snr": float(res.depth_snr[i]),
        "n_input_points": n_input,
        "n_points": int(time.size),
        "downsample_stride": stride,
        "baseline_d": baseline,
        "period_grid_size": int(len(periods)),
        "search_mode": search_mode,
        "method": "astropy BoxLeastSquares, objective=snr",
        "caveat": "BLS can lock onto aliases; compare recovered and catalog ephemerides.",
    }
    if catalog_period:
        out["catalog_period_d"] = float(catalog_period)
        out["period_diff_pct"] = (
            100.0 * (out["recovered_period_d"] - catalog_period) / catalog_period
        )
    return out
