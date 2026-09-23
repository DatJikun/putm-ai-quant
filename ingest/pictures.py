from __future__ import annotations

import re
from pathlib import Path

import yaml

from ingest.slices import load_slices, station_m

GEOMETRY = Path(__file__).resolve().parent.parent / "templates" / "geometry.yaml"
WAKE_OFFSET_MM = 50.0
COMPONENTS = (
    ("FW", "front-wing"),
    ("RW", "rear-wing"),
    ("Floor", "floor"),
)
FEATURES = ("leading_edge", "mid_chord", "trailing_edge_wake")

FIELD_FROM_FOLDER = {
    "cp": "cp",
    "cpt": "cpt",
    "cpt_siatka": "cpt",
    "velocity": "vel",
    "wss": "wss",
    "y_plus": "yplus",
    "yp": "yplus",
    "cpx": "cp",
    "cpz": "cp",
}

FRAME_RE = re.compile(r"AnimationFrame(\d+)", re.I)
SURFACE_RE = re.compile(r"^(CpX|CpZ|Cp|WSS|y_plus)_(\d+)$", re.I)

def _xs_mm(device: dict) -> list[float]:
    xs: list[float] = []
    for key in ("le", "te"):
        point = device.get(key) or {}
        raw = point.get("xMm")
        if isinstance(raw, (int, float)):
            xs.append(float(raw))
    return xs


def component_stations(geometry: dict, wake_mm: float = WAKE_OFFSET_MM) -> list[dict]:
    """X_LE = Xmin, X_MID = środek obwiedni, ślad = Xmax + wake_mm. Jednostka wyjścia: m."""
    by_group: dict[str, list[float]] = {}
    for device in geometry.get("devices") or []:
        group = device.get("group")
        if not group:
            continue
        by_group.setdefault(group, []).extend(_xs_mm(device))

    stations = []
    for component, group in COMPONENTS:
        xs = by_group.get(group) or []
        if len(xs) < 2:
            continue
        x_min = min(xs)
        x_max = max(xs)
        targets = {
            "leading_edge": x_min,
            "mid_chord": 0.5 * (x_min + x_max),
            "trailing_edge_wake": x_max + wake_mm,
        }
        stations.append(
            {
                "component": component,
                "xMinM": round(x_min / 1000.0, 4),
                "xMaxM": round(x_max / 1000.0, 4),
                "targets": [
                    {"feature": feature, "xM": round(targets[feature] / 1000.0, 4)}
                    for feature in FEATURES
                ],
            }
        )
    return stations


def load_geometry(path: Path | None = None) -> dict:
    src = path or GEOMETRY
    if not src.exists():
        return {}
    return yaml.safe_load(src.read_text(encoding="utf-8")) or {}


def _field_from_folder(name: str) -> str:
    return FIELD_FROM_FOLDER.get(name.lower(), name.lower())


