"""Questions to a meta pack. The model asks for one thing and receives that thing, not the whole file.

Used by `ask` (CLI), the MCP server and anything else that needs a short answer:

* `get_findings`: the ranked conclusions, each with the place in `meta.json` that proves it;
* `get_credibility`: the grade, its groups and every check with its source;
* `get_station`: the flow across the car at one x: loss, vortices, wheel wake, reversed flow;
* `get_wall_value`: Cp, shear, y+ and reversed flow at the wall point nearest to a position;
* `explain_change`: why this case differs from another one in the same `packs/` folder;
* `question`: free text, routed to one of the above by keywords.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from ingest.why import explain

SEVERITIES = ("wysoka", "srednia", "niska", "info")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _plain(text: str) -> str:
    """Lower case without Polish diacritics, for matching keywords."""
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in folded if not unicodedata.combining(c)).replace("ł", "l")


def load_meta(pack_dir: Path) -> dict:
    path = Path(pack_dir) / "meta" / "meta.json"
    if not path.exists():
        raise FileNotFoundError("brak meta/meta.json (python -m ingest meta FOLDER_CASE)")
    return json.loads(path.read_text(encoding="utf-8"))


def findings(pack_dir: Path, limit: int = 10, weight: str | None = None) -> dict:
    meta = load_meta(pack_dir)
    rows = meta.get("wnioski") or []
    if weight:
        if weight not in SEVERITIES:
            raise ValueError("waga: " + ", ".join(SEVERITIES))
        rows = [r for r in rows if r["waga"] == weight]
    return {"case": meta.get("caseId"), "razem": len(meta.get("wnioski") or []), "wnioski": rows[: max(1, int(limit))], "werdykt": (meta.get("werdykt") or {}).get("label")}


def credibility(pack_dir: Path) -> dict:
    cred = load_meta(pack_dir).get("wiarygodnosc")
    if not cred:
        raise FileNotFoundError("meta.json nie ma oceny wiarygodności")
    return {
        "ocena": cred["score"],
        "pokrycie_pct": cred["coverage"],
        "etykieta": cred["label"],
        "grupy": cred["byCategory"],
        "sprawdzenia": [{"sprawdzenie": c["title"], "waga": c["weight"], "ocena": c["status"], "wartosc": c["value"], "znaczenie": c["detail"], "zrodla": c["sources"]} for c in cred["checks"]],
        "nie_sprawdzono": cred["unknown"],
    }


def station(pack_dir: Path, x: float) -> dict:
    stations = (load_meta(pack_dir).get("raport") or {}).get("flow", {}) or {}
    rows = stations.get("stations") or []
    if not rows:
        raise FileNotFoundError("brak przekrojów przepływu w meta.json")
    best = min(rows, key=lambda s: abs(s["x_m"] - x))
    return {
        "x_m": best["x_m"],
        "zadane_x_m": x,
        "strata_m2": best.get("lossIntegralM2"),
        "pole_straty_m2": best.get("lossAreaM2"),
        "min_cpt": best.get("minCpt"),
        "cofniety_przeplyw_m2": best.get("reverseFlowAreaM2"),
        "okno_kol": best.get("wheels") or {},
        "wiry": best.get("vortices") or [],
    }


def wall_value(pack_dir: Path, x: float, y: float, z: float, label: str = "3mm") -> dict:
    """The wall point nearest to (x, y, z) from the surface map, with its values."""
    import numpy as np
    from scipy.spatial import cKDTree

    from ingest.metapack import load_surface

    s = load_surface(Path(pack_dir) / "meta", label)
    tree = cKDTree(s["xyz"])
    dist, i = tree.query([x, y, z])
    return {
        "punkt_m": [round(float(v), 4) for v in s["xyz"][i]],
        "odleglosc_m": round(float(dist), 4),
        "strefa": s["zone_names"][int(s["zone"][i])],
        "cp": round(float(s["cp"][i]), 3),
        "tarcie_Pa": round(float(s["wss"][i]), 3),
        "yplus": round(float(s["yplus"][i]), 2),
        "cofniety_przeplyw_pct": int(round(100 * float(s["rev"][i]))),
        "rozdzielczosc": label,
        "zajete_voxele": int(np.size(s["cp"])),
    }


def other_pack(pack_dir: Path, name: str | None) -> Path:
    """A sibling folder in `packs/`. Names with separators are refused."""
    pack_dir = Path(pack_dir)
    if name:
        if not SAFE_NAME.match(name) or name in (".", ".."):
            raise ValueError("zła nazwa drugiej paczki")
        target = pack_dir.parent / name
        if not target.is_dir():
            raise FileNotFoundError(f"brak paczki {name}")
        return target
    siblings = [p for p in pack_dir.parent.iterdir() if p.is_dir() and p != pack_dir and (p / "meta" / "meta.json").exists()]
    if len(siblings) != 1:
        raise ValueError("podaj `other`: nazwę drugiej paczki" + (f" (do wyboru: {', '.join(sorted(p.name for p in siblings))})" if siblings else ""))
    return siblings[0]


def explain_change(pack_dir: Path, other: str | None = None) -> dict:
    """Why `pack_dir` differs from `other`. `other` is the reference, `pack_dir` is the newer case."""
    ref = other_pack(pack_dir, other)
    return explain(load_meta(ref), load_meta(pack_dir))


def question(pack_dir: Path, text: str, other: str | None = None) -> dict:
    """Free text to one tool. The answer says which tool it used, so the choice can be checked."""
    plain = _plain(text)
    number = re.search(r"-?\d+(?:[.,]\d+)?", text)
    if re.search(r"dlaczego|czemu|co sie zmienilo|co zmienilo|roznic|wzgledem|zmiana", plain):
        return {"narzedzie": "explain_change", "odpowiedz": explain_change(pack_dir, other)}
    if re.search(r"ufac|wiarygod|zaufani|czy to dobre|jakosc symulacji|ocena", plain):
        return {"narzedzie": "get_credibility", "odpowiedz": credibility(pack_dir)}
    if number and re.search(r"stacj|przekroj|wir|strata|przeplyw|\bx\b|metr", plain):
        return {"narzedzie": "get_station", "odpowiedz": station(pack_dir, float(number.group().replace(",", ".")))}
    return {"narzedzie": "get_findings", "odpowiedz": findings(pack_dir)}
