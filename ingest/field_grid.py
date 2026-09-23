"""Coarse plane of a solver field. Cells that touch a thin slab are averaged into bins."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# Clip to the car, not the whole wind tunnel.
BOX = {"x": (-1.6, 3.2), "y": (-1.3, 0.15), "z": (-0.5, 1.6)}
Q = 0.5 * 1.225 * 15.0 ** 2


def bin_means(y: np.ndarray, z: np.ndarray, values: np.ndarray, pitch: float) -> dict:
    if values.size == 0:
        return {"origin": {"y": 0.0, "z": 0.0}, "pitchM": pitch, "rows": [], "cols": []}
    y0 = np.floor(y.min() / pitch) * pitch
    z0 = np.floor(z.min() / pitch) * pitch
    iy = np.floor((y - y0) / pitch).astype(np.int32)
    iz = np.floor((z - z0) / pitch).astype(np.int32)
    ny = int(iy.max()) + 1
    nz = int(iz.max()) + 1
    acc = np.zeros((ny, nz), dtype=np.float64)
    cnt = np.zeros((ny, nz), dtype=np.int32)
    np.add.at(acc, (iy, iz), values)
    np.add.at(cnt, (iy, iz), 1)
    grid = np.full((ny, nz), np.nan, dtype=np.float64)
    mask = cnt > 0
    grid[mask] = acc[mask] / cnt[mask]
    rows = []
    for row in grid:
        rows.append([None if not np.isfinite(v) else round(float(v), 4) for v in row])
    return {
        "origin": {"y": round(float(y0), 4), "z": round(float(z0), 4)},
        "pitchM": pitch,
        "ny": ny,
        "nz": nz,
        "rows": rows,
    }


def slice_grid(
    case: Path,
    *,
    axis: str = "x",
    station: float = 0.0,
    quantity: str = "cp",
    pitch: float = 0.025,
    half_thickness: float = 0.012,
) -> dict:
    import h5py

    axis = axis.lower()
    quantity = quantity.lower()
    if axis not in BOX:
        raise ValueError("oś to x, y albo z")
    cas = next(case.rglob("*.cas.h5"))
    dat = next(case.rglob("*.dat.h5"))
    ax = "xyz".index(axis)

    with h5py.File(cas, "r") as mesh, h5py.File(dat, "r") as data:
        coords = mesh["meshes/1/nodes/coords/55702"]
        n_nodes = int(coords.shape[0])
        near = np.zeros(n_nodes + 1, dtype=bool)
        step = 2_000_000
        for start in range(0, n_nodes, step):
            block = coords[start : start + step]
            ids = np.arange(start + 1, start + 1 + block.shape[0])
            keep = np.abs(block[:, ax] - station) <= half_thickness
            for dim, name in enumerate("xyz"):
                if name == axis:
                    continue
                lo, hi = BOX[name]
                keep &= (block[:, dim] >= lo) & (block[:, dim] <= hi)
            near[ids[keep]] = True

        nn = mesh["meshes/1/faces/nodes/1/nnodes"]
        nodes = mesh["meshes/1/faces/nodes/1/nodes"]
        owners = mesh["meshes/1/faces/c0/1"]
        n_faces = int(nn.shape[0])
        cursor = 0
        cell_ids: list[np.ndarray] = []
        cell_y: list[np.ndarray] = []
        cell_z: list[np.ndarray] = []
        other = [i for i in range(3) if i != ax]
        chunk = 400_000
        for start in range(0, n_faces, chunk):
            stop = min(n_faces, start + chunk)
            counts = nn[start:stop].astype(np.int64)
            total = int(counts.sum())
            fnodes = nodes[cursor : cursor + total]
            own = owners[start:stop]
            cursor += total
            inside = near[fnodes]
            starts = np.zeros(counts.size, dtype=np.int64)
            if counts.size > 1:
                starts[1:] = np.cumsum(counts[:-1])
            touched = np.add.reduceat(inside.astype(np.uint8), starts) > 0
            if not np.any(touched):
                continue
            face_of_node = np.repeat(np.arange(counts.size, dtype=np.int32), counts)
            chosen = np.flatnonzero(inside)
            sel_faces = face_of_node[chosen]
            sel_nodes = fnodes[chosen].astype(np.int64)
            ok = sel_nodes >= 1
            sel_faces = sel_faces[ok]
            sel_nodes = sel_nodes[ok]
            uniq_nodes, inv = np.unique(sel_nodes, return_inverse=True)
            pts = np.asarray(coords[uniq_nodes - 1])[inv]
            order = np.argsort(sel_faces, kind="stable")
            sel_faces = sel_faces[order]
            pts = pts[order]
            first = np.r_[0, np.flatnonzero(np.diff(sel_faces)) + 1]
            y_face = np.add.reduceat(pts[:, other[0]], first) / np.diff(np.r_[first, sel_faces.size])
            z_face = np.add.reduceat(pts[:, other[1]], first) / np.diff(np.r_[first, sel_faces.size])
            face_ids = sel_faces[first]
            cell_ids.append(own[face_ids].astype(np.int64))
            cell_y.append(y_face)
            cell_z.append(z_face)

        if not cell_ids:
            raise RuntimeError("płaszczyzna nie trafiła w siatkę")
        cid = np.concatenate(cell_ids)
        yy = np.concatenate(cell_y)
        zz = np.concatenate(cell_z)
        n_cells = int(data["results/1/phase-1/cells/SV_P/1"].shape[0])
        if int(cid.max()) >= n_cells:
            cid = cid - 1
        keep = (cid >= 0) & (cid < n_cells)
        cid, yy, zz = cid[keep], yy[keep], zz[keep]
        order = np.argsort(cid)
        cid, yy, zz = cid[order], yy[order], zz[order]
        uniq, starts_u = np.unique(cid, return_index=True)
        ends = np.r_[starts_u[1:], cid.size]
        y_mean = np.add.reduceat(yy, starts_u) / (ends - starts_u)
        z_mean = np.add.reduceat(zz, starts_u) / (ends - starts_u)

        base = "results/1/phase-1/cells"
        def col(name: str) -> np.ndarray:
            return data[f"{base}/{name}/1"][uniq]

        if quantity == "cp":
            values = col("SV_P") / Q
        elif quantity == "p":
            values = col("SV_P")
        elif quantity == "u":
            values = col("SV_U")
        elif quantity == "v":
            values = col("SV_V")
        elif quantity == "w":
            values = col("SV_W")
        elif quantity == "speed":
            values = np.hypot(np.hypot(col("SV_U"), col("SV_V")), col("SV_W"))
        else:
            raise ValueError("parametr: cp, p, u, v, w, speed")

    grid = bin_means(y_mean, z_mean, values.astype(np.float64), pitch)
    across = [n for n in "xyz" if n != axis]
    grid.update(
        {
            "quantity": quantity,
            "axis": axis,
            "stationM": station,
            "halfThicknessM": half_thickness,
            "cells": int(uniq.size),
            "across": across,
            "note": (
                "Średnia z komórek, które dotykają tej płaszczyzny. "
                "Kierunki w siatce to dwie osie prostopadłe do cięcia, w metrach. "
                "To nie jest całka z CFD-Post i nie jest odczyt z kolorów."
            ),
        }
    )
    return grid


def write_grid(case: Path, out: Path, **kwargs) -> dict:
    data = slice_grid(case, **kwargs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
