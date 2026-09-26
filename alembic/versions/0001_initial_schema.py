"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stars",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hostname", sa.String(128), unique=True, index=True, nullable=False),
        sa.Column("ra", sa.Float), sa.Column("dec", sa.Float), sa.Column("distance_pc", sa.Float),
        sa.Column("gaia_dr2_source_id", sa.String(32)), sa.Column("gaia_dr3_source_id", sa.String(32)),
        sa.Column("gaia_match_method", sa.String(64)), sa.Column("gaia_g_mag", sa.Float),
        sa.Column("gaia_parallax", sa.Float), sa.Column("gaia_pmra", sa.Float), sa.Column("gaia_pmdec", sa.Float),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "planets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pl_name", sa.String(128), unique=True, index=True, nullable=False),
        sa.Column("star_id", sa.Integer, sa.ForeignKey("stars.id"), nullable=False),
        sa.Column("orbital_period_d", sa.Float), sa.Column("transit_epoch_bjd", sa.Float),
        sa.Column("radius_re", sa.Float), sa.Column("mass_me", sa.Float), sa.Column("eq_temp_k", sa.Float),
        sa.Column("discovery_method", sa.String(64)), sa.Column("tic_id", sa.String(32)),
        sa.Column("catalog_ref", sa.String(256)), sa.Column("raw_catalog_json", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "light_curves",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("planet_id", sa.Integer, sa.ForeignKey("planets.id"), nullable=False),
        sa.Column("mission", sa.String(32), nullable=False, server_default="TESS"),
        sa.Column("sectors", sa.JSON), sa.Column("cadence_s", sa.Integer),
        sa.Column("n_points", sa.Integer), sa.Column("n_outliers_removed", sa.Integer),
        sa.Column("flatten_used_known_ephemeris", sa.Boolean, server_default=sa.false()),
        sa.Column("npz_blob", sa.LargeBinary, nullable=False),
        sa.Column("source", sa.String(128)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("planet_id", sa.Integer, sa.ForeignKey("planets.id"), nullable=False),
        sa.Column("light_curve_id", sa.Integer, sa.ForeignKey("light_curves.id")),
        sa.Column("pipeline_version", sa.String(32), nullable=False),
        sa.Column("recovered_period_d", sa.Float), sa.Column("t0_btjd", sa.Float),
        sa.Column("duration_d", sa.Float), sa.Column("depth_frac", sa.Float), sa.Column("depth_snr", sa.Float),
        sa.Column("period_diff_pct", sa.Float), sa.Column("result_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("target_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("analysis_runs.id")),
        sa.Column("error_message", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("base_url", sa.String(256), nullable=False),
        sa.Column("notes", sa.String(512)),
    )
    op.bulk_insert(
        sa.table("data_sources", sa.column("name"), sa.column("base_url"), sa.column("notes")),
        [
            {"name": "NASA Exoplanet Archive", "base_url": "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
             "notes": "pscomppars composite table, queried via TAP/ADQL"},
            {"name": "ESA Gaia DR3", "base_url": "https://gea.esac.esa.int/tap-server/tap/sync",
             "notes": "gaiadr3.gaia_source + gaiadr3.dr2_neighbourhood"},
            {"name": "MAST / TESS", "base_url": "https://mast.stsci.edu",
             "notes": "SPOC 2-min light curves via lightkurve"},
        ],
    )


def downgrade() -> None:
    op.drop_table("data_sources")
    op.drop_table("jobs")
    op.drop_table("analysis_runs")
    op.drop_table("light_curves")
    op.drop_table("planets")
    op.drop_table("stars")
