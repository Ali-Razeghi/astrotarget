import asyncio

import httpx
import pytest
from astrotarget import gaia, nasa

def test_adql_escaping():
    assert "x'' OR ''1''=''1" in nasa.build_query("x' OR '1'='1")

def test_nasa_uses_current_pscomppars_columns():
    q = nasa.build_query("WASP-12 b")
    assert "gaia_dr2_id" in q
    assert "gaia_dr3_id" in q
    assert "tic_id" in q
    assert "gaia_id," not in q
    assert "pl_refname" not in q

def test_extract_gaia_ids():
    assert nasa.extract_gaia_id('Gaia DR2 6236469606352205696') == 6236469606352205696
    assert nasa.extract_gaia_id('Gaia DR3 1234567890123456789') == 1234567890123456789
    assert nasa.extract_gaia_id(None) is None

def test_transit_midpoint_to_btjd():
    assert abs(nasa.transit_midpoint_btjd(2458000.25) - 1000.25) < 1e-09
    assert nasa.transit_midpoint_btjd(1000.25) == 1000.25

def test_nasa_fetch_mocked():

    def handler(req):
        assert 'wasp-12 b' in req.url.params['query']
        return httpx.Response(200, json=[{'pl_name': 'WASP-12 b', 'pl_orbper': 1.09}])

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await nasa.fetch_planet(c, 'wasp-12_b')
    assert asyncio.run(go())['pl_name'] == 'WASP-12 b'

def test_gaia_cone_match_prefers_magnitude_agreement():
    c = [{'source_id': 1, 'sep_deg': 0.0001, 'phot_g_mean_mag': 18.0}, {'source_id': 2, 'sep_deg': 0.002, 'phot_g_mean_mag': 11.6}]
    assert gaia.select_cone_match(c, 11.6)['match']['source_id'] == 2

def test_gaia_no_candidates():
    assert gaia.select_cone_match([], 10)['match'] is None

def test_gaia_prefers_direct_dr3_id():
    calls = []

    def handler(req):
        q = req.url.params['QUERY']
        calls.append(q)
        assert 'source_id = 999' in q
        return httpx.Response(200, json={'metadata': [{'name': 'source_id'}, {'name': 'parallax'}], 'data': [[999, 5.0]]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await gaia.crossmatch(c, 10, 20, 10, dr3_id=999, dr2_id=123)
    out = asyncio.run(go())
    assert out['match_method'] == 'nasa_gaia_dr3_id' and len(calls) == 1

def test_gaia_crossmatch_uses_dr2_neighbourhood_when_available():
    calls = []

    def handler(req):
        q = req.url.params['QUERY']
        calls.append(q)
        if 'dr2_neighbourhood' in q:
            return httpx.Response(200, json={'metadata': [{'name': 'dr3_source_id'}, {'name': 'angular_distance'}, {'name': 'magnitude_difference'}, {'name': 'proper_motion_propagation'}], 'data': [[999, 0.01, 0.02, True]]})
        assert 'source_id = 999' in q
        return httpx.Response(200, json={'metadata': [{'name': 'source_id'}, {'name': 'parallax'}, {'name': 'phot_g_mean_mag'}], 'data': [[999, 5.0, 10.0]]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await gaia.crossmatch(c, 10, 20, 10, dr2_id=123456)
    out = asyncio.run(go())
    assert out['match_method'] == 'dr2_neighbourhood_crossmatch' and out['match']['source_id'] == 999 and (len(calls) == 2)

def test_gaia_falls_back_to_cone():

    def handler(req):
        return httpx.Response(200, json={'metadata': [{'name': 'source_id'}, {'name': 'sep_deg'}, {'name': 'phot_g_mean_mag'}, {'name': 'parallax'}], 'data': [[42, 0.001, 11.5, 4.0]]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await gaia.crossmatch(c, 10, 20, 11.5)
    assert asyncio.run(go())['match_method'] == 'cone_search_heuristic'


def test_http_400_is_not_retried_and_includes_upstream_detail():
    calls = 0

    def handler(req):
        nonlocal calls
        calls += 1
        return httpx.Response(400, text="ORA-00904: invalid identifier pl_refname")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await nasa.fetch_planet(client, "WASP-12 b")

    with pytest.raises(RuntimeError, match="invalid identifier pl_refname"):
        asyncio.run(go())
    assert calls == 1
