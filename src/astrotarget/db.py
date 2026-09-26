import os
from datetime import UTC, datetime
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, LargeBinary, String, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql+asyncpg://astro:astro@localhost:5432/astrotarget')
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

def _now():
    return datetime.now(UTC)

class Base(DeclarativeBase):
    pass

class Star(Base):
    __tablename__ = 'stars'
    id: Mapped[int] = mapped_column(primary_key=True)
    hostname: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    ra: Mapped[float | None] = mapped_column(Float)
    dec: Mapped[float | None] = mapped_column(Float)
    distance_pc: Mapped[float | None] = mapped_column(Float)
    gaia_dr2_source_id: Mapped[str | None] = mapped_column(String(32))
    gaia_dr3_source_id: Mapped[str | None] = mapped_column(String(32))
    gaia_match_method: Mapped[str | None] = mapped_column(String(64))
    gaia_g_mag: Mapped[float | None] = mapped_column(Float)
    gaia_parallax: Mapped[float | None] = mapped_column(Float)
    gaia_pmra: Mapped[float | None] = mapped_column(Float)
    gaia_pmdec: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    planets: Mapped[list['Planet']] = relationship(back_populates='star')

class Planet(Base):
    __tablename__ = 'planets'
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    star_id: Mapped[int] = mapped_column(ForeignKey('stars.id'))
    orbital_period_d: Mapped[float | None] = mapped_column(Float)
    transit_epoch_bjd: Mapped[float | None] = mapped_column(Float)
    radius_re: Mapped[float | None] = mapped_column(Float)
    mass_me: Mapped[float | None] = mapped_column(Float)
    eq_temp_k: Mapped[float | None] = mapped_column(Float)
    discovery_method: Mapped[str | None] = mapped_column(String(64))
    tic_id: Mapped[str | None] = mapped_column(String(32))
    catalog_ref: Mapped[str | None] = mapped_column(String(256))
    raw_catalog_json: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    star: Mapped['Star'] = relationship(back_populates='planets')

class LightCurve(Base):
    __tablename__ = 'light_curves'
    id: Mapped[int] = mapped_column(primary_key=True)
    planet_id: Mapped[int] = mapped_column(ForeignKey('planets.id'))
    mission: Mapped[str] = mapped_column(String(32), default='TESS')
    sectors: Mapped[list] = mapped_column(JSON)
    cadence_s: Mapped[int | None] = mapped_column(Integer)
    n_points: Mapped[int | None] = mapped_column(Integer)
    n_outliers_removed: Mapped[int | None] = mapped_column(Integer)
    flatten_used_known_ephemeris: Mapped[bool | None] = mapped_column(default=False)
    npz_blob: Mapped[bytes] = mapped_column(LargeBinary)
    source: Mapped[str | None] = mapped_column(String(128))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class AnalysisRun(Base):
    __tablename__ = 'analysis_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    planet_id: Mapped[int] = mapped_column(ForeignKey('planets.id'))
    light_curve_id: Mapped[int | None] = mapped_column(ForeignKey('light_curves.id'))
    pipeline_version: Mapped[str] = mapped_column(String(32))
    recovered_period_d: Mapped[float | None] = mapped_column(Float)
    t0_btjd: Mapped[float | None] = mapped_column(Float)
    duration_d: Mapped[float | None] = mapped_column(Float)
    depth_frac: Mapped[float | None] = mapped_column(Float)
    depth_snr: Mapped[float | None] = mapped_column(Float)
    period_diff_pct: Mapped[float | None] = mapped_column(Float)
    result_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    planet: Mapped['Planet'] = relationship()
    light_curve: Mapped['LightCurve'] = relationship()

class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    target_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default='queued')
    run_id: Mapped[int | None] = mapped_column(ForeignKey('analysis_runs.id'))
    error_message: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

class DataSource(Base):
    __tablename__ = 'data_sources'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    base_url: Mapped[str] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(String(512))

async def ping():
    async with engine.connect() as c:
        await c.execute(text('SELECT 1'))

async def latest_run_for_planet_name(s: AsyncSession, pl_name: str):
    q = select(AnalysisRun).join(Planet).where(Planet.pl_name == pl_name).order_by(AnalysisRun.created_at.desc()).limit(1)
    return (await s.execute(q)).scalar_one_or_none()

async def get_run(s, run_id):
    return await s.get(AnalysisRun, run_id)

async def get_job(s, job_id):
    return await s.get(Job, job_id)

async def get_light_curve(s, lc_id):
    return await s.get(LightCurve, lc_id)
