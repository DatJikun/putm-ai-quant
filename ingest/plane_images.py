"""Pictures of the flow drawn from the solver files, at the same planes as CFD-Post.

CFD-Post animations step through 150 planes on each axis. The same planes are cut here from
the cell data (Cp, total-pressure coefficient, velocity relative to the free stream, with the
same colour ranges as `templates/slices.yaml`), plus three views of the wall (Cp, shear and y+).
A small HTML gallery with a slider goes with them, so nothing has to be opened one by one.
Grey is where there are no cells: the car and the ground.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np

AXES = ("x", "y", "z")
# Plot box, the same as the flow scan: the car, not the whole wind tunnel.
BOX = {"x": (-1.6, 3.2), "y": (-1.3, 0.15), "z": (-0.02, 1.6)}
PITCH_M = 0.01
FILL_BINS = 2
DEFAULT_FRAMES = 150
DEFAULT_RANGES = {"x": (-1.1, 2.5), "y": (-0.01, -0.9), "z": (0.0, 1.5)}
FIELDS = {
    "cp": {"label": "Cp (ciśnienie)", "range": (-2.25, 1.0), "cmap": "RdBu_r"},
    "cpt": {"label": "Cpt (ciśnienie całkowite, strata)", "range": (-1.0, 1.0), "cmap": "viridis"},
    "vel": {"label": "V / V∞ (prędkość względna)", "range": (0.0, 2.5), "cmap": "turbo"},
}
SURFACE_FIELDS = {
    "cp": {"label": "Cp na powierzchni", "range": (-2.25, 1.0), "cmap": "RdBu_r"},
    "wss": {"label": "Tarcie przy ścianie [Pa]", "range": (0.0, 3.0), "cmap": "magma"},
    "yplus": {"label": "y+", "range": (0.0, 60.0), "cmap": "viridis"},
}
VIEWS = {
    # name: (horizontal axis, vertical axis, depth axis, nearest is the smaller value?)
    "z-gory": (0, 1, 2, False),
    "z-boku": (0, 2, 1, True),
    "z-przodu": (1, 2, 0, True),
}


# ---------------------------------------------------------------- plane positions

def plane_positions(template: dict | None = None, images_index: dict | None = None) -> dict[str, list[float]]:
    """The 150 planes per axis of the CFD-Post animation. From the picture index when it knows them."""
    out: dict[str, list[float]] = {}
    template = template or {}
    frames = int(template.get("frames") or DEFAULT_FRAMES)
    for axis in AXES:
        spec = template.get(axis) or {}
        start = float(spec.get("startM", DEFAULT_RANGES[axis][0]))
        end = float(spec.get("endM", DEFAULT_RANGES[axis][1]))
        out[axis] = [round(float(v), 4) for v in np.linspace(start, end, frames)]
    if images_index:
        seen: dict[str, set[float]] = {}
        for entry in images_index.get("index", []):
            axis, station = entry.get("axis"), entry.get("stationM")
            if axis in AXES and isinstance(station, (int, float)):
                seen.setdefault(axis, set()).add(round(float(station), 4))
        for axis, values in seen.items():
            if len(values) >= 10:
                out[axis] = sorted(values)
    return out


def _spread(values: list[float], count: int) -> list[float]:
    """`count` values spread evenly over the whole list, first and last included."""
    if count >= len(values):
        return list(values)
    picks = sorted({int(round(i)) for i in np.linspace(0, len(values) - 1, count)})
    return [values[i] for i in picks]


# ------------------------------------------------------------------ plane slicing

class Slicer:
    """Cuts thin slabs out of the cell cloud. Cells are ordered once per axis."""

    def __init__(self, centers: np.ndarray, fields: dict[str, np.ndarray]):
        self.centers = centers
        self.fields = fields
        self._order: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def _sorted(self, ax: int):
        if ax not in self._order:
            order = np.argsort(self.centers[:, ax], kind="stable")
            self._order[ax] = (order, self.centers[order, ax])
        return self._order[ax]

    def slab(self, axis: str, position: float, half: float) -> np.ndarray:
        ax = AXES.index(axis)
        order, values = self._sorted(ax)
        lo, hi = np.searchsorted(values, [position - half, position + half])
        return order[lo:hi]

    def grid(self, axis: str, position: float, half: float, pitch: float = PITCH_M) -> dict[str, np.ndarray]:
        idx = self.slab(axis, position, half)
        h_ax, v_ax = [a for a in range(3) if a != AXES.index(axis)]
        (h0, h1), (v0, v1) = BOX[AXES[h_ax]], BOX[AXES[v_ax]]
        nh, nv = int(np.ceil((h1 - h0) / pitch)), int(np.ceil((v1 - v0) / pitch))
        ih = np.floor((self.centers[idx, h_ax] - h0) / pitch).astype(np.int64)
        iv = np.floor((self.centers[idx, v_ax] - v0) / pitch).astype(np.int64)
        keep = (ih >= 0) & (ih < nh) & (iv >= 0) & (iv < nv)
        flat = ih[keep] * nv + iv[keep]
        counts = np.bincount(flat, minlength=nh * nv).astype(np.float64)
        out = {}
        for name, values in self.fields.items():
            total = np.bincount(flat, weights=values[idx][keep].astype(np.float64), minlength=nh * nv)
            with np.errstate(invalid="ignore", divide="ignore"):
                out[name] = np.where(counts > 0, total / counts, np.nan).reshape(nh, nv)
        out["count"] = counts.reshape(nh, nv)
        return out


def fill_gaps(grid: np.ndarray, bins: int = FILL_BINS, far_bins: int = 8) -> np.ndarray:
    """Fill empty bins, as far as the local spacing of the data allows.

    Where the cells are fine (near the car) at most `bins` away from data is filled, so thin wings
    stay thin. Where they are coarse (the far field) the spacing is larger and so is the reach,
    up to `far_bins`. Bins deep inside a solid have no data around them and stay empty.
    """
    from scipy.ndimage import distance_transform_edt, uniform_filter

    empty = ~np.isfinite(grid)
    if not empty.any() or empty.all():
        return grid
    dist, (iy, iz) = distance_transform_edt(empty, return_indices=True)
    density = uniform_filter((~empty).astype(np.float64), size=9, mode="constant")
    spacing = 1.0 / np.sqrt(np.maximum(density, 1e-3))  # bins between neighbouring data around a point
    reach = np.clip(1.2 * spacing[iy, iz], bins, far_bins)
    out = grid.copy()
    near = empty & (dist <= reach)
    out[near] = grid[iy[near], iz[near]]
    return out


# ---------------------------------------------------------------------- drawing

def _figure(width: float = 6.4, height: float = 4.0):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt.subplots(figsize=(width, height), dpi=80)


def draw_plane(grid: np.ndarray, axis: str, position: float, field: str, path: Path, markers: list[dict] | None = None) -> None:
    """One plane. `grid` is indexed [first, second remaining axis]; the first one runs to the right."""
    import matplotlib.pyplot as plt

    spec = FIELDS[field]
    h_ax, v_ax = [a for a in AXES if a != axis]
    fig, ax = _figure()
    ax.set_facecolor("#d9d9d9")
    image = ax.imshow(
        np.ma.masked_invalid(fill_gaps(grid)).T,
        origin="lower",
        extent=(BOX[h_ax][0], BOX[h_ax][1], BOX[v_ax][0], BOX[v_ax][1]),
        aspect="equal",
        cmap=spec["cmap"],
        vmin=spec["range"][0],
        vmax=spec["range"][1],
        interpolation="nearest",
    )
    ax.set_xlabel(f"{h_ax} [m]")
    ax.set_ylabel(f"{v_ax} [m]")
    ax.set_title(f"{spec['label']}   {axis} = {position:.3f} m", fontsize=10)
    fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02)
    if axis == "x":
        for m in markers or []:
            ax.plot(m["y_m"], m["z_m"], marker="o", mfc="none", mec="k", ms=9, mew=1.4)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def draw_surface(centers: np.ndarray, values: np.ndarray, view: str, field: str, path: Path, pitch: float = 0.004) -> None:
    """Wall values seen from the top, the side or the front. The face nearest to the viewer wins each pixel."""
    import matplotlib.pyplot as plt

    spec = SURFACE_FIELDS[field]
    h_ax, v_ax, depth_ax, nearest_smaller = VIEWS[view]
    names = AXES
    margin = 0.05
    h0, h1 = float(centers[:, h_ax].min()) - margin, float(centers[:, h_ax].max()) + margin
    v0, v1 = float(centers[:, v_ax].min()) - margin, float(centers[:, v_ax].max()) + margin
    nh, nv = int(np.ceil((h1 - h0) / pitch)), int(np.ceil((v1 - v0) / pitch))
    ih = np.floor((centers[:, h_ax] - h0) / pitch).astype(np.int64)
    iv = np.floor((centers[:, v_ax] - v0) / pitch).astype(np.int64)
    keep = (ih >= 0) & (ih < nh) & (iv >= 0) & (iv < nv)
    depth = centers[keep, depth_ax]
    order = np.argsort(-depth if nearest_smaller else depth, kind="stable")  # the nearest is written last
    img = np.full((nh, nv), np.nan)
    img[ih[keep][order], iv[keep][order]] = values[keep][order]
    fig, ax = _figure(7.2, 4.2)
    ax.set_facecolor("#d9d9d9")
    shown = ax.imshow(
        np.ma.masked_invalid(img.T),
        origin="lower",
        extent=(h0, h1, v0, v1),
        aspect="equal",
        cmap=spec["cmap"],
        vmin=spec["range"][0],
        vmax=spec["range"][1],
        interpolation="nearest",
    )
    ax.set_xlabel(f"{names[h_ax]} [m]")
    ax.set_ylabel(f"{names[v_ax]} [m]")
    ax.set_title(f"{spec['label']}, widok {view.replace('z-', 'z ')}", fontsize=10)
    fig.colorbar(shown, ax=ax, fraction=0.03, pad=0.02)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------- gallery

GALLERY = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>Przekroje przepływu</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#f4f4f2;color:#1c1c1c}
header{padding:12px 18px;background:#fff;border-bottom:1px solid #ddd}
h1{font-size:18px;margin:0 0 4px} p{margin:2px 0;color:#555;font-size:13px}
main{display:flex;gap:16px;padding:16px;flex-wrap:wrap;align-items:flex-start}
.controls{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;min-width:260px}
label{display:block;font-size:13px;margin:8px 0 3px;color:#444}
select,input[type=range]{width:100%}
img{max-width:100%;background:#fff;border:1px solid #ddd;border-radius:8px}
.view{flex:1;min-width:320px}
button{margin:2px;padding:4px 9px}
.surf img{width:48%;min-width:300px}
</style></head><body>
<header><h1>__TITLE__</h1><p>Te same płaszczyzny co w animacjach CFD-Post, rysowane z plików wyników. Szary obszar to miejsca bez komórek (bolid i podłoże).</p></header>
<main>
<div class="controls">
<label>Oś przekroju</label><select id="axis"></select>
<label>Pole</label><select id="field"></select>
<label>Pozycja: <b id="pos"></b> m</label><input id="slider" type="range" min="0" max="0" value="0">
<div><button id="prev">&larr;</button><button id="next">&rarr;</button><button id="play">&#9654; odtwórz</button></div>
</div>
<div class="view"><img id="img" alt="przekrój"><p id="cap"></p></div>
</main>
<main class="surf"><div id="surf"></div></main>
<script>
const DATA = __DATA__;
const axis = document.getElementById('axis'), field = document.getElementById('field'), slider = document.getElementById('slider');
const img = document.getElementById('img'), pos = document.getElementById('pos'), cap = document.getElementById('cap');
for (const a of Object.keys(DATA.planes)) axis.add(new Option('x = const'.replace('x', a), a));
for (const [k, v] of Object.entries(DATA.fields)) field.add(new Option(v, k));
function refresh(){
  const list = DATA.planes[axis.value]; slider.max = list.length - 1;
  const i = Math.min(+slider.value, list.length - 1), p = list[i];
  pos.textContent = p.toFixed(3);
  img.src = 'przekroje/' + axis.value + '/' + field.value + '/' + axis.value + '_' + p.toFixed(3) + '.png';
  cap.textContent = 'Płaszczyzna ' + axis.value + ' = ' + p.toFixed(3) + ' m, klatka ' + (i + 1) + ' z ' + list.length;
}
axis.onchange = () => { slider.value = 0; refresh(); }; field.onchange = refresh; slider.oninput = refresh;
document.getElementById('prev').onclick = () => { slider.value = Math.max(0, +slider.value - 1); refresh(); };
document.getElementById('next').onclick = () => { slider.value = Math.min(+slider.max, +slider.value + 1); refresh(); };
let timer = null;
document.getElementById('play').onclick = () => {
  if (timer) { clearInterval(timer); timer = null; return; }
  timer = setInterval(() => { slider.value = (+slider.value + 1) % (+slider.max + 1); refresh(); }, 150);
};
const surf = document.getElementById('surf');
for (const s of DATA.surface) { const im = document.createElement('img'); im.src = 'powierzchnia/' + s; im.alt = s; surf.appendChild(im); }
refresh();
</script></body></html>
"""


