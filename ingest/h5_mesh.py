"""Low-level readers for the mesh part of a Fluent .cas.h5."""

from __future__ import annotations

import numpy as np


def node_coords(mesh):
    """Node coordinates. The dataset is named after a Fluent id that differs per mesh."""
    group = mesh["meshes/1/nodes/coords"]
    return group[next(iter(group))]


def text_of(raw) -> str:
    item = raw if isinstance(raw, bytes) else raw.ravel()[0]
    return item.decode()


def face_ranges(mesh) -> list[tuple[str, int, int]]:
    """Wall zones as (name, first face id, last face id). The tunnel roof is left out."""
    top = mesh["meshes/1/faces/zoneTopology"]
    names = text_of(top["name"][()]).split(";")
    types = top["zoneType"][()]
    lo = top["minId"][()]
    hi = top["maxId"][()]
    walls = []
    for name, kind, a, b in zip(names, types, lo, hi):
        if int(kind) != 3 or name == "domain_sky":
            continue
        walls.append((name, int(a), int(b)))
    return walls


def node_cursor(nnodes, face_index: int) -> int:
    """Offset into the flat node list of the first node of face `face_index` (0-based)."""
    cursor = 0
    pos = 0
    while pos < face_index:
        take = min(2_000_000, face_index - pos)
        cursor += int(nnodes[pos : pos + take].astype(np.int64).sum())
        pos += take
    return cursor


SYMMETRY_ZONE = 7
INTERIOR_ZONE = 2


def zone_types(mesh) -> list[tuple[str, int, int, int]]:
    """(name, type code, first face id, last face id) of every face zone."""
    top = mesh["meshes/1/faces/zoneTopology"]
    names = text_of(top["name"][()]).split(";")
    return [
        (name, int(kind), int(lo), int(hi))
        for name, kind, lo, hi in zip(names, top["zoneType"][()], top["minId"][()], top["maxId"][()])
    ]


def has_symmetry(mesh) -> bool:
    """A symmetry plane in the mesh means only half of the car was solved."""
    return any(kind == SYMMETRY_ZONE and hi >= lo for _, kind, lo, hi in zone_types(mesh))


def read_split(group, start: int, stop: int) -> np.ndarray:
    """Slice [start, stop) of a dataset that Fluent may split into numbered pieces ('1', '2', ...)."""
    out = []
    offset = 0
    for key in sorted(group, key=int):
        part = group[key]
        n = int(part.shape[0])
        lo, hi = max(start, offset), min(stop, offset + n)
        if lo < hi:
            out.append(part[lo - offset : hi - offset])
        offset += n
        if offset >= stop:
            break
    return np.concatenate(out) if out else np.zeros(0, dtype=np.uint32)


def interior_runs(mesh) -> list[tuple[int, int, int]]:
    """(first face, one past the last face, offset in the c1 list) of every interior zone, 0-based.

    Only interior faces have a second cell, so Fluent stores c1 for them alone, zone after zone.
    """
    zones = sorted((lo, hi, kind) for _, kind, lo, hi in zone_types(mesh))
    runs, offset = [], 0
    for lo, hi, kind in zones:
        if kind != INTERIOR_ZONE:
            continue
        runs.append((lo - 1, hi, offset))
        offset += hi - lo + 1
    return runs


def second_cells(c1, runs, start: int, stop: int) -> tuple[np.ndarray, np.ndarray]:
    """Face indices (within [start, stop)) and second-cell ids of the interior faces in the slice."""
    idx, cells = [], []
    for lo, hi, offset in runs:
        a, b = max(lo, start), min(hi, stop)
        if a >= b:
            continue
        idx.append(np.arange(a - start, b - start))
        cells.append(read_split(c1, offset + (a - lo), offset + (b - lo)).astype(np.int64))
    if not idx:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    return np.concatenate(idx), np.concatenate(cells)


def fan_area(pts: np.ndarray, starts: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Area vector of faces given as consecutive node runs (fan triangulation from the first node)."""
    area = np.zeros((counts.size, 3), dtype=np.float64)
    origin = pts[starts].astype(np.float64)
    for j in range(1, int(counts.max()) - 1):
        idx = np.flatnonzero(counts > j + 1)
        a = pts[starts[idx] + j] - origin[idx]
        b = pts[starts[idx] + j + 1] - origin[idx]
        area[idx] += 0.5 * np.cross(a, b)
    return area


def iter_face_chunks(mesh, chunk_faces: int = 2_000_000):
    """Yield (start, stop, area, centre, cells0, face_idx1, cells1) for slices of all faces.

    area points from the first cell into the second one, so it is outward for cell 0 and
    inward for cell 1. `cells0` holds 1-based first-cell ids, `face_idx1` and `cells1` the
    interior faces of the slice and their second cells.
    """
    coords = np.asarray(node_coords(mesh)[:], dtype=np.float32)
    nn = mesh["meshes/1/faces/nodes/1/nnodes"]
    nodes = mesh["meshes/1/faces/nodes/1/nodes"]
    c0 = mesh["meshes/1/faces/c0"]
    c1 = mesh["meshes/1/faces/c1"]
    runs = interior_runs(mesh)
    n_faces = int(nn.shape[0])
    cursor = 0
    for start in range(0, n_faces, chunk_faces):
        stop = min(n_faces, start + chunk_faces)
        counts = nn[start:stop].astype(np.int64)
        total = int(counts.sum())
        fnodes = nodes[cursor : cursor + total].astype(np.int64)
        cursor += total
        pts = coords[fnodes - 1]
        starts = np.zeros(counts.size, dtype=np.int64)
        if counts.size > 1:
            starts[1:] = np.cumsum(counts[:-1])
        centre = np.add.reduceat(pts, starts) / counts[:, None]
        area = fan_area(pts, starts, counts)
        first = read_split(c0, start, stop).astype(np.int64)
        face_idx, second = second_cells(c1, runs, start, stop)
        yield start, stop, area, centre, first, face_idx, second
