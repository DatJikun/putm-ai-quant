"""Place post-pro stations on the whole car, not only on wing profiles."""

from __future__ import annotations


def classify_part(name: str) -> dict:
    """What a STEP body is. Mesh boxes are not the car."""
    low = name.lower()
    if low == "domain" or low.startswith("domain"):
        return _row("tunnel", "tunel", "Obszar tunelu, nie auto.", False)
    if "ref-box" in low or "ref-edge" in low or "lvl" in low:
        return _row("mesh-box", "siatka", "Pudełko zagęszczenia siatki, nie kształt części.", False)
    if low.startswith("lustro"):
        return _row("other-half", "druga połowa", "Odbicie lustrzane. Symulacja tej połowy nie liczy.", False)
    if "fw-main" in low or "main_profile" in low:
        return _row("airfoil", "przednie skrzydło, profil główny", "Płat.", True)
    if "fw-profile" in low:
        return _row("airfoil", "przednie skrzydło, klapa", "Płat.", True)
    if "fw-end" in low:
        return _row("plate", "przednie skrzydło, płyta końcowa", "Płyta, nie profil.", True)
    if "fw-middle" in low or "middle_plate" in low:
        return _row("plate", "przednie skrzydło, płotek", "Płyta, nie profil.", True)
    if "rw-main" in low or "main_plane" in low:
        return _row("airfoil", "tylne skrzydło, profil główny", "Płat.", True)
    if "rw-plane" in low or "plane1" in low or "plane2" in low or "plane3" in low:
        return _row("airfoil", "tylne skrzydło, element", "Płat.", True)
    if "rw-end" in low:
        return _row("plate", "tylne skrzydło, płyta końcowa", "Płyta, nie profil.", True)
    if "mount" in low or "mouting" in low:
        return _row("mount", "mocowanie", "Wspornik.", True)
    if "cs-fan" in low or low.endswith("fan-cfd"):
        return _row("cooling", "wentylator", "Wentylator chłodnicy.", True)
    if "schroud" in low or "shroud" in low:
        return _row("cooling", "kanał chłodnicy", "Obudowa kanału.", True)
    if "-ut-" in low or low.endswith("ut-cfd") or "ut-assembly" in low:
        return _row("floor", "podłoga", "Bryła podłogi. Kąt z najdłuższej linii przekroju nie jest kątem natarcia.", True)
    if name.startswith("PM09-C"):
        return _row(
            "body",
            "monokok",
            "Powłoka nadwozia na szerokość auta. W pliku nie widać wręg ani warstw laminatu.",
            True,
        )
    if name.startswith("PM09-S"):
        return _row(
            "body",
            "nadwozie przy osi",
            "Bryła dosunięta do płaszczyzny symetrii. Nazwa CAD nie mówi, czy to pokrywa czy rama.",
            True,
        )
    if name.startswith("PM09-P"):
        return _row(
            "body",
            "nadwozie boczne",
            "Bryła z boku auta, schodzi najniżej w modelu. Nazwa CAD nie rozbija jej na podłogę i sidepod.",
            True,
        )
    return _row("part", name, "Część z CAD.", True)


def _row(kind: str, label: str, note: str, on_car: bool) -> dict:
    return {"kind": kind, "label": label, "note": note, "onCar": on_car}


def other_half_bbox(bbox: dict) -> bool:
    """Solid that sits only on +Y. The CFD half is Y<=0."""
    return bbox["ymin"] > 10 and bbox["ymax"] > 10


def parts_at(parts: list[dict], axis: str, station_m: float) -> list[str]:
    mm = station_m * 1000.0
    lo, hi = {"x": ("xmin", "xmax"), "y": ("ymin", "ymax"), "z": ("zmin", "zmax")}[axis]
    found = []
    for part in parts:
        if not part.get("onCar"):
            continue
        box = part["bboxMm"]
        if box[lo] - 1.0 <= mm <= box[hi] + 1.0:
            found.append(part["id"])
    return found


def segments_along_x(parts: list[dict]) -> list[dict]:
    """Intervals where the set of car parts does not change."""
    car = [part for part in parts if part.get("onCar")]
    edges = {box for part in car for box in (part["bboxMm"]["xmin"], part["bboxMm"]["xmax"])}
    ordered = sorted(edges)
    segments = []
    for left, right in zip(ordered, ordered[1:]):
        if right - left < 0.5:
            continue
        mid_m = (left + right) / 2.0 / 1000.0
        ids = parts_at(car, "x", mid_m)
        if not ids:
            continue
        if segments and segments[-1]["partIds"] == ids:
            segments[-1]["toM"] = round(right / 1000.0, 3)
            continue
        segments.append(
            {
                "fromM": round(left / 1000.0, 3),
                "toM": round(right / 1000.0, 3),
                "partIds": ids,
            }
        )
    return segments


def stamp_frames(entries: list[dict], parts: list[dict]) -> None:
    """Write onCar onto slice frames. Surface shots are the whole car, not a station."""
    for entry in entries:
        axis = entry.get("axis")
        station = entry.get("stationM")
        if axis in {"x", "y", "z"} and station is not None:
            entry["onCar"] = parts_at(parts, axis, station)
            entry["where"] = "przekrój"
        else:
            entry["onCar"] = []
            entry["where"] = "cały bolid, ujęcie kamery, bez pozycji przekroju"
