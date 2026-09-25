from __future__ import annotations

import re
from pathlib import Path

CELL_RE = re.compile(r"(?:(\d[\d,]*)\s+cells|cells:\s*(\d[\d,]*))", re.I)
ORTHO_RE = re.compile(
    r"final minimum Orthogonal Quality is\s+([0-9.]+)", re.I
)
ORTHO_WARN_RE = re.compile(
    r"minimum Orthogonal Quality of:\s+([0-9.]+)", re.I
)
ORTHO_SOLVER_RE = re.compile(
    r"Minimum Orthogonal Quality =\s+([0-9.]+(?:[eE][+-]?\d+)?)", re.I
)
ASPECT_RE = re.compile(r"Maximum Aspect Ratio =\s+([0-9.]+(?:[eE][+-]?\d+)?)", re.I)
PLANNED_ITER_RE = re.compile(
    r'IntegerEntry\d+\(Number of Iterations\)"\s+(\d+)|/solve/iterate\s+(\d+)', re.I
)
ITER_LEFT_RE = re.compile(
    r"^[ \t]*(\d+)[ \t]+[-+.\deE \t]+?[ \t]\d+:\d{2}:\d{2}[ \t]+(\d+)[ \t]*$", re.M
)
SCRIPT_ERROR_RE = re.compile(
    r"^.*(?:unknown -- enter choice again|Error: eval: unbound variable|invalid command \[).*$",
    re.M,
)
HEXCORE_RE = re.compile(r"octree hexcore", re.I)
PRISM_RE = re.compile(r"scoped prisms", re.I)
STAIRSTEP_RE = re.compile(
    r"Stair-stepping of all boundary layers occurr?ed at\s+(\d+)\s+locations",
    re.I,
)
FLUENT_RE = re.compile(r"ANSYS Fluent\s+([0-9]+ R[0-9]+)", re.I)
SYMMETRY_RE = re.compile(r"(\d+)\s+polygonal symmetry faces", re.I)
INLET_RE = re.compile(r"(\d+)\s+polygonal velocity-inlet faces", re.I)
SST_RE = re.compile(r"k-omega|k-ω|SST|Spalart|Realizable k-e", re.I)
MRF_RE = re.compile(r"mrf_fan", re.I)
MEMORY_RE = re.compile(r"Memory allocation failed", re.I)
YPLUS_WRITE_RE = re.compile(r"Written y-plus", re.I)
RESIDUAL_HEADER_RE = re.compile(
    r"continuity\s+x-velocity\s+y-velocity\s+z-velocity",
    re.I,
)
RESIDUAL_ROW_RE = re.compile(
    r"^\s*(\d+)\s+"
    r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"(?:\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?))?"
    r"(?:\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?))?",
    re.M,
)
DIVERGENCE_RE = re.compile(r"Divergence detected in AMG solver:\s*([A-Za-z -]+?)(?:\s{2,}|$)", re.M)
FPE_RE = re.compile(r"floating point exception", re.I)
BAD_TERMINATION_RE = re.compile(r"BAD TERMINATION OF ONE OF YOUR APPLICATION PROCESSES")
SIGSEGV_RE = re.compile(r"Received signal SIGSEGV")
WALL_NORMAL_RE = re.compile(
    r"wall motion has a significant normal component on\s+(\d+)\s+faces of face zone\s+(\d+)",
    re.I,
)
YPLUS_STAT_RE = re.compile(
    r"(area-weighted average|minimum|maximum|min|max|average)"
    r"\s+of\s+y-?plus\s+on\s+(\S+)\s*(?:=|is)\s*"
    r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)",
    re.I,
)


def _int(text: str) -> int:
    return int(text.replace(",", ""))


def _parse_residuals(text: str) -> dict | None:
    header = RESIDUAL_HEADER_RE.search(text)
    if not header:
        return None
    last = None
    for match in RESIDUAL_ROW_RE.finditer(text, header.end()):
        last = match
    if last is None:
        return None
    parsed = {
        "iteration": int(last.group(1)),
        "continuity": float(last.group(2)),
        "xMomentum": float(last.group(3)),
        "yMomentum": float(last.group(4)),
        "zMomentum": float(last.group(5)),
    }
    if last.group(6):
        parsed["k"] = float(last.group(6))
    if last.group(7):
        parsed["omega"] = float(last.group(7))
    return parsed