def index_pictures(
    root: Path,
    picture_rels: list[str],
    slices: dict | None = None,
    geometry: dict | None = None,
) -> dict:
    slices = slices if slices is not None else load_slices()
    geometry = geometry if geometry is not None else load_geometry()
    entries = []
    max_frame = {"x": 1, "y": 1, "z": 1}

    for rel in picture_rels:
        path = Path(rel)
        parts = [p.lower() for p in path.parts]
        axis = "full"
        for candidate in ("x", "y", "z", "surface"):
            if candidate in parts:
                axis = "full" if candidate == "surface" else candidate
                break
        folder_field = path.parent.name
        field = _field_from_folder(folder_field)
        camera = "mesh" if "siatka" in folder_field.lower() else "slice"
        frame = None
        m = FRAME_RE.search(path.stem)
        if m:
            frame = int(m.group(1))
        else:
            s = SURFACE_RE.match(path.stem)
            if s:
                camera = s.group(1)
                frame = int(s.group(2))
                axis = "full"
        if axis in max_frame and frame:
            max_frame[axis] = max(max_frame[axis], frame)
        entries.append(
            {
                "id": rel.replace("\\", "/"),
                "filename": rel.replace("\\", "/"),
                "axis": axis,
                "field": field,
                "stationM": None,
                "frame": frame,
                "camera": camera,
                "hero": False,
            }
        )

    for item in entries:
        if item["axis"] in {"x", "y", "z"} and item["frame"]:
            item["stationM"] = station_m(
                item["axis"], item["frame"], max_frame[item["axis"]], slices
            )

    stations = component_stations(geometry)
    mark_heroes(entries, stations)
    by_axis = {"full": 0, "x": 0, "y": 0, "z": 0}
    for item in entries:
        by_axis[item["axis"]] = by_axis.get(item["axis"], 0) + 1
    encoded = any(e["stationM"] is not None for e in entries)
    return {
        "total": len(entries),
        "stationEncoded": encoded,
        "slices": {
            axis: slices[axis] for axis in ("x", "y", "z") if axis in slices
        },
        "byAxis": by_axis,
        "heroCount": sum(1 for e in entries if e["hero"]),
        "componentStations": stations,
        "index": entries,
        "warning": None if encoded else (
            "JPG z CFD-Post: folder = oś/pole, nazwa = AnimationFrameNNNN. "
            "Brak slices.yaml — stacja nieprzypisana."
        ),
    }


def _closest(pool: list[dict], target: float) -> dict | None:
    with_st = [e for e in pool if e.get("stationM") is not None]
    if not with_st:
        return None
    return min(with_st, key=lambda e: abs(e["stationM"] - target))


# Y/Z nie wynikają z obwiedni X komponentu. Symetria i wysokość podłogi zostają.
HERO_Y_M = (-0.01, -0.4)
HERO_Z_M = (0.05, 0.25, 0.55)


def mark_heroes(entries: list[dict], stations: list[dict] | None = None) -> None:
    by_key: dict[tuple[str, str, str], list[dict]] = {}
    for item in entries:
        key = (item["axis"], item["field"], item["camera"])
        by_key.setdefault(key, []).append(item)

    def pick_surface(field: str, camera: str, frames: list[int], reason: str) -> None:
        pool = by_key.get(("full", field, camera), [])
        indexed = {e["frame"]: e for e in pool if e.get("frame") is not None}
        for frame in frames:
            if frame in indexed and not indexed[frame]["hero"]:
                indexed[frame]["hero"] = True
                indexed[frame]["reason"] = reason

    def pick_station(axis: str, field: str, camera: str, targets: tuple, reason: str) -> None:
        pool = by_key.get((axis, field, camera), [])
        for target in targets:
            img = _closest(
                [e for e in pool if not e.get("hero")],
                target,
            )
            if img:
                img["hero"] = True
                img["reason"] = f"{reason} (stacja {img['stationM']} m)."

    def pick_feature(component: str, feature: str, target: float) -> None:
        pool = [
            e
            for e in by_key.get(("x", "cpt", "slice"), [])
            if e.get("stationM") is not None and not e.get("feature")
        ]
        img = _closest(pool, target)
        if not img:
            return
        img["hero"] = True
        img["component"] = component
        img["feature"] = feature
        img["targetM"] = target
        img["reason"] = (
            f"{component} {feature} (stacja {img['stationM']} m, cel {target} m)."
        )

    pick_surface("yplus", "y_plus", [1], "y+ na powierzchni.")
    pick_surface("cp", "Cp", [1, 12], "Mapa Cp na karoserii.")
    for station in stations or []:
        for target in station["targets"]:
            pick_feature(station["component"], target["feature"], target["xM"])
    pick_station("y", "cpt", "slice", HERO_Y_M, "Przekrój Y, Cp total")
    pick_station("y", "vel", "slice", (-0.01,), "Przekrój Y, |V|")
    pick_station("z", "cpt", "slice", HERO_Z_M, "Przekrój Z, Cp total")
    pick_station("z", "vel", "slice", (0.55,), "Przekrój Z, |V|")
