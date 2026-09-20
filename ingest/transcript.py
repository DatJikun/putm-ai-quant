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


def _int(text: str) -> int:
    return int(text.replace(",", ""))


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

    orthos = [float(m.group(1)) for m in ORTHO_RE.finditer(text)]
    if orthos:
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
    extracted["hits"] = hits[:80]
    return extracted


def parse_transcripts(paths: list[Path]) -> dict:
    parsed = [parse_transcript(p) for p in paths]
    merged: dict = {"files": [p["file"] for p in parsed], "hits": []}
    for item in parsed:
        merged["hits"].extend(item.get("hits", []))
        for key, value in item.items():
            if key in {"file", "hits"}:
                continue
            if key not in merged or merged[key] in (None, False):
                merged[key] = value
            elif key == "cells" and isinstance(value, int):
                merged[key] = max(int(merged[key]), value)
    merged["hits"] = merged["hits"][:120]
    return merged
