"""Device cards from the case STEP, so hero frames follow this baseline."""

from __future__ import annotations

from pathlib import Path

from ingest.car_layout import classify_part, other_half_bbox

HERO_GROUP = {
    "przednie skrzydło, profil główny": "front-wing",
    "przednie skrzydło, klapa": "front-wing",
    "tylne skrzydło, profil główny": "rear-wing",
    "tylne skrzydło, element": "rear-wing",
    "podłoga": "floor",
}

PROFILE_KNOWN = "nieznana rodzina — współrzędne przekroju są w sectionMm"


def _slug(name: str, bbox: dict) -> str:
    side = "L" if bbox["ymax"] <= 10 else ("R" if bbox["ymin"] > 10 else "C")
    raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in name)
    while "--" in raw:
        raw = raw.replace("--", "-")
    return f"{raw.strip('-')}-{side}"


def _span_mm(bbox: dict) -> float:
    if bbox["ymin"] < 0:
        return round(abs(min(bbox["ymin"], 0.0)), 2)
    return round(bbox["dy"], 2)


def card_from_measure(name: str, measured: dict) -> dict | None:
    """One CAD body -> one card. Mesh boxes and the unswept half are omitted."""
    info = classify_part(name)
    bbox = measured.get("bboxMm") or {}
    if not bbox or not info["onCar"] or other_half_bbox(bbox):
        return None
    group = HERO_GROUP.get(info["label"], info["kind"])
    card = {
        "id": _slug(name, bbox),
        "group": group,
        "role": info["label"],
        "cadName": name,
        "spanMm": _span_mm(bbox),
        "le": {"xMm": bbox["xmin"], "zMm": bbox["zmin"]},
        "te": {"xMm": bbox["xmax"], "zMm": bbox["zmax"]},
        "bboxMm": bbox,
        "onCar": True,
        "notes": info["note"],
    }
    chord = measured.get("chord")
    if info["kind"] == "airfoil" and chord:
        card["chordMm"] = chord["chordMm"]
        card["incidenceDeg"] = chord["incidenceDeg"]
        card["le"] = chord["le"]
        card["te"] = chord["te"]
        card["sectionYMm"] = measured.get("sectionYMm")
        card["sectionMm"] = measured.get("sectionLoops") or []
        card["profile"] = PROFILE_KNOWN
    elif info["kind"] == "floor":
        card["sectionYMm"] = measured.get("sectionYMm")
        card["sectionMm"] = measured.get("sectionLoops") or []
        card["notes"] = (
            info["note"]
            + " Pozycja X skrzydła bierz z płatów. Ta karta ustawia tylko zasięg podłogi."
        )
    return card


def cards_from_step(path: Path) -> list[dict]:
    from ingest.cad_measure import HAS_OCP, _bbox, load_named_solids, measure_solid

    if not HAS_OCP:
        raise ImportError("cad_measure wymaga pakietu ocp")
    cards = []
    for item in load_named_solids(path):
        info = classify_part(item["name"])
        bbox = _bbox(item["shape"])
        if not info["onCar"] or other_half_bbox(bbox):
            continue
        do_section = info["kind"] in {"airfoil", "floor"}
        measured = measure_solid(item, do_chord=do_section) if do_section else {
            "bboxMm": {key: round(value, 2) for key, value in bbox.items()},
        }
        card = card_from_measure(item["name"], measured)
        if card:
            cards.append(card)
    return cards
