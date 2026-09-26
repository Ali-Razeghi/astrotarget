import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _rows(pairs):
    return [[k, "" if v is None else str(v)] for k, v in pairs]


def _table(rows):
    t = Table(rows, colWidths=[180, 300])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
    ]))
    return t


def build_pdf_report(result: dict, png_bytes: bytes | None) -> bytes:
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=f"AstroTarget report: {result.get('target')}")
    story = [Paragraph("AstroTarget Research Target Report", styles["Title"]),
            Paragraph(result.get("target", "unknown"), styles["Heading2"]), Spacer(1, 0.2 * inch)]

    planet = result.get("catalog", {}).get("data", {})
    story.append(Paragraph("Planetary parameters (NASA Exoplanet Archive)", styles["Heading3"]))
    story.append(_table(_rows([
        ("Host star", planet.get("hostname")), ("RA / Dec", f"{planet.get('ra')} / {planet.get('dec')}"),
        ("Orbital period (d)", planet.get("pl_orbper")), ("Radius (Earth radii)", planet.get("pl_rade")),
        ("Mass (Earth masses)", planet.get("pl_bmasse")), ("Eq. temperature (K)", planet.get("pl_eqt")),
        ("Discovery method", planet.get("discoverymethod")),
    ])))
    story.append(Spacer(1, 0.2 * inch))

    gaia = result.get("gaia_dr3")
    if gaia:
        m = gaia.get("match") or {}
        story.append(Paragraph("Gaia DR3 cross-match", styles["Heading3"]))
        story.append(_table(_rows([
            ("Match method", gaia.get("match_method")), ("Gaia source_id", m.get("source_id")),
            ("Parallax (mas)", m.get("parallax")), ("Distance (pc, 1/parallax)", gaia.get("distance_pc_naive")),
            ("G magnitude", m.get("phot_g_mean_mag")), ("Ambiguous match?", gaia.get("ambiguous")),
        ])))
        story.append(Spacer(1, 0.2 * inch))

    tess = result.get("tess")
    if isinstance(tess, dict) and tess.get("available"):
        fit = tess.get("analysis", {})
        story.append(Paragraph("TESS observations & transit analysis", styles["Heading3"]))
        story.append(_table(_rows([
            ("Sectors", tess.get("sectors")), ("Cadence (s)", tess.get("cadence_s")),
            ("Points analyzed", fit.get("n_points")),
            ("Recovered period (d)", fit.get("recovered_period_d")),
            ("Catalog period (d)", fit.get("catalog_period_d")),
            ("Period difference (%)", fit.get("period_diff_pct")),
            ("Transit depth (frac)", fit.get("depth_frac")), ("Depth S/N", fit.get("depth_snr")),
            ("Note", fit.get("caveat")),
        ])))
        story.append(Spacer(1, 0.2 * inch))
        if png_bytes:
            story.append(Image(io.BytesIO(png_bytes), width=6.5 * inch, height=6.5 * inch * 0.4))
            story.append(Spacer(1, 0.2 * inch))
    elif isinstance(tess, dict):
        story.append(Paragraph("No TESS SPOC 2-min light curve was found for this target.", styles["Normal"]))

    repro = result.get("reproducibility", {})
    story.append(Paragraph("Reproducibility", styles["Heading3"]))
    story.append(_table(_rows([
        ("Pipeline version", repro.get("pipeline_version")), ("Python", repro.get("python")),
        *[(f"package:{k}", v) for k, v in (repro.get("packages") or {}).items()],
    ])))

    doc.build(story)
    return buf.getvalue()