def _yplus_group(zone: str) -> str | None:
    name = zone.lower().strip(".,;")
    if any(token in name for token in ("fw", "rw", "wing", "flap")):
        return "wings"
    if any(token in name for token in ("ut", "floor", "diffuser", "under")):
        return "floor"
    return None


def _rollup_yplus(zones: dict[str, dict], group: str) -> dict | None:
    members = [
        stats for zone, stats in zones.items() if _yplus_group(zone) == group and stats
    ]
    if not members:
        return None
    rolled: dict[str, float] = {}
    for stat in ("min", "avg", "max"):
        values = [item[stat] for item in members if stat in item]
        if not values:
            continue
        if stat == "min":
            rolled[stat] = min(values)
        elif stat == "max":
            rolled[stat] = max(values)
        else:
            rolled[stat] = sum(values) / len(values)
    return rolled or None


def _yplus_record(zones: dict[str, dict]) -> dict:
    return {
        "zones": zones,
        "wings": _rollup_yplus(zones, "wings"),
        "floor": _rollup_yplus(zones, "floor"),
    }


def _parse_yplus(text: str) -> dict | None:
    zones: dict[str, dict] = {}
    stat_key = {
        "area-weighted average": "avg",
        "average": "avg",
        "minimum": "min",
        "min": "min",
        "maximum": "max",
        "max": "max",
    }
    for match in YPLUS_STAT_RE.finditer(text):
        key = stat_key[match.group(1).lower()]
        zone = match.group(2).strip(".,;")
        zones.setdefault(zone, {})[key] = float(match.group(3))
    if not zones:
        return None
    return _yplus_record(zones)


def _merge_yplus(previous: dict | None, incoming: dict) -> dict:
    if not previous:
        return incoming
    zones = dict(previous.get("zones") or {})
    zones.update(incoming.get("zones") or {})
    return _yplus_record(zones)


def _solver_health(text: str) -> dict:
    divergence: dict[str, int] = {}
    for m in DIVERGENCE_RE.finditer(text):
        eq = m.group(1).strip()
        divergence[eq] = divergence.get(eq, 0) + 1
    wall_normal = [
        {"faces": int(m.group(1)), "zoneId": int(m.group(2))}
        for m in WALL_NORMAL_RE.finditer(text)
    ]
    fpe = len(FPE_RE.findall(text))
    reasons = []
    if fpe:
        reasons.append("floating point exception")
    if SIGSEGV_RE.search(text):
        reasons.append("SIGSEGV")
    if MEMORY_RE.search(text):
        reasons.append("brak pamięci")
    crashed = fpe > 0 or bool(BAD_TERMINATION_RE.search(text) or SIGSEGV_RE.search(text))
    planned = [int(m.group(1) or m.group(2)) for m in PLANNED_ITER_RE.finditer(text)]
    rows = list(ITER_LEFT_RE.finditer(text))
    script_errors = [" ".join(m.group(0).split())[:160] for m in SCRIPT_ERROR_RE.finditer(text)]
    return {
        "plannedIterations": planned[-1] if planned else None,
        "iterationsLeft": int(rows[-1].group(2)) if rows else None,
        "scriptErrors": script_errors[:10],
        "scriptErrorCount": len(script_errors),
        "crashed": crashed,
        "crashReasons": reasons if crashed else [],
        "floatingPointExceptions": fpe,
        "divergence": divergence,
        "wallMotionNormal": wall_normal,
    }


