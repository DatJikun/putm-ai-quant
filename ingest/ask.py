"""One answer from a pack folder. Shared by the MCP server and the app."""

from __future__ import annotations

import json
import math
from pathlib import Path


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _plain(value):
    """JSON-safe copy of a YAML value. TBD and empty mean "not measured yet"."""
    if value in ("TBD", ""):
        return None
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _device_cards(pack_dir: Path) -> list[dict]:
    path = pack_dir / "geometry.yaml"
    if not path.exists():
        raise FileNotFoundError("brak geometry.yaml (python -m ingest pack FOLDER_CASE --out packs/ID)")
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    devices = doc.get("devices") if isinstance(doc, dict) else None
    cards = [_plain(item) for item in devices or [] if isinstance(item, dict)]
    return [card for card in cards if isinstance(card.get("id"), str) and card["id"]]


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
        raise FileNotFoundError("brak profile.json (python -m ingest profiles FOLDER_CASE --out packs/ID/profile.json)")
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


def device(pack_dir: Path, name: str) -> dict:
    """One geometry card. With no name, the ids to ask for."""
    cards = _device_cards(pack_dir)
    key = name.strip().lower()
    if not key:
        return {
            "urzadzenia": [
                {"id": card["id"], "group": card.get("group"), "role": card.get("role")}
                for card in cards
            ]
        }
    for card in cards:
        if card["id"].lower() == key:
            return card
    ids = ", ".join(card["id"] for card in cards)
    raise FileNotFoundError(f"brak urządzenia {name} (dostępne: {ids})")


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
    if tool in {"get_device", "device"}:
        return device(pack_dir, str(args.get("device") or ""))
    if tool in {"get_slice", "slice"}:
        try:
            station = float(args.get("station") or args.get("station_m") or 0)
        except (TypeError, ValueError):
            station = math.nan
        if not math.isfinite(station):
            raise ValueError("station musi być liczbą")
        return slice_frame(pack_dir, str(args.get("axis") or "x"), station, args.get("field"))
    raise ValueError(f"nieznane pytanie: {tool}")
