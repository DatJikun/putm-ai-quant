from __future__ import annotations

from pathlib import Path

import yaml

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "slices.yaml"


def load_slices(path: Path | None = None) -> dict:
    src = path or TEMPLATE
    data = yaml.safe_load(src.read_text(encoding="utf-8"))
    return data


def station_m(axis: str, frame: int, n_frames: int, slices: dict) -> float | None:
    spec = slices.get(axis)
    if not spec or frame is None or n_frames < 1:
        return None
    start = float(spec["startM"])
    end = float(spec["endM"])
    if n_frames == 1:
        return start
    t = (frame - 1) / (n_frames - 1)
    return round(start + t * (end - start), 4)
