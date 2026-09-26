import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def lightcurve_png(time, flux, target: str, period=None, t0=None, duration=None) -> bytes:
    """Raw light curve, plus a phase-folded panel when a period/t0 is available."""
    time, flux = np.asarray(time), np.asarray(flux)
    ncols = 2 if (period and t0) else 1
    fig, axes = plt.subplots(1, ncols, figsize=(6 * ncols, 4))
    axes = np.atleast_1d(axes)

    axes[0].plot(time, flux, ".", ms=1.5, alpha=0.5, color="#2c6fbb")
    axes[0].set_xlabel("Time (BTJD)")
    axes[0].set_ylabel("Normalized flux")
    axes[0].set_title(f"{target} — TESS light curve")

    if ncols == 2:
        phase = ((time - t0) + 0.5 * period) % period - 0.5 * period
        order = np.argsort(phase)
        axes[1].plot(phase[order], flux[order], ".", ms=1.5, alpha=0.4, color="#2c6fbb")
        if duration:
            axes[1].axvspan(-duration / 2, duration / 2, color="orange", alpha=0.15, label="transit window")
            axes[1].legend(loc="lower right", fontsize=8)
        axes[1].set_xlabel(f"Phase (days), P={period:.5f} d")
        axes[1].set_title("Phase-folded")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    return buf.getvalue()
