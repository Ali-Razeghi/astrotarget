import json
import numpy as np
from astrotarget import db
from astrotarget.persist import _pack_npz, unpack_npz

def test_npz_pack_roundtrip():
    t = np.linspace(0, 5, 100)
    f = np.ones(100)
    e = np.ones(100) * 0.001
    out = unpack_npz(_pack_npz(t, f, e))
    assert np.allclose(out['time'], t) and np.allclose(out['flux'], f)

def test_schema_has_expected_tables():
    assert set(db.Base.metadata.tables) == {'stars', 'planets', 'light_curves', 'analysis_runs', 'jobs', 'data_sources'}

def test_analysis_runs_are_not_unique_per_version():
    t = db.Base.metadata.tables['analysis_runs']
    assert not any((c.__class__.__name__ == 'UniqueConstraint' for c in t.constraints))

def test_public_result_can_be_json_serialized_after_arrays_removed():
    r = {'target': 'x', 'tess': {'available': True, '_arrays': {'time': np.arange(3)}}}
    public = dict(r)
    public['tess'] = {k: v for k, v in r['tess'].items() if k != '_arrays'}
    json.dumps(public)
