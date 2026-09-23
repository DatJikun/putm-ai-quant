"""Turn CFD-Post screenshots into numbers using the locked colour bar.

The bar is read from the picture. Folder name picks the scale from the
Omega post-pro script (user-specified min/max). Values are picture-space:
a 3D view is not square metres and not a solver integral.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from ingest.pictures import FRAME_RE, _field_from_folder

# Skala z Post Pro Ansys 2023_Omega.txt, Contour Range = User Specified.
# Góra legendy = max, dół = min.
SCALE = {
    "cp": (-1.5, 1.0),
    "cpt": (-1.0, 1.0),
    "vel": (0.0, 2.5),
    "wss": (0.0, 3.0),
    "yplus": (0.0, 2.0),
}

# Koniec animacji Y zależy od pola. X i Z są wspólne. 150 klatek.
X_RANGE = (-1.1, 2.5)
Z_RANGE = (0.0, 1.5)
Y_END = {"cp": -0.9, "cpt": -0.8, "vel": -0.8}


def _sat(rgb: np.ndarray) -> np.ndarray:
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    return mx - mn


def find_colourbar(rgb: np.ndarray) -> tuple[int, int, int] | None:
    """Return (x, y0, y1) of the vertical legend, or None."""
    height, width = rgb.shape[:2]
    sat = _sat(rgb.astype(np.int16)) > 50
    best = None
    limit = min(140, width // 5)
    for x in range(8, limit):
        ys = np.where(sat[:, x])[0]
        if ys.size < 40:
            continue
        # keep the longest run, not scattered car pixels
        breaks = np.where(np.diff(ys) > 3)[0]
        starts = np.r_[0, breaks + 1]
        ends = np.r_[breaks, ys.size - 1]
        run = int(np.argmax(ends - starts))
        y0, y1 = int(ys[starts[run]]), int(ys[ends[run]])
        span = y1 - y0
        if span < 40:
            continue
        if best is None or span > best[0]:
            best = (span, x, y0, y1)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _bar_colours(rgb: np.ndarray, x: int, y0: int, y1: int, n: int = 48) -> np.ndarray:
    ys = np.linspace(y0 + 2, y1 - 2, n).astype(int)
    x0 = max(0, x - 1)
    x1 = min(rgb.shape[1], x + 2)
    return rgb[ys, x0:x1].mean(axis=1)


def _values(rgb: np.ndarray, bar: np.ndarray, vmin: float, vmax: float, x_cut: int, y0: int, y1: int) -> np.ndarray:
    plot = rgb[:, x_cut:].astype(np.int16)
    sat = _sat(plot)
    white = plot.min(axis=2) > 235
    keep = (sat > 28) & ~white
    # drop the legend vertical extent copied into the crop, and the scale bar
    keep[: max(0, y0 - 10), :] = False
    out = np.full(plot.shape[:2], np.nan, dtype=np.float32)
    ys, xs = np.where(keep)
    if ys.size == 0:
        return out
    step = max(1, ys.size // 80_000)
    ys, xs = ys[::step], xs[::step]
    pix = plot[ys, xs].astype(np.float32)
    dist = ((pix[:, None, :] - bar[None, :, :]) ** 2).sum(axis=2)
    idx = dist.argmin(axis=1)
    t = idx / max(1, bar.shape[0] - 1)
    vals = vmax + (vmin - vmax) * t
    out[ys, xs] = vals.astype(np.float32)
    return out


def _grid(values: np.ndarray, rows: int = 3, cols: int = 4) -> list[list[float | None]]:
    height, width = values.shape
    grid = []
    for r in range(rows):
        row = []
        y0 = r * height // rows
        y1 = (r + 1) * height // rows
        for c in range(cols):
            x0 = c * width // cols
            x1 = (c + 1) * width // cols
            cell = values[y0:y1, x0:x1]
            good = cell[np.isfinite(cell)]
            row.append(None if good.size < 20 else round(float(good.mean()), 3))
        grid.append(row)
    return grid


def _station(axis: str, field: str, frame: int | None, n_frames: int) -> float | None:
    if frame is None or n_frames < 2:
        return None
    t = (frame - 1) / (n_frames - 1)
    if axis == "x":
        a, b = X_RANGE
    elif axis == "z":
        a, b = Z_RANGE
    elif axis == "y":
        end = Y_END.get(field)
        if end is None:
            return None
        a, b = -0.01, end
    else:
        return None
    return round(a + t * (b - a), 4)


def quantify_image(path: Path, field: str, axis: str, frame: int | None, n_frames: int) -> dict | None:
    scale = SCALE.get(field)
    if scale is None:
        return None
    vmin, vmax = scale
    rgb = np.asarray(Image.open(path).convert("RGB"))
    # work at half resolution; the bar is still dozens of pixels wide
    if rgb.shape[1] > 1000:
        rgb = rgb[::2, ::2]
    found = find_colourbar(rgb)
    if found is None:
        return None
    x, y0, y1 = found
    bar = _bar_colours(rgb, x, y0, y1)
    values = _values(rgb, bar, vmin, vmax, x + 8, y0, y1)
    good = values[np.isfinite(values)]
    if good.size < 50:
        return None
    low = float((good < 0).mean()) if field in {"cp", "cpt"} else float((good <= 0.15 * (vmax - vmin) + vmin).mean())
    return {
        "file": path.name,
        "axis": axis,
        "field": field,
        "frame": frame,
        "stationM": _station(axis, field, frame, n_frames),
        "scale": [vmin, vmax],
        "mean": round(float(good.mean()), 3),
        "p10": round(float(np.percentile(good, 10)), 3),
        "p90": round(float(np.percentile(good, 90)), 3),
        "lowFraction": round(low, 3),
        "grid": _grid(values),
        "note": "Liczby z koloru piksela i legendy na zdjęciu. Siatka 3x4 to góra-dół i lewo-prawo kadru, nie metry na aucie.",
    }


def _axis(path: Path) -> str:
    parts = {p.lower() for p in path.parts}
    for name in ("x", "y", "z"):
        if name in parts:
            return name
    return "full"


def quantify_tree(root: Path) -> dict:
    frames: dict[str, list[dict]] = {}
    skipped = 0
    files = sorted(p for p in root.rglob("*.jpg") if p.is_file())
    grouped: dict[tuple[str, str], list[Path]] = {}
    for path in files:
        field = _field_from_folder(path.parent.name)
        axis = _axis(path)
        grouped.setdefault((axis, field), []).append(path)
    for (axis, field), paths in grouped.items():
        n_frames = 1
        for path in paths:
            match = FRAME_RE.search(path.stem)
            if match:
                n_frames = max(n_frames, int(match.group(1)))
        rows = []
        for path in paths:
            match = FRAME_RE.search(path.stem)
            frame = int(match.group(1)) if match else None
            row = quantify_image(path, field, axis, frame, n_frames)
            if row is None:
                skipped += 1
                continue
            rows.append(row)
        rows.sort(key=lambda item: (item["frame"] is None, item["frame"] or 0))
        frames[f"{axis}/{field}"] = rows
    return {
        "root": str(root),
        "images": sum(len(v) for v in frames.values()),
        "skipped": skipped,
        "whatThisIs": (
            "Kolor piksela przeliczony przez legendę z tego samego zdjęcia. "
            "To trend na klatce, nie Cx z solvera i nie metry kwadratowe."
        ),
        "series": frames,
    }


def write_quant(root: Path, out: Path) -> dict:
    data = quantify_tree(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