def write_gallery(out_dir: Path, planes: dict[str, list[float]], fields: dict[str, str], surface_files: list[str], title: str) -> Path:
    data = {"planes": planes, "fields": fields, "surface": surface_files}
    page = GALLERY.replace("__TITLE__", html.escape(title)).replace("__DATA__", json.dumps(data, ensure_ascii=False))
    dest = out_dir / "galeria.html"
    dest.write_text(page, encoding="utf-8")
    return dest


# ------------------------------------------------------------------------- main

def render_all(
    case: Path,
    out_dir: Path,
    *,
    rho: float,
    mu: float,
    speed_ms: float,
    template: dict | None = None,
    images_index: dict | None = None,
    cache_dir: Path | None = None,
    surface: bool = True,
    axes: tuple[str, ...] = AXES,
    limit: int | None = None,
    title: str = "Przekroje przepływu",
) -> dict:
    """Render every plane of every axis and field, the wall views, and the gallery page."""
    import h5py

    from ingest.flow_field import cell_centers

    cas = next(case.rglob("*.cas.h5"))
    dat = next(case.rglob("*.dat.h5"))
    centers = cell_centers(cas, None if cache_dir is None else cache_dir / "cell_centers.npy")
    q = 0.5 * rho * speed_ms**2
    with h5py.File(dat, "r") as data:
        cells = data["results/1/phase-1/cells"]
        p = np.asarray(cells["SV_P/1"][:], dtype=np.float32)
        u = np.asarray(cells["SV_U/1"][:], dtype=np.float32)
        v = np.asarray(cells["SV_V/1"][:], dtype=np.float32)
        w = np.asarray(cells["SV_W/1"][:], dtype=np.float32)
    speed2 = u * u + v * v + w * w
    fields = {"cp": p / q, "cpt": (p + 0.5 * rho * speed2) / q, "vel": np.sqrt(speed2) / speed_ms}
    del p, u, v, w, speed2
    slicer = Slicer(centers, fields)
    positions = plane_positions(template, images_index)
    if limit:
        positions = {a: _spread(positions[a], limit) for a in axes}
    positions = {a: positions[a] for a in axes}
    written = 0
    for axis in axes:
        positions_axis = positions[axis]
        step = float(np.median(np.abs(np.diff(positions_axis)))) if len(positions_axis) > 1 else 0.02
        half = max(step / 2.0, 0.006)
        for pos in positions_axis:
            grid = slicer.grid(axis, pos, half)
            for field in FIELDS:
                draw_plane(grid[field], axis, pos, field, out_dir / "przekroje" / axis / field / f"{axis}_{pos:.3f}.png")
                written += 1
    surface_files = render_surface_views(case, out_dir, rho=rho, mu=mu, speed_ms=speed_ms) if surface else []
    gallery = write_gallery(out_dir, positions, {k: v["label"] for k, v in FIELDS.items()}, surface_files, title)
    index = {"planes": {a: len(positions[a]) for a in axes}, "positions": positions, "fields": list(FIELDS), "surface": surface_files, "images": written + len(surface_files), "gallery": gallery.name}
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return index


