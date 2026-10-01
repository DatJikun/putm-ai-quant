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
