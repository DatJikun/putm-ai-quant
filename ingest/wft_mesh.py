"""Boundary-layer recipe from a Fluent Meshing workflow (.wft)."""

from __future__ import annotations

import json
from pathlib import Path


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _zones(args: dict) -> list[str]:
    raw = args.get("ZoneSelectionList") or args.get("BLZoneList") or args.get("BlLabelList") or []
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw]


def parse_wft(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    root = (data.get("workflow") or {}).get("ROOT") or {}
    layers = []
    stale = []
    for task in root.values():
        if not isinstance(task, dict):
            continue
        args = task.get("Arguments") or {}
        if "NumberOfLayers" not in args:
            continue
        name = str(args.get("BLControlName") or task.get("_name_") or "boundary-layer")
        record = {
            "name": name,
            "layers": int(float(args["NumberOfLayers"])),
            "firstHeightM": _as_float(args.get("FirstHeight")),
            "offset": args.get("OffsetMethodType"),
            "zones": _zones(args),
            "state": task.get("State"),
        }
        layers.append(record)
        if task.get("State") and task.get("State") != "Up-to-date":
            stale.append(name)
    return {
        "file": path.name,
        "version": (data.get("workflow") or {}).get("version"),
        "boundaryLayers": layers,
        "staleControls": stale,
    }


def ground_layer_warnings(parsed: dict) -> list[str]:
    warnings = []
    if parsed.get("staleControls"):
        warnings.append(
            "Przepis pryzm w .wft nie jest Up-to-date ("
            + ", ".join(parsed["staleControls"])
            + "). To zapis ustawień, nie pomiar warstwy w gotowej siatce."
        )
    for layer in parsed.get("boundaryLayers") or []:
        zones = layer.get("zones") or []
        if not any(zone == "domain_ground" or zone.endswith("domain_ground") for zone in zones):
            continue
        if layer.get("firstHeightM") is None:
            warnings.append(
                f"{layer['name']} na domain_ground: {layer['layers']} warstw, "
                "bez FirstHeight w .wft. Wysokości pierwszej komórki przy asfalcie nie ma w przepisie."
            )
    return warnings
