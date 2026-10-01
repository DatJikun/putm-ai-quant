"""The flow around the car as numbers, station by station, instead of a thousand pictures.

For every plane across the car (x = const) the solver cells that touch it are binned
on a regular grid. From that grid come:

* loss of total pressure (Cpt = (p + rho |U|^2 / 2) / q, equal to 1 in the free stream),
  its area and integral, which show where the air loses energy;
* vortices, found with the swirling strength of the in-plane velocity gradient. Unlike
  vorticity it is zero in plain shear, so the boundary layers on the walls are not
  reported as vortices. Each one gets position, circulation, core size and swirl speed;
* regions of reversed flow (u < 0 in the car frame);
* vortex tracks, i.e. the same vortex followed from station to station.

Cell centres are not stored in the solver files. They are rebuilt once from the face
centres of every cell and cached next to the output.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ingest.h5_mesh import iter_face_chunks

BOX_Y = (-1.3, 0.15)
BOX_Z = (-0.02, 1.6)
PITCH_M = 0.02
HALF_THICKNESS_M = 0.015
STATION_STEP_M = 0.1
STATION_RANGE_M = (-1.2, 2.8)
SWIRL_THRESHOLD = 0.08  # of U_inf / pitch
MIN_CLUSTER_CELLS = 3
MAX_VORTICES = 8
LOSS_CPT = 0.9
REVERSE_U_FRACTION = -0.05
TRACK_LINK_M = 0.12


# ------------------------------------------------------------------ cell centres

def cell_centers(cas_path: Path, cache: Path | None = None, chunk_faces: int = 2_000_000) -> np.ndarray:
    """Cell centres (n, 3) as the mean of the centres of the cell's faces. Cached as .npy."""
    import h5py

    if cache is not None and cache.exists():
        return np.load(cache)
    with h5py.File(cas_path, "r") as mesh:
        c0, c1 = mesh["meshes/1/faces/c0"], mesh["meshes/1/faces/c1"]
        n_cells = int(max(max(int(c0[k][:].max()) for k in c0), max(int(c1[k][:].max()) for k in c1)))
        acc = np.zeros((n_cells, 3), dtype=np.float64)
        cnt = np.zeros(n_cells, dtype=np.float64)
        for _, _, _, centre, first, face_idx, second in iter_face_chunks(mesh, chunk_faces):
            for owner, source in ((first, centre), (second, centre[face_idx])):
                keep = owner > 0
                ids = owner[keep] - 1
                for dim in range(3):
                    acc[:, dim] += np.bincount(ids, weights=source[keep, dim], minlength=n_cells)
                cnt += np.bincount(ids, minlength=n_cells)
    out = (acc / np.maximum(cnt, 1)[:, None]).astype(np.float32)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache, out)
    return out


# ------------------------------------------------------------------- plane grids

def grid_shape(pitch: float = PITCH_M) -> tuple[int, int]:
    return (
        int(np.ceil((BOX_Y[1] - BOX_Y[0]) / pitch)),
        int(np.ceil((BOX_Z[1] - BOX_Z[0]) / pitch)),
    )


def bin_plane(y: np.ndarray, z: np.ndarray, fields: dict[str, np.ndarray], pitch: float = PITCH_M) -> dict[str, np.ndarray]:
    """Mean of every field per grid bin, NaN where no cell fell. Axes are [y, z]."""
    ny, nz = grid_shape(pitch)
    iy = np.floor((y - BOX_Y[0]) / pitch).astype(np.int64)
    iz = np.floor((z - BOX_Z[0]) / pitch).astype(np.int64)
    keep = (iy >= 0) & (iy < ny) & (iz >= 0) & (iz < nz)
    flat = iy[keep] * nz + iz[keep]
    counts = np.bincount(flat, minlength=ny * nz).astype(np.float64)
    out = {}
    for name, values in fields.items():
        total = np.bincount(flat, weights=values[keep].astype(np.float64), minlength=ny * nz)
        with np.errstate(invalid="ignore", divide="ignore"):
            grid = np.where(counts > 0, total / counts, np.nan)
        out[name] = grid.reshape(ny, nz)
    out["count"] = counts.reshape(ny, nz)
    return out


def _smooth(grid: np.ndarray, size: int = 3) -> np.ndarray:
    """Box filter that ignores empty bins, so the air next to a wall is not mixed with nothing."""
    from scipy.ndimage import uniform_filter

    mask = np.isfinite(grid)
    filled = np.where(mask, grid, 0.0)
    num = uniform_filter(filled, size=size, mode="constant")
    den = uniform_filter(mask.astype(np.float64), size=size, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, num / den, np.nan)
    out[~mask] = np.nan
    return out


