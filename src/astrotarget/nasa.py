import re

from .http import get_json

NASA_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

# Keep this list deliberately small and limited to fields consumed by the pipeline.
# These columns are documented for the current PSCompPars table. In particular,
# pl_refname belongs to PS, not PSCompPars, and must not be queried here.
COLUMNS = (
    "pl_name,hostname,ra,dec,pl_orbper,pl_tranmid,pl_rade,pl_bmasse,pl_eqt,"
    "pl_trandep,pl_trandur,discoverymethod,sy_dist,sy_gaiamag,gaia_dr2_id,gaia_dr3_id,"
    "tic_id"
)
GAIA_ID_RE = re.compile(r"(?:Gaia\s+DR[23]\s+)?(\d{10,})", re.I)


def normalize_name(name: str) -> str:
    return " ".join(name.strip().replace("_", " ").split())


def escape_adql(value: str) -> str:
    return value.replace("'", "''")


def build_query(name: str) -> str:
    n = escape_adql(normalize_name(name))
    return f"select {COLUMNS} from pscomppars where upper(pl_name)=upper('{n}')"


def extract_gaia_id(value: str | int | None) -> int | None:
    if value is None:
        return None
    match = GAIA_ID_RE.search(str(value))
    return int(match.group(1)) if match else None


def extract_gaia_dr2_id(value):
    return extract_gaia_id(value)


def transit_midpoint_btjd(value: float | None) -> float | None:
    """Convert a full JD/BJD-style transit midpoint to TESS BTJD when needed."""
    if value is None:
        return None
    midpoint = float(value)
    return midpoint - 2457000.0 if midpoint > 2_000_000 else midpoint


async def fetch_planet(client, name: str) -> dict | None:
    rows = await get_json(
        client,
        NASA_TAP,
        {"query": build_query(name), "format": "json"},
    )
    return rows[0] if rows else None
