import numpy as np
import pytest
from astrotarget.analysis import analyze_transits

def synthetic(period=1.091, depth=0.014, dur=0.125, t0=0.4, days=27, noise=0.002, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(0, days, 2 / 1440)
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    f = 1 + rng.normal(0, noise, t.size)
    f[np.abs(phase) < dur / 2] -= depth
    return (t, f)

def test_recovers_injected_transit():
    t, f = synthetic()
    r = analyze_transits(t, f, catalog_period=1.091)
    assert abs(r['period_diff_pct']) < 0.5
    assert 0.01 < r['depth_frac'] < 0.018
    assert r['depth_snr'] > 10

def test_rejects_too_few_points():
    with pytest.raises(ValueError):
        analyze_transits(np.arange(10.0), np.ones(10))


def test_catalog_guided_search_is_bounded():
    t, f = synthetic(days=10)
    r = analyze_transits(t, f, catalog_period=1.091, max_points=5000)
    assert r["search_mode"] == "catalog_guided"
    assert r["period_grid_size"] == 401
    assert r["n_points"] <= 5000
    assert r["n_input_points"] == len(t)
    assert r["downsample_stride"] >= 1
    assert abs(r["period_diff_pct"]) < 0.5