def swirl_fields(v: np.ndarray, w: np.ndarray, pitch: float = PITCH_M) -> tuple[np.ndarray, np.ndarray]:
    """Swirling strength and streamwise vorticity of the in-plane velocity (v, w) on a [y, z] grid."""
    v, w = _smooth(v), _smooth(w)
    dv_dy, dv_dz = np.gradient(v, pitch, axis=0), np.gradient(v, pitch, axis=1)
    dw_dy, dw_dz = np.gradient(w, pitch, axis=0), np.gradient(w, pitch, axis=1)
    disc = ((dv_dy - dw_dz) / 2.0) ** 2 + dv_dz * dw_dy
    with np.errstate(invalid="ignore"):
        swirl = np.where(disc < 0, np.sqrt(-disc), 0.0)
    omega = dw_dy - dv_dz
    swirl[~np.isfinite(swirl)] = 0.0
    return swirl, omega


def find_vortices(swirl, omega, cpt, pitch: float, speed_ms: float, *, threshold: float = SWIRL_THRESHOLD, limit: int = MAX_VORTICES) -> list[dict]:
    """Compact clusters of strong swirl, strongest circulation first."""
    from scipy.ndimage import label

    thr = threshold * speed_ms / pitch
    mask = swirl > thr
    labels, count = label(mask, structure=np.ones((3, 3), dtype=int))
    vortices = []
    for idx in range(1, count + 1):
        cells = np.argwhere(labels == idx)
        if cells.shape[0] < MIN_CLUSTER_CELLS:
            continue
        iy, iz = cells[:, 0], cells[:, 1]
        h = iy.max() - iy.min() + 1
        wdt = iz.max() - iz.min() + 1
        if cells.shape[0] / float(h * wdt) < 0.4 or max(h, wdt) > 4 * min(h, wdt):
            continue  # a thin strip along a wall is shear, not a vortex
        weights = swirl[iy, iz]
        gamma = float(np.nansum(omega[iy, iz]) * pitch**2)
        area = cells.shape[0] * pitch**2
        radius = float(np.sqrt(area / np.pi))
        local_cpt = cpt[iy, iz]
        vortices.append(
            {
                "y_m": round(float(BOX_Y[0] + (np.average(iy, weights=weights) + 0.5) * pitch), 3),
                "z_m": round(float(BOX_Z[0] + (np.average(iz, weights=weights) + 0.5) * pitch), 3),
                "circulationM2s": round(gamma, 4),
                "turn": "przeciwnie do ruchu wskazówek (patrząc z przodu)" if gamma > 0 else "zgodnie z ruchem wskazówek (patrząc z przodu)",
                "swirlPeakPerS": round(float(weights.max()), 1),
                "coreRadiusM": round(radius, 3),
                "swirlSpeedMs": round(abs(gamma) / (2 * np.pi * radius), 2) if radius > 0 else None,
                "minCpt": None if not np.isfinite(local_cpt).any() else round(float(np.nanmin(local_cpt)), 3),
            }
        )
    vortices.sort(key=lambda v: -abs(v["circulationM2s"]))
    return vortices[:limit]


def link_tracks(stations: list[dict], max_jump_m: float = TRACK_LINK_M) -> list[dict]:
    """Follow the same vortex (same turning direction, close in y and z) from station to station."""
    tracks: list[dict] = []
    open_tracks: list[dict] = []
    for station in stations:
        taken = set()
        next_open = []
        for vortex in station["vortices"]:
            sign = vortex["circulationM2s"] > 0
            best, best_d = None, max_jump_m
            for t in open_tracks:
                if id(t) in taken or t["sign"] != sign:
                    continue
                last = t["points"][-1]
                d = float(np.hypot(vortex["y_m"] - last["y_m"], vortex["z_m"] - last["z_m"]))
                if d < best_d:
                    best, best_d = t, d
            point = {"x_m": station["x_m"], "y_m": vortex["y_m"], "z_m": vortex["z_m"], "circulationM2s": vortex["circulationM2s"], "minCpt": vortex["minCpt"]}
            if best is None:
                best = {"sign": sign, "points": []}
                tracks.append(best)
            best["points"].append(point)
            taken.add(id(best))
            next_open.append(best)
        open_tracks = next_open
    out = []
    for t in tracks:
        pts = t["points"]
        if len(pts) < 2:
            continue
        strongest = max(pts, key=lambda p: abs(p["circulationM2s"]))
        out.append(
            {
                "turn": "przeciwnie do ruchu wskazówek" if t["sign"] else "zgodnie z ruchem wskazówek",
                "fromX_m": pts[0]["x_m"],
                "toX_m": pts[-1]["x_m"],
                "start": {"y_m": pts[0]["y_m"], "z_m": pts[0]["z_m"]},
                "end": {"y_m": pts[-1]["y_m"], "z_m": pts[-1]["z_m"]},
                "strongestAtX_m": strongest["x_m"],
                "peakCirculationM2s": strongest["circulationM2s"],
                "points": pts,
            }
        )
    out.sort(key=lambda t: -abs(t["peakCirculationM2s"]))
    return out


