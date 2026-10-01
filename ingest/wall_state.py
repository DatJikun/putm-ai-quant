"""Geometry, pressure and rebuilt wall shear of the wall zones of a solved case.

The stored SV_WALL_SHEAR is not usable: it points against the flow (it is the
force of the wall on the fluid) and is four to five orders of magnitude too small
to be pascals. Wall shear is rebuilt from the friction-velocity y+ and the distance
of the first cell, tau = mu^2 y+^2 / (rho y^2), pointing along the near-wall
velocity relative to the wall.
"""

from __future__ import annotations

import numpy as np

from ingest.h5_mesh import face_ranges, node_coords, node_cursor

AIR_RHO = 1.225
AIR_MU = 1.7894e-5


def face_geometry(mesh, min_id: int, max_id: int) -> tuple[np.ndarray, np.ndarray]:
    """Area vector and centre of every face in [min_id, max_id].

    Fluent stores the nodes of a boundary face so that the right-hand normal
    points from the wall into the fluid cell. The pressure force on the wall is
    therefore -p A.
    """
    start = min_id - 1
    count = max_id - min_id + 1
    nn = mesh["meshes/1/faces/nodes/1/nnodes"]
    nodes = mesh["meshes/1/faces/nodes/1/nodes"]
    coords = node_coords(mesh)
    counts = nn[start : start + count].astype(np.int64)
    cursor = node_cursor(nn, start)
    total = int(counts.sum())
    fnodes = nodes[cursor : cursor + total].astype(np.int64)
    uniq, inv = np.unique(fnodes, return_inverse=True)
    pts = np.asarray(coords[uniq - 1], dtype=np.float64)[inv]
    starts = np.zeros(count, dtype=np.int64)
    if count > 1:
        starts[1:] = np.cumsum(counts[:-1])
    area = np.zeros((count, 3), dtype=np.float64)
    origin = pts[starts]
    # Fan triangulation from the first node. Valid for the convex faces a mesh has.
    for j in range(1, int(counts.max()) - 1):
        idx = np.flatnonzero(counts > j + 1)
        a = pts[starts[idx] + j] - origin[idx]
        b = pts[starts[idx] + j + 1] - origin[idx]
        area[idx] += 0.5 * np.cross(a, b)
    centers = np.add.reduceat(pts, starts) / counts[:, None]
    return area, centers


def area_vectors(mesh, min_id: int, max_id: int) -> np.ndarray:
    return face_geometry(mesh, min_id, max_id)[0]


def wall_layout(mesh) -> list[tuple[str, int, int, int]]:
    """(name, packed offset, first face id, last face id) for each wall zone."""
    layout = []
    packed = 0
    for name, a, b in face_ranges(mesh):
        layout.append((name, packed, a, b))
        packed += b - a + 1
    return layout


def checked_layout(mesh, data) -> list[tuple[str, int, int, int]]:
    """wall_layout, after checking that the wall fields in the .dat.h5 belong to this mesh."""
    layout = wall_layout(mesh)
    packed_total = sum(b - a + 1 for _, _, a, b in layout)
    have = int(data["results/1/phase-1/faces/SV_WALL_YPLUS_UTAU/1"].shape[0])
    if have != packed_total:
        raise RuntimeError(f"ściany {packed_total} nie zgadzają się z polem y+ {have}")
    return layout


def wall_state(mesh, data, packed_at: int, a: int, b: int, *, rho: float = AIR_RHO, mu: float = AIR_MU) -> dict:
    """Geometry, pressure, rebuilt wall shear, y+ and near-wall velocity of one wall zone."""
    count = b - a + 1
    area, centers = face_geometry(mesh, a, b)
    magnitude = np.linalg.norm(area, axis=1)
    normal = area / np.maximum(magnitude, 1e-30)[:, None]
    faces = data["results/1/phase-1/faces"]
    cells = data["results/1/phase-1/cells"]
    pressure = np.asarray(faces["SV_P/1"][a - 1 : b], dtype=np.float64)
    yplus = np.asarray(faces["SV_WALL_YPLUS_UTAU/1"][packed_at : packed_at + count], dtype=np.float64)
    moving = np.asarray(faces["SV_WALL_V/1"][packed_at : packed_at + count], dtype=np.float64)

    owners = mesh["meshes/1/faces/c0/1"][a - 1 : b].astype(np.int64) - 1
    uniq, inv = np.unique(owners, return_inverse=True)

    def gather(field: str) -> np.ndarray:
        return np.asarray(cells[f"{field}/1"][uniq], dtype=np.float64)[inv]

    first_cell = gather("SV_WALL_DIST")
    velocity = np.stack([gather("SV_U"), gather("SV_V"), gather("SV_W")], axis=1)
    relative = velocity - moving
    u_tan = relative - (relative * normal).sum(axis=1)[:, None] * normal
    length = np.linalg.norm(u_tan, axis=1)
    direction = u_tan / np.maximum(length, 1e-30)[:, None]
    tau_magnitude = mu**2 * yplus**2 / (rho * np.maximum(first_cell, 1e-12) ** 2)
    return {
        "area": area,
        "magnitude": magnitude,
        "normal": normal,
        "centers": centers,
        "pressure": pressure,
        "tau": direction * tau_magnitude[:, None],
        "yplus": yplus,
        "uTan": u_tan,
    }


