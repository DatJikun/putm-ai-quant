"""Export a solved case as a package for the CFD 3D viewer (github.com/DatJikun/cfd-3d-viewer).

The viewer reads a `<case>.viewer` folder: `metadata.json`, `surface.vtp` (the car), `volume.zarr`
(fields on a regular grid, one copy per slicing axis), `presets.json`, `streamlines/*.vtp` and
checksums. The viewer has no Fluent import of its own yet, so this writes the contract from the
`.cas.h5` and `.dat.h5`:

* the volume is the cell data averaged into a 2 cm grid (u, v, w, pressure, Cp and total pressure
  coefficient). Bins with no cells next to data are filled so the picture is continuous; bins deep
  inside the car stay empty and are masked out;
* the surface is the car's wall faces, merged on a 4 mm voxel grid so a browser can draw it, with Cp,
  wall shear and y+ on the vertices and the zone of every face;
* the streamlines are integrated here through the volume, from seed planes ahead of and under the car.

The numerical pieces below take plain arrays, so they can be tested without a solver file.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

FORMAT_VERSION = "1.0"
BOX = {"x": (-1.6, 3.2), "y": (-1.3, 0.15), "z": (-0.02, 1.6)}
SPACING_M = 0.02
VOXEL_M = 0.004
AXES = ("x", "y", "z")
GROUPS = {"surface": ("surface.vtp",), "presets": ("presets.json",), "streamlines": ("streamlines",), "volume": ("volume.zarr",)}

VOLUME_FIELDS = [
    {"id": "u", "label": "U (wzdłuż auta)", "unit": "m/s", "default_range": [0.0, 25.0], "default_palette": "rainbow-cfd"},
    {"id": "v", "label": "V (w bok)", "unit": "m/s", "default_range": [-8.0, 8.0], "default_palette": "rainbow-cfd"},
    {"id": "w", "label": "W (w górę)", "unit": "m/s", "default_range": [-8.0, 8.0], "default_palette": "rainbow-cfd"},
    {"id": "pressure", "label": "Ciśnienie", "unit": "Pa", "default_range": [-300.0, 150.0], "default_palette": "cp-diverging"},
    {"id": "cp", "label": "Cp", "unit": "1", "default_range": [-2.25, 1.0], "default_palette": "cp-diverging"},
    {"id": "cpt", "label": "Cpt (strata ciśnienia całkowitego)", "unit": "1", "default_range": [-1.0, 1.0], "default_palette": "rainbow-cfd"},
]
SURFACE_FIELDS = [
    {"id": "cp", "label": "Cp", "unit": "1", "default_range": [-2.25, 1.0], "default_palette": "cp-diverging"},
    {"id": "wss", "label": "Tarcie przy ścianie", "unit": "Pa", "default_range": [0.0, 3.0], "default_palette": "rainbow-cfd"},
    {"id": "yplus", "label": "y+", "unit": "1", "default_range": [0.0, 60.0], "default_palette": "rainbow-cfd"},
]


# ------------------------------------------------------------------------ volume

def grid_shape(spacing: float = SPACING_M) -> tuple[int, int, int]:
    return tuple(int(np.ceil((BOX[a][1] - BOX[a][0]) / spacing)) for a in AXES)  # type: ignore[return-value]


def grid_origin() -> tuple[float, float, float]:
    return tuple(BOX[a][0] for a in AXES)  # type: ignore[return-value]


def bin_cells(centers: np.ndarray, fields: dict[str, np.ndarray], spacing: float = SPACING_M) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Average cell values into a regular grid. Returns the fields (NaN where empty) and the cell counts."""
    shape = grid_shape(spacing)
    origin = np.asarray(grid_origin())
    idx = np.floor((centers - origin) / spacing).astype(np.int64)
    keep = np.all((idx >= 0) & (idx < np.asarray(shape)), axis=1)
    flat = (idx[keep, 0] * shape[1] + idx[keep, 1]) * shape[2] + idx[keep, 2]
    size = int(np.prod(shape))
    counts = np.bincount(flat, minlength=size).astype(np.float64)
    out = {}
    for name, values in fields.items():
        total = np.bincount(flat, weights=values[keep].astype(np.float64), minlength=size)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[name] = np.where(counts > 0, total / counts, np.nan).reshape(shape)
    return out, counts.reshape(shape)


