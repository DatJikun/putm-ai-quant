"""One answer from a pack folder. Shared by the MCP server and the app."""

from __future__ import annotations

import json
import math
from pathlib import Path


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def forces(pack_dir: Path) -> dict:
    pack = _read(pack_dir / "aeropack.json")
    if pack is None:
        raise FileNotFoundError("brak aeropack.json")
    kpis = pack.get("kpis") or {}
    groups = ((kpis.get("components") or {}).get("groups")) or {}
    return {
        "case": (pack.get("identity") or {}).get("caseId"),
        "cd": kpis.get("Cd"),
        "cl": kpis.get("Cl"),
        "ld": kpis.get("LOverD"),
        "cm": kpis.get("cm"),
        "cz": kpis.get("cz"),
        "komponenty": groups,
    }


def part(pack_dir: Path, name: str) -> dict:
    key = name.strip().lower()
    if not key:
        raise ValueError("brak nazwy części")
    doc = _read(pack_dir / "profile.json")
    if doc is None:
        raise FileNotFoundError("brak profile.json (python -m ingest profiles FOLDER_CASE_A --out packs/ID/profile.json)")
    for wing in doc.get("skrzydla") or []:
        if wing.get("id") != key and key not in str(wing.get("nazwa", "")).lower():
            continue
        cuts = []
        for cut in wing.get("przekroje") or []:
            item = {"y_m": cut.get("y_m")}
            if "dol" in cut:
                item["dol"] = (cut.get("dol") or {}).get("podsumowanie")
                item["gora"] = (cut.get("gora") or {}).get("podsumowanie")
            else:
                item["podsumowanie"] = cut.get("podsumowanie")
            cuts.append(item)
        return {"id": wing.get("id"), "nazwa": wing.get("nazwa"), "przekroje": cuts}
    raise FileNotFoundError(f"brak części {name}")


def slice_frame(pack_dir: Path, axis: str, station: float, field: str | None = None) -> dict:
    index = _read(pack_dir / "images" / "index.json")
    rows = (index or {}).get("index") or []
    best = None
    best_dist = None
    for row in rows:
        if row.get("axis") != axis:
            continue
        if field and row.get("field") != field:
            continue
        if row.get("stationM") is None:
            continue
        dist = abs(float(row["stationM"]) - station)
        if best_dist is None or dist < best_dist:
            best = row
            best_dist = dist
    if best is None:
        raise FileNotFoundError("brak klatki dla tej stacji")
    return {
        "plik": best.get("filename") or best.get("file"),
        "os": best.get("axis"),
        "pole": best.get("field"),
        "stacja_m": best.get("stationM"),
        "czesci": best.get("onCar") or [],
    }


def answer(pack_dir: Path, tool: str, args: dict) -> dict:
    if tool in {"get_forces", "forces"}:
        return forces(pack_dir)
    if tool in {"get_part", "part"}:
        return part(pack_dir, str(args.get("part") or args.get("name") or ""))
    if tool in {"get_slice", "slice"}:
        try:
            station = float(args.get("station") or args.get("station_m") or 0)
        except (TypeError, ValueError):
            station = math.nan
        if not math.isfinite(station):
            raise ValueError("station musi być liczbą")
        return slice_frame(pack_dir, str(args.get("axis") or "x"), station, args.get("field"))
    raise ValueError(f"nieznane pytanie: {tool}")
