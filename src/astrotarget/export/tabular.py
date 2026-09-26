import csv
import io
import json

import numpy as np
from astropy.io import fits
from astropy.time import Time


def to_csv_bytes(time, flux, flux_err) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_btjd", "flux_normalized", "flux_err"])
    for t, f, e in zip(time, flux, flux_err):
        w.writerow([t, f, e])
    return buf.getvalue().encode("utf-8")


def to_fits_bytes(time, flux, flux_err, header_meta: dict) -> bytes:
    col_defs = [
        fits.Column(name="TIME", format="D", array=np.asarray(time), unit="BTJD"),
        fits.Column(name="FLUX", format="D", array=np.asarray(flux)),
        fits.Column(name="FLUX_ERR", format="D", array=np.asarray(flux_err)),
    ]
    hdu = fits.BinTableHDU.from_columns(col_defs, name="LIGHTCURVE")
    for k, v in header_meta.items():
        key = k.upper()[:8]
        if v is None:
            continue
        try:
            hdu.header[key] = v
        except (ValueError, TypeError):
            hdu.header[key] = str(v)
    hdu.header["DATE"] = Time.now().isot
    primary = fits.PrimaryHDU()
    buf = io.BytesIO()
    fits.HDUList([primary, hdu]).writeto(buf)
    return buf.getvalue()


def to_json_bytes(result: dict) -> bytes:
    return json.dumps(result, indent=2, default=str).encode("utf-8")
