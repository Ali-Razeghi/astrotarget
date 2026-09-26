import io
import json
import numpy as np
from astropy.io import fits
from astrotarget.export.plot import lightcurve_png
from astrotarget.export.report import build_pdf_report
from astrotarget.export.tabular import to_csv_bytes, to_fits_bytes, to_json_bytes
TIME = np.linspace(0, 10, 2000)
FLUX = 1 + 0.001 * np.sin(TIME)
ERR = np.full_like(TIME, 0.001)

def test_csv_roundtrip():
    raw = to_csv_bytes(TIME, FLUX, ERR).decode()
    lines = raw.strip().splitlines()
    assert lines[0] == 'time_btjd,flux_normalized,flux_err'
    assert len(lines) == len(TIME) + 1

def test_fits_roundtrip():
    blob = to_fits_bytes(TIME, FLUX, ERR, {'target': 'WASP-12 b', 'period_d': 1.09, 'note': None})
    with fits.open(io.BytesIO(blob)) as hdul:
        data = hdul['LIGHTCURVE'].data
        assert len(data['TIME']) == len(TIME)
        assert hdul['LIGHTCURVE'].header['TARGET'] == 'WASP-12 b'

def test_json_bytes_is_valid_json():
    out = json.loads(to_json_bytes({'a': 1, 'b': [1, 2, 3]}))
    assert out['a'] == 1

def test_plot_png_smoke():
    png = lightcurve_png(TIME, FLUX, 'WASP-12 b', period=1.091, t0=0.4, duration=0.1)
    assert png[:8] == b'\x89PNG\r\n\x1a\n'

def test_pdf_report_smoke():
    result = {'target': 'WASP-12 b', 'catalog': {'data': {'hostname': 'WASP-12', 'ra': 97.6, 'dec': 29.6, 'pl_orbper': 1.091, 'pl_rade': 21.0, 'pl_bmasse': 465.0, 'pl_eqt': 2500, 'discoverymethod': 'Transit'}}, 'gaia_dr3': {'match': {'source_id': 999, 'parallax': 5.0, 'phot_g_mean_mag': 11.7}, 'match_method': 'dr2_neighbourhood_crossmatch', 'ambiguous': False, 'distance_pc_naive': 200.0}, 'tess': {'available': True, 'sectors': [20, 47], 'cadence_s': 120, 'analysis': {'n_points': 2000, 'recovered_period_d': 1.09, 'catalog_period_d': 1.091, 'period_diff_pct': -0.09, 'depth_frac': 0.014, 'depth_snr': 25, 'caveat': 'check aliases', 't0_btjd': 0.4, 'duration_d': 0.1}}, 'reproducibility': {'pipeline_version': '0.2.0', 'python': '3.12', 'packages': {'numpy': '1.26', 'astropy': '6.0'}}}
    png = lightcurve_png(TIME, FLUX, 'WASP-12 b', period=1.091, t0=0.4, duration=0.1)
    pdf = build_pdf_report(result, png)
    assert pdf[:4] == b'%PDF'
