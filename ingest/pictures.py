from __future__ import annotations

import re
from pathlib import Path

from ingest.slices import load_slices, station_m

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

# Stacje, które warto pokazać agentowi na starcie (metry, oś X).
HERO_X_M = (-0.5, 0.0, 0.7, 1.2, 1.6, 2.0, 2.4)
HERO_Y_M = (-0.01, -0.4)
HERO_Z_M = (0.05, 0.25, 0.55)


def _field_from_folder(name: str) -> str:
    return FIELD_FROM_FOLDER.get(name.lower(), name.lower())


def index_pictures(
    root: Path,
    picture_rels: list[str],
    slices: dict | None = None,
) -> dict:
    slices = slices if slices is not None else load_slices()
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

    mark_heroes(entries)
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


def mark_heroes(entries: list[dict]) -> None:
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

    def pick_station(axis: str, field: str, camera: str, stations: tuple, reason: str) -> None:
        pool = by_key.get((axis, field, camera), [])
        for target in stations:
            img = _closest(pool, target)
            if img and not img["hero"]:
                img["hero"] = True
                img["reason"] = f"{reason} (stacja {img['stationM']} m)."

    pick_surface("yplus", "y_plus", [1], "y+ na powierzchni.")
    pick_surface("cp", "Cp", [1, 12], "Mapa Cp na karoserii.")
    pick_station("x", "cpt", "slice", HERO_X_M, "Przekrój X, Cp total")
    pick_station("x", "vel", "slice", (0.7, 2.0), "Przekrój X, |V|")
    pick_station("y", "cpt", "slice", HERO_Y_M, "Przekrój Y, Cp total")
    pick_station("y", "vel", "slice", (-0.01,), "Przekrój Y, |V|")
    pick_station("z", "cpt", "slice", HERO_Z_M, "Przekrój Z, Cp total")
    pick_station("z", "vel", "slice", (0.55,), "Przekrój Z, |V|")