def window_loss(cpt: np.ndarray, y_range: tuple[float, float], z_max: float, pitch: float = PITCH_M) -> dict:
    """Loss of total pressure inside a window of the plane, and how wide the lossy air is."""
    ny, nz = cpt.shape
    y = BOX_Y[0] + (np.arange(ny) + 0.5) * pitch
    z = BOX_Z[0] + (np.arange(nz) + 0.5) * pitch
    inside = (y[:, None] >= y_range[0]) & (y[:, None] <= y_range[1]) & (z[None, :] <= z_max)
    valid = inside & np.isfinite(cpt)
    if not valid.any():
        return {"lossAreaM2": 0.0, "lossIntegralM2": 0.0, "minCpt": None, "widthM": 0.0}
    lossy = valid & (cpt < LOSS_CPT)
    loss = np.where(valid, np.clip(1.0 - np.nan_to_num(cpt, nan=1.0), 0.0, None), 0.0)
    rows = np.flatnonzero(lossy.any(axis=1))
    return {
        "lossAreaM2": round(float(lossy.sum() * pitch**2), 4),
        "lossIntegralM2": round(float(loss.sum() * pitch**2), 4),
        "minCpt": round(float(np.nanmin(np.where(valid, cpt, np.nan))), 3),
        "widthM": round(float((rows.max() - rows.min() + 1) * pitch), 3) if rows.size else 0.0,
    }


WHEEL_WINDOW_HALF_WIDTH_M = 0.35
WHEEL_WINDOW_HEIGHT_M = 0.6


def wheel_windows(cpt: np.ndarray, x: float, wheels: dict | None, pitch: float = PITCH_M) -> dict:
    """Loss in the window behind each wheel. The front wheel is followed only up to the rear axle."""
    out = {}
    rear = ((wheels or {}).get("rear") or {}).get("originM")
    for name in ("front", "rear"):
        origin = ((wheels or {}).get(name) or {}).get("originM")
        if not origin or x < origin[0] + 0.1:
            continue
        if name == "front" and rear and x > rear[0] - 0.1:
            continue  # the rear wheel sits in the same lane, so the loss there is no longer the front wheel's
        out[name] = window_loss(cpt, (origin[1] - WHEEL_WINDOW_HALF_WIDTH_M, origin[1] + WHEEL_WINDOW_HALF_WIDTH_M), WHEEL_WINDOW_HEIGHT_M, pitch)
    return out


def tag_region(x: float, y: float, z: float, wheels: dict | None = None) -> str:
    """A rough label for where a vortex sits, from the wheel positions of the case."""
    wheels = wheels or {}
    fx = (wheels.get("front") or {}).get("originM") or [0.0, -0.7, 0.206]
    rx = (wheels.get("rear") or {}).get("originM") or [1.53, -0.7, 0.206]
    radius = 0.23
    near_y = lambda w: abs(y - w[1]) < 0.3
    if z < 0.15:
        return "pod podłogą lub przy ziemi (wiry krawędzi podłogi, dyfuzor)"
    if near_y(fx) and z < 2.0 * radius and fx[0] - 0.1 <= x <= fx[0] + 1.2:
        return "ślad za kołem przednim"
    if near_y(rx) and z < 2.0 * radius and x >= rx[0] - 0.1:
        return "ślad za kołem tylnym"
    if x < fx[0] + 0.1:
        return "przed przednią osią (przednie skrzydło, jego końcówki)"
    if x > rx[0] and z > 0.45:
        return "za tylną osią, wysoko (tylne skrzydło, jego końcówki)"
    if z > 0.45:
        return "nad bolidem (kokpit, hoop, nadwozie)"
    return "przy nadwoziu, między osiami"


# -------------------------------------------------------------------- the scan

def station_list(start: float = STATION_RANGE_M[0], stop: float = STATION_RANGE_M[1], step: float = STATION_STEP_M) -> list[float]:
    return [round(float(v), 3) for v in np.arange(start, stop + 1e-9, step)]