def parse_transcript(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    hits: list[dict] = []

    def add(kind: str, match: re.Match[str]) -> None:
        start = text.rfind("\n", 0, match.start()) + 1
        end = text.find("\n", match.end())
        line = text[start : end if end != -1 else None].strip()
        hits.append({"kind": kind, "line": line, "file": path.name})

    extracted: dict = {"file": path.name}

    m = FLUENT_RE.search(text)
    if m:
        extracted["fluentVersion"] = m.group(1)
        add("fluent", m)

    cells = []
    for m in CELL_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        n = _int(raw)
        if n > 1000:
            cells.append(n)
            add("cells", m)
    if cells:
        extracted["cells"] = max(cells)

    solver_orthos = list(ORTHO_SOLVER_RE.finditer(text))
    orthos = [float(m.group(1)) for m in ORTHO_RE.finditer(text)]
    if solver_orthos:
        extracted["minOrthogonalQuality"] = float(solver_orthos[-1].group(1))
        add("ortho", solver_orthos[-1])
        aspects = list(ASPECT_RE.finditer(text))
        if aspects:
            extracted["maxAspectRatio"] = float(aspects[-1].group(1))
    elif orthos:
        extracted["minOrthogonalQuality"] = orthos[-1]
        add("ortho", list(ORTHO_RE.finditer(text))[-1])
    else:
        m = ORTHO_WARN_RE.search(text)
        if m:
            extracted["minOrthogonalQuality"] = float(m.group(1))
            add("ortho", m)

    extracted["hexcore"] = bool(HEXCORE_RE.search(text))
    extracted["scopedPrisms"] = bool(PRISM_RE.search(text))
    m = STAIRSTEP_RE.search(text)
    if m:
        extracted["prismStairstepLocations"] = int(m.group(1))
        add("stairstep", m)

    m = SYMMETRY_RE.search(text)
    if m:
        extracted["symmetryFaces"] = int(m.group(1))
        extracted["halfModel"] = True
        add("symmetry", m)

    m = INLET_RE.search(text)
    if m:
        extracted["inletFaces"] = int(m.group(1))
        add("inlet", m)

    turb = SST_RE.search(text)
    if turb:
        extracted["turbulenceHit"] = turb.group(0)
        add("turbulence", turb)

    extracted["mrfFan"] = bool(MRF_RE.search(text))
    extracted["memoryFailure"] = bool(MEMORY_RE.search(text))
    extracted["yPlusExported"] = bool(YPLUS_WRITE_RE.search(text))
    residuals = _parse_residuals(text)
    if residuals:
        extracted["residuals"] = residuals
        hits.append(
            {
                "kind": "residuals",
                "line": (
                    f"iter {residuals['iteration']} continuity {residuals['continuity']}"
                ),
                "file": path.name,
            }
        )
    y_plus = _parse_yplus(text)
    if y_plus:
        extracted["yPlus"] = y_plus
    health = _solver_health(text)
    extracted["solverHealth"] = health
    for m in list(FPE_RE.finditer(text))[:1]:
        add("crash", m)
    for m in list(DIVERGENCE_RE.finditer(text))[:1]:
        add("divergence", m)
    for m in WALL_NORMAL_RE.finditer(text):
        add("wall-motion", m)
    extracted["hits"] = hits[:80]
    return extracted


LATEST_WINS = {
    "residuals",
    "cells",
    "minOrthogonalQuality",
    "maxAspectRatio",
    "symmetryFaces",
    "inletFaces",
    "turbulenceHit",
    "fluentVersion",
}


def parse_transcripts(paths: list[Path]) -> dict:
    # fluent-YYYYMMDD-HHMMSS-PID.trn sorts by session start
    parsed = [parse_transcript(p) for p in sorted(paths, key=lambda p: p.name)]
    merged: dict = {"files": [p["file"] for p in parsed], "hits": []}
    merged["sessions"] = [
        {
            "file": item["file"],
            "lastIteration": (item.get("residuals") or {}).get("iteration"),
            **item["solverHealth"],
        }
        for item in parsed
    ]
    for item in parsed:
        merged["hits"].extend(item.get("hits", []))
        for key, value in item.items():
            if key in {"file", "hits", "solverHealth"}:
                continue
            if key == "yPlus" and isinstance(value, dict):
                merged["yPlus"] = _merge_yplus(merged.get("yPlus"), value)
                continue
            # A later session re-reads or re-meshes the case, so its numbers replace earlier ones.
            if key in LATEST_WINS and value is not None:
                merged[key] = value
            elif key not in merged or merged[key] in (None, False):
                merged[key] = value
    merged["hits"] = merged["hits"][:120]
    return merged
