# Changelog

## 0.3.5 — Release candidate

Release-hardening update based on the live-validated v0.3.4 scientific pipeline.

- Passes TESS/analysis/worker performance controls from `.env` into the worker container.
- Makes AstroTarget INFO-level stage timing logs visible under the ARQ worker logging setup.
- Replaces remaining `research-grade` wording with the more precise `research-oriented` description.
- Documents the default BLS workflow as catalog-guided verification/characterization rather than independent period discovery.
- Adds repository `.gitignore` rules and removes local pytest cache artifacts.
- Keeps the v0.3.4 scientific pipeline and bounded-analysis defaults unchanged.

### Live validation inherited from v0.3.4

The pipeline was exercised end-to-end with live archive access for `WASP-12 b` and `HD 209458 b`, covering FastAPI, Redis/arq, NASA Exoplanet Archive, Gaia DR3, MAST/TESS, scientific analysis, PostgreSQL persistence, and API retrieval.
