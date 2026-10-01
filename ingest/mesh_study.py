"""Does the answer depend on the mesh? Compare packs of the same car on different meshes.

Two meshes give a difference. Three give the order of convergence, an extrapolated
value and the grid convergence index (GCI, Roache), which is the uncertainty of the
finest mesh. The comparison is only meaningful when everything except the mesh is
the same, so that is checked first and every difference is listed.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

SAFETY_FACTOR_THREE = 1.25
SAFETY_FACTOR_TWO = 3.0
ASYMPTOTIC_MIN, ASYMPTOTIC_MAX = 0.5, 4.0
AREF_TOLERANCE = 0.02

QUANTITIES = (
    ("Cd", "opór Cd", ("kpis", "Cd")),
    ("downforce", "docisk (współczynnik)", ("kpis", "downforceCoeff")),
    ("frontPct", "balans przód [%]", ("kpis", "aeroBalance", "frontPct")),
    ("copXM", "środek parcia [m]", ("kpis", "aeroBalance", "copXM")),
)


def _dig(data, path):
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def load_pack(path: Path) -> dict:
    target = path / "aeropack.json" if path.is_dir() else path
    pack = json.loads(target.read_text(encoding="utf-8"))
    pack["_name"] = (pack.get("identity") or {}).get("caseId") or target.parent.name
    return pack


def cells_of(pack: dict) -> int | None:
    value = _num(_dig(pack, ("mesh", "cells")))
    return int(value) if value else None


def differences(packs: list[dict]) -> list[str]:
    """Everything that differs between the packs besides the mesh."""
    issues = []
    first = packs[0]
    for key, label in (
        (("methods", "turbulence"), "model turbulencji"),
        (("methods", "wallTreatment"), "traktowanie ściany"),
        (("identity", "halfModel"), "model połowy auta"),
        (("identity", "yawDeg"), "kąt znoszenia"),
        (("identity", "speedMs"), "prędkość"),
    ):
        values = [_dig(p, key) for p in packs]
        if any(v != values[0] for v in values):
            issues.append(f"Różni się {label}: " + ", ".join(f"{p['_name']}: {v}" for p, v in zip(packs, values)) + ".")
    areas = [_num(_dig(p, ("kpis", "references", "frontalAreaM2", "value"))) for p in packs]
    if all(areas) and max(areas) / min(areas) - 1 > AREF_TOLERANCE:
        issues.append("Różni się powierzchnia odniesienia (więcej niż 2%), więc to może być inna geometria, a nie tylko siatka: " + ", ".join(f"{p['_name']}: {a:.4f} m²" for p, a in zip(packs, areas)) + ".")
    for pack in packs:
        if _dig(pack, ("kpis", "convergence", "settled")) is False:
            issues.append(f"{pack['_name']}: siły się jeszcze nie ustabilizowały, więc różnica może wynikać z niedokończonego liczenia, a nie z siatki.")
    del first
    return issues


def richardson(fine: float, medium: float, coarse: float, r21: float, r32: float) -> dict:
    """Order of convergence, extrapolated value and GCI from three solutions (fine, medium, coarse)."""
    e21 = medium - fine
    e32 = coarse - medium
    if abs(e21) < 1e-12 and abs(e32) < 1e-12:
        return {"kind": "niezależne od siatki", "order": None, "extrapolated": fine, "gciFinePct": 0.0}
    ratio = e32 / e21 if abs(e21) > 1e-12 else None
    if ratio is None or ratio <= 0:
        return {
            "kind": "oscylacyjna lub rozbieżna",
            "order": None,
            "extrapolated": None,
            "gciFinePct": None,
            "note": "Wynik nie zbiega monotonicznie, więc rzędu zbieżności ani niepewności nie da się policzyć.",
        }
    # Fixed point iteration for a non-constant refinement ratio (Celik et al.).
    p = math.log(ratio) / math.log(r21)
    if abs(r21 - r32) > 1e-6:
        for _ in range(100):
            q = math.log((r21**p - 1) / (r32**p - 1))
            p_next = abs(math.log(ratio) + q) / math.log(r21)
            if abs(p_next - p) < 1e-6:
                p = p_next
                break
            p = p_next
    extrapolated = (r21**p * fine - medium) / (r21**p - 1)
    scale = abs(fine) if abs(fine) > 1e-12 else 1.0
    gci = SAFETY_FACTOR_THREE * abs((medium - fine) / scale) / (r21**p - 1) * 100.0
    return {
        "kind": "zbieżna",
        "order": round(p, 2),
        "extrapolated": extrapolated,
        "gciFinePct": round(gci, 3),
        "inAsymptoticRange": bool(ASYMPTOTIC_MIN <= p <= ASYMPTOTIC_MAX),
    }


def study(packs: list[dict]) -> dict:
    """packs: two or three aeropack dicts of the same car. Sorted from the finest mesh."""
    if len(packs) < 2:
        raise ValueError("potrzebne co najmniej dwie paczki")
    sized = [p for p in packs if cells_of(p)]
    if len(sized) != len(packs):
        missing = [p["_name"] for p in packs if not cells_of(p)]
        raise ValueError("brak liczby komórek w: " + ", ".join(missing))
    ordered = sorted(packs, key=lambda p: -cells_of(p))[:3]
    cells = [cells_of(p) for p in ordered]
    sizes = [c ** (-1.0 / 3.0) for c in cells]
    ratios = [sizes[i + 1] / sizes[i] for i in range(len(sizes) - 1)]
    issues = differences(ordered)
    rows = []
    for key, label, path in QUANTITIES:
        values = [_num(_dig(p, path)) for p in ordered]
        row = {"id": key, "label": label, "values": values}
        if any(v is None for v in values):
            row["verdict"] = "brak wartości w którejś paczce"
            rows.append(row)
            continue
        base = values[0]
        row["relativeDifferencePct"] = [None if abs(base) < 1e-12 else round(100.0 * (v - base) / abs(base), 3) for v in values[1:]]
        if len(ordered) == 3:
            row.update(richardson(values[0], values[1], values[2], ratios[0], ratios[1]))
        else:
            row["kind"] = "tylko dwie siatki"
            row["note"] = "Przy dwóch siatkach widać różnicę, ale nie rząd zbieżności ani niepewność."
        rows.append(row)
    return {
        "meshes": [{"name": p["_name"], "cells": c, "relativeCellSize": round(s / sizes[0], 3)} for p, c, s in zip(ordered, cells, sizes)],
        "refinementRatios": [round(r, 3) for r in ratios],
        "comparable": not [i for i in issues if not i.startswith(tuple(p["_name"] + ":" for p in ordered))],
        "issues": issues,
        "quantities": rows,
    }


def render(result: dict) -> str:
    lines = ["# Test niezależności od siatki", ""]
    lines += ["| Siatka | Komórki | Względny rozmiar komórki |", "| --- | --- | --- |"]
    for m in result["meshes"]:
        lines.append(f"| {m['name']} | {m['cells']:,} | {m['relativeCellSize']} |".replace(",", " "))
    lines.append("")
    if result["issues"]:
        lines += ["## Uwaga: to porównanie ma zastrzeżenia", ""] + [f"- {i}" for i in result["issues"]] + [""]
    else:
        lines += ["Poza siatką wszystko jest takie samo (model, ściana, prędkość, powierzchnia).", ""]
    lines += ["## Wyniki", "", "| Wielkość | Wartości (od najgęstszej) | Zmiana względem najgęstszej | Rząd zbieżności | Wartość z ekstrapolacji | Niepewność GCI |", "| --- | --- | --- | --- | --- | --- |"]
    for row in result["quantities"]:
        values = ", ".join("brak" if v is None else f"{v:.4g}" for v in row["values"])
        diff = ", ".join("brak" if d is None else f"{d:+.2f}%" for d in row.get("relativeDifferencePct", [])) or "brak"
        order = row.get("order")
        extra = row.get("extrapolated")
        gci = row.get("gciFinePct")
        lines.append(
            f"| {row['label']} | {values} | {diff} | {'brak' if order is None else order} | "
            f"{'brak' if extra is None else f'{extra:.4g}'} | {'brak' if gci is None else f'{gci:.2f}%'} |"
        )
    notes = sorted({row["note"] for row in result["quantities"] if row.get("note")})
    if notes:
        lines += [""] + [f"- {n}" for n in notes]
    lines += [""]
    return "\n".join(lines)


def write_study(paths: list[Path], out_json: Path, out_md: Path) -> dict:
    result = study([load_pack(p) for p in paths])
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render(result), encoding="utf-8")
    return result