def fill_volume(fields: dict[str, np.ndarray], counts: np.ndarray, min_reach: float = 1.5, max_reach: float = 8.0) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Fill empty voxels from the nearest data, as far as the local spacing of the data allows.

    Where cells are fine the reach is short, so thin walls stay thin. In the coarse far field the data
    are sparse and the reach is long. Voxels deep inside a solid have no data around them and stay
    empty. Returns the filled fields (0 where still empty) and the validity mask (uint8).
    """
    from scipy.ndimage import distance_transform_edt, uniform_filter

    filled = counts > 0
    dist, (ix, iy, iz) = distance_transform_edt(~filled, return_indices=True)
    density = uniform_filter(filled.astype(np.float64), size=5, mode="constant")
    spacing = 1.0 / np.cbrt(np.maximum(density, 1e-4))
    reach = np.clip(1.2 * spacing[ix, iy, iz], min_reach, max_reach)
    usable = filled | (dist <= reach)
    out = {}
    for name, grid in fields.items():
        value = grid[ix, iy, iz]
        out[name] = np.where(usable, value, 0.0).astype("<f4")
    return out, usable.astype("u1")


def volume_fields(centers: np.ndarray, p: np.ndarray, u: np.ndarray, v: np.ndarray, w: np.ndarray, rho: float, speed_ms: float, spacing: float = SPACING_M) -> tuple[dict[str, np.ndarray], np.ndarray]:
    q = 0.5 * rho * speed_ms**2
    speed2 = u * u + v * v + w * w
    binned, counts = bin_cells(centers, {"u": u, "v": v, "w": w, "pressure": p, "cp": p / q, "cpt": (p + 0.5 * rho * speed2) / q}, spacing)
    return fill_volume(binned, counts)


# ----------------------------------------------------------------------- surface

def cluster_faces(node_xyz: np.ndarray, counts: np.ndarray, face_values: dict[str, np.ndarray], voxel: float = VOXEL_M) -> dict:
    """Merge the nodes of the faces on a voxel grid and rebuild the polygons.

    node_xyz: the nodes of all faces one after another, shape (total, 3); counts: nodes per face.
    face_values: one value per face. Returns points, polygons (connectivity and offsets), the index of
    the face every polygon came from, and the face values averaged at the points.
    """
    keys = np.floor(node_xyz / voxel).astype(np.int64)
    keys -= keys.min(axis=0)
    code = (keys[:, 0] << 42) | (keys[:, 1] << 21) | keys[:, 2]
    unique, inverse = np.unique(code, return_inverse=True)
    n_points = unique.size
    members = np.bincount(inverse, minlength=n_points).astype(np.float64)
    points = np.stack([np.bincount(inverse, weights=node_xyz[:, d], minlength=n_points) / members for d in range(3)], axis=1)

    starts = np.zeros(counts.size, dtype=np.int64)
    if counts.size > 1:
        starts[1:] = np.cumsum(counts[:-1])
    face_of = np.repeat(np.arange(counts.size), counts)
    previous = np.roll(inverse, 1)
    first = np.zeros(inverse.size, dtype=bool)
    first[starts] = True
    drop = (inverse == previous) & ~first
    last = starts + counts - 1
    drop[last] |= inverse[last] == inverse[starts]
    keep_entry = ~drop
    new_counts = np.bincount(face_of[keep_entry], minlength=counts.size)
    face_ok = new_counts >= 3
    entry_ok = keep_entry & face_ok[face_of]
    connectivity = inverse[entry_ok]
    offsets = np.cumsum(new_counts[face_ok])
    face_index = np.flatnonzero(face_ok)
    vertex_weight = np.bincount(connectivity, minlength=n_points).astype(np.float64)
    point_values = {}
    for name, values in face_values.items():
        per_entry = np.repeat(values[face_index].astype(np.float64), new_counts[face_ok])
        total = np.bincount(connectivity, weights=per_entry, minlength=n_points)
        with np.errstate(invalid="ignore", divide="ignore"):
            point_values[name] = np.where(vertex_weight > 0, total / vertex_weight, 0.0)
    return {"points": points, "connectivity": connectivity, "offsets": offsets, "face_index": face_index, "point_values": point_values}


def _numbers(values: np.ndarray, fmt: str) -> str:
    flat = np.asarray(values).ravel()
    if flat.size == 0:
        return ""
    return " ".join(fmt % v for v in flat.tolist())


def _data_array(vtk_type: str, values: np.ndarray, name: str | None = None, components: int | None = None, fmt: str = "%.6g") -> str:
    attributes = [f'type="{vtk_type}"', 'format="ascii"']
    if name is not None:
        attributes.append(f'Name="{name}"')
    if components is not None:
        attributes.append(f'NumberOfComponents="{components}"')
    return f"<DataArray {' '.join(attributes)}>{_numbers(values, fmt)}</DataArray>"


def write_vtp(path: Path, points: np.ndarray, *, polys: tuple[np.ndarray, np.ndarray] | None = None, lines: tuple[np.ndarray, np.ndarray] | None = None, point_data: dict[str, np.ndarray] | None = None, cell_data: dict[str, np.ndarray] | None = None) -> None:
    """ASCII PolyData file in the layout the viewer's own writer produces."""
    points = np.asarray(points, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Punkty VTP muszą mieć kształt (n, 3)")
    n_polys = 0 if polys is None else int(polys[1].size)
    n_lines = 0 if lines is None else int(lines[1].size)
    point_xml = "\n".join(_data_array("Float32", np.asarray(v, dtype=np.float32), name=k) for k, v in (point_data or {}).items())
    cell_xml = "\n".join(
        _data_array("Int32", np.asarray(v), name=k, fmt="%d") if np.issubdtype(np.asarray(v).dtype, np.integer) else _data_array("Float32", np.asarray(v), name=k)
        for k, v in (cell_data or {}).items()
    )
    for values in (cell_data or {}).values():
        if np.asarray(values).size != n_polys + n_lines:
            raise ValueError("Dane komórek VTP muszą odpowiadać liczbie komórek")
    lines_xml = "" if lines is None else "<Lines>\n" + _data_array("Int64", lines[0], name="connectivity", fmt="%d") + "\n" + _data_array("Int64", lines[1], name="offsets", fmt="%d") + "\n</Lines>"
    polys_xml = "" if polys is None else "<Polys>\n" + _data_array("Int64", polys[0], name="connectivity", fmt="%d") + "\n" + _data_array("Int64", polys[1], name="offsets", fmt="%d") + "\n</Polys>"
    payload = f"""<?xml version="1.0"?>
<VTKFile type="PolyData" version="1.0" byte_order="LittleEndian">
<PolyData>
<Piece NumberOfPoints="{len(points)}" NumberOfLines="{n_lines}" NumberOfPolys="{n_polys}">
<PointData>{point_xml}</PointData>
<CellData>{cell_xml}</CellData>
<Points>{_data_array("Float32", points, components=3)}</Points>
{lines_xml}
{polys_xml}
</Piece>
</PolyData>
</VTKFile>
"""
    Path(path).write_text(payload, encoding="utf-8")


# ------------------------------------------------------------------- streamlines

def integrate_streamlines(u: np.ndarray, v: np.ndarray, w: np.ndarray, mask: np.ndarray, seeds: np.ndarray, *, spacing: float = SPACING_M, step: float = 0.02, max_length: float = 6.0, min_speed: float = 0.3) -> list[np.ndarray]:
    """Follow the velocity field from each seed (second-order, unit steps). Returns one polyline per seed."""
    from scipy.ndimage import map_coordinates

    origin = np.asarray(grid_origin())
    shape = np.asarray(u.shape)
    n_steps = int(max_length / step)

    def sample(pos: np.ndarray):
        idx = ((pos - origin) / spacing - 0.5).T
        vel = np.stack([map_coordinates(f, idx, order=1, mode="nearest") for f in (u, v, w)], axis=1)
        ok = map_coordinates(mask.astype("f4"), idx, order=1, mode="nearest") > 0.99
        return vel, ok

    pos = np.asarray(seeds, dtype=np.float64).copy()
    alive = np.ones(len(pos), dtype=bool)
    paths = [[p.copy()] for p in pos]
    for _ in range(n_steps):
        inside = np.all((pos >= origin) & (pos < origin + shape * spacing), axis=1)
        alive &= inside
        if not alive.any():
            break
        vel, ok = sample(pos)
        speed = np.linalg.norm(vel, axis=1)
        alive &= ok & (speed > min_speed)
        mid_vel, mid_ok = sample(pos + 0.5 * step * vel / np.maximum(speed, 1e-9)[:, None])
        mid_speed = np.linalg.norm(mid_vel, axis=1)
        alive &= mid_ok & (mid_speed > min_speed)
        direction = mid_vel / np.maximum(mid_speed, 1e-9)[:, None]
        pos = np.where(alive[:, None], pos + step * direction, pos)
        for i in np.flatnonzero(alive):
            paths[i].append(pos[i].copy())
    return [np.asarray(p) for p in paths if len(p) >= 3]


def plane_seeds(x: float, y: tuple[float, float], z: tuple[float, float], count: tuple[int, int]) -> np.ndarray:
    ys = np.linspace(y[0], y[1], count[0])
    zs = np.linspace(z[0], z[1], count[1])
    return np.array([[x, a, b] for a in ys for b in zs])


STREAMLINE_PRESETS = [
    {"id": "przod", "label": "Przed autem (siatka w poprzek)", "seed_kind": "plane", "x": -1.2, "y": (-0.95, -0.05), "z": (0.04, 1.05), "count": (8, 6)},
    {"id": "podloga", "label": "Pod podłogą", "seed_kind": "plane", "x": -0.55, "y": (-0.6, -0.05), "z": (0.02, 0.09), "count": (7, 2)},
    {"id": "skrzydla", "label": "Nad skrzydłami", "seed_kind": "plane", "x": -1.0, "y": (-0.85, -0.1), "z": (0.12, 0.35), "count": (6, 3)},
]


def preset_documents(streams: list[dict]) -> dict:
    cameras = [
        {"id": "bok", "label": "Z boku", "position": [0.45, -4.6, 0.7], "focal_point": [0.45, -0.3, 0.4], "view_up": [0, 0, 1]},
        {"id": "przod", "label": "Z przodu", "position": [-4.6, -0.3, 0.8], "focal_point": [0.45, -0.3, 0.4], "view_up": [0, 0, 1]},
        {"id": "gora", "label": "Z góry", "position": [0.45, -0.3, 5.0], "focal_point": [0.45, -0.3, 0.4], "view_up": [1, 0, 0]},
        {"id": "ukos", "label": "Z ukosa", "position": [3.6, -3.6, 2.1], "focal_point": [0.45, -0.3, 0.4], "view_up": [0, 0, 1]},
    ]
    color_maps = [
        {"id": "rainbow-cfd", "label": "Tęcza CFD", "stops": [{"position": 0, "rgba": [0.06, 0.12, 0.55, 1]}, {"position": 0.5, "rgba": [0.05, 0.8, 0.65, 1]}, {"position": 1, "rgba": [0.9, 0.15, 0.08, 1]}]},
        {"id": "cp-diverging", "label": "Cp: podciśnienie na niebiesko", "stops": [{"position": 0, "rgba": [0.1, 0.25, 0.7, 1]}, {"position": 0.5, "rgba": [0.95, 0.95, 0.95, 1]}, {"position": 1, "rgba": [0.8, 0.1, 0.1, 1]}]},
        {"id": "cobalt", "label": "Kobalt", "stops": [{"position": 0, "rgba": [0.12, 0.3, 0.55, 1]}, {"position": 1, "rgba": [0.95, 0.35, 0.12, 1]}]},
    ]
    streamlines = [
        {"id": s["id"], "label": s["label"], "seed_kind": s["seed_kind"], "seed_bounds_m": [s["x"], s["y"][0], s["z"][0], s["x"], s["y"][1], s["z"][1]], "seed_count": [1, s["count"][0], s["count"][1]], "max_length_m": 6.0, "direction": "forward"}
        for s in streams
    ]
    return {"cameras": cameras, "color_maps": color_maps, "streamlines": streamlines}


# ----------------------------------------------------------------------- package

def digest_paths(root: Path, paths) -> str:
    """Same hash the viewer uses to check a package: sorted relative paths with content digests."""
    entries = []
    for path in paths:
        if path.is_file():
            entries.append((path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    logical = hashlib.sha256()
    for relative, content in sorted(entries):
        logical.update(relative.encode("utf-8"))
        logical.update(b"\0")
        logical.update(content.encode("ascii"))
        logical.update(b"\n")
    return logical.hexdigest()


def digest_group(root: Path, group: str) -> str:
    paths: list[Path] = []
    for location in GROUPS[group]:
        candidate = root / location
        if candidate.is_dir():
            paths.extend(p for p in candidate.rglob("*") if p.is_file())
        else:
            paths.append(candidate)
    return digest_paths(root, paths)


def write_volume(path: Path, fields: dict[str, np.ndarray], mask: np.ndarray) -> None:
    import zarr

    shape = mask.shape
    chunks = {"x": (1, min(shape[1], 128), min(shape[2], 128)), "y": (min(shape[0], 128), 1, min(shape[2], 128)), "z": (min(shape[0], 128), min(shape[1], 128), 1)}
    group = zarr.open_group(path, mode="w")
    for name, values in {**fields, "valid_mask": mask}.items():
        for axis, axis_chunks in chunks.items():
            group.create_array(f"{name}/{axis}", data=values, chunks=axis_chunks)


def assemble_package(
    out: Path,
    *,
    case_id: str,
    display_name: str,
    reference: dict,
    fields: dict[str, np.ndarray],
    mask: np.ndarray,
    surface: dict,
    zone_names: list[str],
    streams: list[dict],
    paths_by_stream: dict[str, list[np.ndarray]],
    spacing: float = SPACING_M,
) -> Path:
    """Write the package atomically: build next to the target, then rename."""
    out = Path(out)
    building = out.with_name(out.name + ".building")
    if building.exists():
        shutil.rmtree(building)
    if out.exists():
        shutil.rmtree(out)
    (building / "streamlines").mkdir(parents=True)
    write_vtp(
        building / "surface.vtp",
        surface["points"],
        polys=(surface["connectivity"], surface["offsets"]),
        point_data=surface["point_values"],
        cell_data={"zone_id": surface["zone_id"].astype(np.int32)},
    )
    (building / "presets.json").write_text(json.dumps(preset_documents(streams), indent=2, sort_keys=True), encoding="utf-8")
    for stream_id, paths in paths_by_stream.items():
        if not paths:
            continue
        points = np.concatenate(paths)
        sizes = np.array([len(p) for p in paths])
        write_vtp(building / "streamlines" / f"{stream_id}.vtp", points, lines=(np.arange(points.shape[0]), np.cumsum(sizes)))
    write_volume(building / "volume.zarr", fields, mask)
    metadata = {
        "format_version": FORMAT_VERSION,
        "case_id": case_id,
        "display_name": display_name,
        "steady": True,
        "complete": True,
        "grid": {"shape": list(mask.shape), "origin_m": list(grid_origin()), "spacing_m": [spacing] * 3, "axis_order": "xyz"},
        "reference_values": {"density_kg_m3": reference["rho"], "velocity_m_s": reference["speed_ms"], "pressure_pa": 0.0, "length_m": reference["length_m"]},
        "volume_fields": VOLUME_FIELDS,
        "surface_fields": SURFACE_FIELDS,
        "surface_zones": zone_names,
        "checksums": {group: digest_group(building, group) for group in GROUPS},
    }
    (building / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    (building / "COMPLETE").write_text("", encoding="utf-8")
    building.rename(out)
    return out


# --------------------------------------------------------------------- from files

def _zone_polygons(mesh, first: int, last: int) -> tuple[np.ndarray, np.ndarray]:
    """Nodes (flat, xyz) and node counts of the faces first..last (1-based, inclusive)."""
    from ingest.h5_mesh import node_coords, node_cursor

    start, count = first - 1, last - first + 1
    nn = mesh["meshes/1/faces/nodes/1/nnodes"]
    nodes = mesh["meshes/1/faces/nodes/1/nodes"]
    counts = nn[start : start + count].astype(np.int64)
    cursor = node_cursor(nn, start)
    fnodes = nodes[cursor : cursor + int(counts.sum())].astype(np.int64)
    unique, inverse = np.unique(fnodes, return_inverse=True)
    xyz = np.asarray(node_coords(mesh)[unique - 1], dtype=np.float64)[inverse]
    return xyz, counts


def read_surface(case: Path, *, rho: float, mu: float, speed_ms: float, voxel: float = VOXEL_M) -> tuple[dict, list[str]]:
    import h5py

    from ingest.wall_forces import group_for
    from ingest.wall_state import checked_layout, wall_state

    cas, dat = next(case.rglob("*.cas.h5")), next(case.rglob("*.dat.h5"))
    q = 0.5 * rho * speed_ms**2
    parts, zone_names = [], []
    with h5py.File(cas, "r") as mesh, h5py.File(dat, "r") as data:
        for name, packed_at, a, b in checked_layout(mesh, data):
            if group_for(name) is None:
                continue
            state = wall_state(mesh, data, packed_at, a, b, rho=rho, mu=mu)
            xyz, counts = _zone_polygons(mesh, a, b)
            clustered = cluster_faces(xyz, counts, {"cp": state["pressure"] / q, "wss": np.linalg.norm(state["tau"], axis=1), "yplus": state["yplus"]}, voxel)
            clustered["zone_id"] = np.full(clustered["face_index"].size, len(zone_names), dtype=np.int32)
            zone_names.append(name)
            parts.append(clustered)
    points, connectivity, offsets, zone_id = [], [], [], []
    point_values: dict[str, list[np.ndarray]] = {k: [] for k in ("cp", "wss", "yplus")}
    base, ends = 0, 0
    for part in parts:
        points.append(part["points"])
        connectivity.append(part["connectivity"] + base)
        offsets.append(part["offsets"] + ends)
        zone_id.append(part["zone_id"])
        for k in point_values:
            point_values[k].append(part["point_values"][k])
        base += part["points"].shape[0]
        ends += int(part["connectivity"].size)
    return (
        {
            "points": np.concatenate(points),
            "connectivity": np.concatenate(connectivity),
            "offsets": np.concatenate(offsets),
            "zone_id": np.concatenate(zone_id),
            "point_values": {k: np.concatenate(v) for k, v in point_values.items()},
        },
        zone_names,
    )


def export_viewer_package(
    case: Path,
    out_dir: Path,
    *,
    case_id: str,
    display_name: str,
    rho: float,
    mu: float,
    speed_ms: float,
    length_m: float = 1.53,
    cache_dir: Path | None = None,
    spacing: float = SPACING_M,
    voxel: float = VOXEL_M,
) -> Path:
    import h5py

    from ingest.flow_field import cell_centers

    cas, dat = next(case.rglob("*.cas.h5")), next(case.rglob("*.dat.h5"))
    centers = cell_centers(cas, None if cache_dir is None else cache_dir / "cell_centers.npy")
    with h5py.File(dat, "r") as data:
        cells = data["results/1/phase-1/cells"]
        p, u, v, w = (np.asarray(cells[f"{name}/1"][:], dtype=np.float32) for name in ("SV_P", "SV_U", "SV_V", "SV_W"))
    fields, mask = volume_fields(centers, p, u, v, w, rho, speed_ms, spacing)
    del centers, p
    seeds = {s["id"]: plane_seeds(s["x"], s["y"], s["z"], s["count"]) for s in STREAMLINE_PRESETS}
    paths = {sid: integrate_streamlines(fields["u"], fields["v"], fields["w"], mask, pts, spacing=spacing) for sid, pts in seeds.items()}
    surface, zones = read_surface(case, rho=rho, mu=mu, speed_ms=speed_ms, voxel=voxel)
    return assemble_package(
        Path(out_dir) / f"{case_id}.viewer",
        case_id=case_id,
        display_name=display_name,
        reference={"rho": rho, "speed_ms": speed_ms, "length_m": length_m},
        fields=fields,
        mask=mask,
        surface=surface,
        zone_names=zones,
        streams=[s for s in STREAMLINE_PRESETS if paths.get(s["id"])],
        paths_by_stream=paths,
        spacing=spacing,
    )