def render_surface_views(case: Path, out_dir: Path, *, rho: float, mu: float, speed_ms: float) -> list[str]:
    """Cp, wall shear and y+ on the car, from the top, the side and the front."""
    import h5py

    from ingest.wall_forces import group_for
    from ingest.wall_state import checked_layout, wall_state

    cas = next(case.rglob("*.cas.h5"))
    dat = next(case.rglob("*.dat.h5"))
    q = 0.5 * rho * speed_ms**2
    centers, values = [], {"cp": [], "wss": [], "yplus": []}
    with h5py.File(cas, "r") as mesh, h5py.File(dat, "r") as data:
        for name, packed_at, a, b in checked_layout(mesh, data):
            if group_for(name) is None:
                continue
            state = wall_state(mesh, data, packed_at, a, b, rho=rho, mu=mu)
            centers.append(state["centers"])
            values["cp"].append(state["pressure"] / q)
            values["wss"].append(np.linalg.norm(state["tau"], axis=1))
            values["yplus"].append(state["yplus"])
    xyz = np.concatenate(centers)
    files = []
    for field in SURFACE_FIELDS:
        merged = np.concatenate(values[field])
        for view in VIEWS:
            name = f"{field}_{view}.png"
            draw_surface(xyz, merged, view, field, out_dir / "powierzchnia" / name)
            files.append(name)
    return files
