"""sim_orbit3d — schematic verification views for the 3D orbit (Day 7).

TWO views, by design, because they catch different failures:
  1. Rotating matplotlib-3D plot — for intuition ("a camera circling the subject").
  2. Tri-view orthographic projections (top XY / side XZ / front YZ) — for catching
     LIES: a subtly wrong path (drift, ellipse, off look-at) looks obviously wrong in
     at least one orthographic view even when the 3D plot looks plausible.

Both drive off the SAME flightpath.OrbitPath code — we validate the real path, not a
parallel mock. These are SCHEMATIC matplotlib views, NOT a renderer: there is no
photoreal imagery and no view synthesis (see the localization caveat in notes.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

from AirLine.flightpath import OrbitPath


def _writer(fps: int):
    from matplotlib.animation import FFMpegWriter, PillowWriter
    if FFMpegWriter.isAvailable():
        return FFMpegWriter(fps=fps, bitrate=2400), ".mp4"
    return PillowWriter(fps=fps), ".gif"


def _sample(path: OrbitPath, n_frames: int,
            centers_fn: Optional[Sequence] = None):
    """Return (cam_positions[n,3], target_positions[n,3]) over ~1.25 periods."""
    ts = np.linspace(0.0, path.period * 1.25, n_frames)
    cams, tgts = [], []
    for i, t in enumerate(ts):
        c = None if centers_fn is None else centers_fn(t)
        cams.append(path.position_at(t, c))
        tgts.append(path.center_at(t, c))
    return np.array(cams), np.array(tgts)


def _bounds(cams, tgts):
    allp = np.vstack([cams, tgts])
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    pad = 0.15 * (hi - lo + 1e-6)
    return lo - pad, hi + pad


def render_3d(path: OrbitPath, out_path: str, n_frames: int = 120,
              fps: int = 24, centers_fn: Optional[Sequence] = None,
              title: str = "AirLine orbit (3D)") -> str:
    cams, tgts = _sample(path, n_frames, centers_fn)
    lo, hi = _bounds(cams, tgts)
    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_subplot(111, projection="3d")
    writer, ext = _writer(fps)
    out = str(Path(out_path).with_suffix(ext))

    def draw(i):
        ax.clear()
        ax.plot(cams[:, 0], cams[:, 1], cams[:, 2], "-", color="#2a6", lw=1.2, alpha=0.7)
        ax.scatter(*tgts[i], color="#d22", s=60, label="target")
        ax.scatter(*cams[i], color="#06c", s=50, label="camera")
        ax.plot(*np.array([cams[i], tgts[i]]).T, "--", color="#888", lw=1.0)
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
        ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z (up)")
        ax.set_title(f"{title}  frame {i + 1}/{n_frames}")
        ax.view_init(elev=22, azim=(i * 3) % 360)  # rotate for intuition
        ax.legend(loc="upper right")

    anim = FuncAnimation(fig, draw, frames=n_frames, interval=1000 / fps)
    anim.save(out, writer=writer)
    plt.close(fig)
    return out


def render_triview(path: OrbitPath, out_path: str, n_frames: int = 120,
                   fps: int = 24, centers_fn: Optional[Sequence] = None,
                   title: str = "AirLine orbit (orthographic)") -> str:
    cams, tgts = _sample(path, n_frames, centers_fn)
    lo, hi = _bounds(cams, tgts)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))
    # (axis, x-index, y-index, label)
    views = [(axes[0], 0, 1, "TOP  (X-Y)"), (axes[1], 0, 2, "SIDE (X-Z)"),
             (axes[2], 1, 2, "FRONT (Y-Z)")]
    writer, ext = _writer(fps)
    out = str(Path(out_path).with_suffix(ext))

    def draw(i):
        for ax, a, b, name in views:
            ax.clear()
            ax.plot(cams[:, a], cams[:, b], "-", color="#2a6", lw=1.0, alpha=0.6)
            ax.scatter(tgts[i, a], tgts[i, b], color="#d22", s=50)
            ax.scatter(cams[i, a], cams[i, b], color="#06c", s=40)
            ax.plot([cams[i, a], tgts[i, a]], [cams[i, b], tgts[i, b]],
                    "--", color="#888", lw=0.9)
            ax.set_xlim(lo[a], hi[a]); ax.set_ylim(lo[b], hi[b])
            ax.set_aspect("equal", adjustable="box")
            ax.set_title(name)
            ax.grid(True, alpha=0.3)
        fig.suptitle(f"{title}  frame {i + 1}/{n_frames}")

    anim = FuncAnimation(fig, draw, frames=n_frames, interval=1000 / fps)
    anim.save(out, writer=writer)
    plt.close(fig)
    return out