def scan_stations(
    case: Path,
    *,
    rho: float,
    speed_ms: float,
    wheels: dict | None = None,
    stations: list[float] | None = None,
    cache_dir: Path | None = None,
    pitch: float = PITCH_M,
) -> dict:
    import h5py

    cas = next(case.rglob("*.cas.h5"))
    dat = next(case.rglob("*.dat.h5"))
    centers = cell_centers(cas, None if cache_dir is None else cache_dir / "cell_centers.npy")
    q = 0.5 * rho * speed_ms**2
    with h5py.File(dat, "r") as data:
        cells = data["results/1/phase-1/cells"]
        pressure = np.asarray(cells["SV_P/1"][:], dtype=np.float32)
        u = np.asarray(cells["SV_U/1"][:], dtype=np.float32)
        v = np.asarray(cells["SV_V/1"][:], dtype=np.float32)
        w = np.asarray(cells["SV_W/1"][:], dtype=np.float32)
    if centers.shape[0] != pressure.shape[0]:
        raise RuntimeError(f"komórek w siatce {centers.shape[0]}, w polu {pressure.shape[0]}")
    cpt_all = (pressure + 0.5 * rho * (u * u + v * v + w * w)) / q
    in_box = (centers[:, 1] >= BOX_Y[0]) & (centers[:, 1] <= BOX_Y[1]) & (centers[:, 2] >= BOX_Z[0]) & (centers[:, 2] <= BOX_Z[1])
    out_stations = []
    for x in stations or station_list():
        sel = np.flatnonzero(in_box & (np.abs(centers[:, 0] - x) <= HALF_THICKNESS_M))
        if sel.size < 50:
            out_stations.append({"x_m": x, "cells": int(sel.size), "vortices": [], "note": "za mało komórek"})
            continue
        grid = bin_plane(centers[sel, 1], centers[sel, 2], {"u": u[sel], "v": v[sel], "w": w[sel], "cpt": cpt_all[sel]}, pitch)
        swirl, omega = swirl_fields(grid["v"], grid["w"], pitch)
        cpt = grid["cpt"]
        valid = np.isfinite(cpt)
        loss = np.where(valid, np.clip(1.0 - cpt, 0.0, None), 0.0)
        lossy = valid & (cpt < LOSS_CPT)
        rev = np.isfinite(grid["u"]) & (grid["u"] < REVERSE_U_FRACTION * speed_ms)
        vortices = find_vortices(swirl, omega, cpt, pitch, speed_ms)
        for item in vortices:
            item["region"] = tag_region(x, item["y_m"], item["z_m"], wheels)
        out_stations.append(
            {
                "x_m": x,
                "cells": int(sel.size),
                "binsFilled": int(valid.sum()),
                "lossIntegralM2": round(float(loss.sum() * pitch**2), 4),
                "lossAreaM2": round(float(lossy.sum() * pitch**2), 4),
                "minCpt": None if not valid.any() else round(float(np.nanmin(cpt)), 3),
                "reverseFlowAreaM2": round(float(rev.sum() * pitch**2), 4),
                "minU_ms": None if not np.isfinite(grid["u"]).any() else round(float(np.nanmin(grid["u"])), 2),
                "wheels": wheel_windows(cpt, x, wheels, pitch),
                "vortices": vortices,
            }
        )
    tracks = link_tracks([s for s in out_stations if s["vortices"]])
    for track in tracks:
        mid = track["points"][len(track["points"]) // 2]
        track["region"] = tag_region(track["fromX_m"], track["start"]["y_m"], track["start"]["z_m"], wheels)
        track["points"] = [{k: p[k] for k in ("x_m", "y_m", "z_m", "circulationM2s")} for p in track["points"]]
    return {
        "opis": (
            "Skan płaszczyzn w poprzek auta. Każda stacja to średnia z komórek solvera w pasie grubości "
            f"{2 * HALF_THICKNESS_M * 1000:.0f} mm, na siatce {pitch * 1000:.0f} mm. x rośnie do tyłu, y w bok (ujemne to połowa z symulacji). "
            "Cpt to ciśnienie całkowite podzielone przez ciśnienie dynamiczne: 1 w czystym powietrzu, mniej tam, gdzie powietrze straciło energię."
        ),
        "speedMs": speed_ms,
        "pitchM": pitch,
        "stations": out_stations,
        "vortexTracks": tracks,
    }


def write_stations(case: Path, out: Path, **kwargs) -> dict:
    data = scan_stations(case, cache_dir=out.parent / ".cache", **kwargs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
