"""Parse Fluent report-definitions from ASCII .cas / Scheme dumps."""

from __future__ import annotations

import re
from pathlib import Path

VEC_RE = re.compile(
    r"force-vector\s+([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)"
    r"\s+([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)"
    r"\s+([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)"
)
NAME_RE = re.compile(r'\(name \. "([^"]+)"\)')
TYPE_RE = re.compile(r'\btype\s+"([^"]+)"')
THREAD_PAREN_RE = re.compile(r"thread-names\s+\(([^)]+)\)")
THREAD_BARE_RE = re.compile(r"\(thread-names\s+([^)]+)\)")
ZONE_INFO_RE = re.compile(r"\(([A-Za-z0-9_.:-]+)\s+(wall|symmetry|velocity-inlet|pressure-outlet|interior)\b")


def _scheme_bool(blob: str, key: str) -> bool | None:
    m = re.search(rf"{re.escape(key)}\s+\.\s+#([tf])", blob)
    if not m:
        m = re.search(rf"{re.escape(key)}\s+#([tf])", blob)
    if not m:
        return None
    return m.group(1) == "t"


def _vector_meaning(name: str, vector: list[float] | None) -> str | None:
    if not vector:
        return None
    x, _y, z = vector
    if name == "cx" or (x > 0.5 and abs(z) < 0.1):
        return "drag"
    if z < -0.5:
        return "downforce"
    if z > 0.5:
        return "lift"
    return None


def _split_reports(text: str) -> list[tuple[str, str]]:
    hits = list(NAME_RE.finditer(text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        out.append((m.group(1), text[m.start() : end]))
    return out


def parse_report_blob(text: str) -> dict:
    reports: dict[str, dict] = {}
    zones: list[str] = []
    for m in ZONE_INFO_RE.finditer(text):
        if m.group(1) not in zones:
            zones.append(m.group(1))

    for name, blob in _split_reports(text):
        rec: dict = {"name": name}
        vm = VEC_RE.search(blob)
        if vm:
            rec["forceVector"] = [float(vm.group(1)), float(vm.group(2)), float(vm.group(3))]
        tm = TYPE_RE.search(blob)
        if tm:
            rec["type"] = tm.group(1)
        elif "report-definition drag" in blob:
            rec["type"] = "drag"
        elif "report-definition lift" in blob:
            rec["type"] = "lift"
        elif "report-definition moment" in blob:
            rec["type"] = "moment"
        threads = THREAD_PAREN_RE.search(blob) or THREAD_BARE_RE.search(blob)
        if threads:
            rec["threadNames"] = threads.group(1).split()
        scaled = _scheme_bool(blob, "scaled?")
        if scaled is not None:
            rec["scaled"] = scaled
        per_zone = _scheme_bool(blob, "per-zone?")
        if per_zone is not None:
            rec["perZone"] = per_zone
        meaning = _vector_meaning(name, rec.get("forceVector"))
        if meaning:
            rec["positiveMeans"] = meaning
        if "forceVector" in rec or "threadNames" in rec or rec.get("type"):
            reports[name] = rec

    return {"reports": reports, "wallZones": zones}


def _is_text_cas(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".cas.h5") or name.endswith(".dat.h5"):
        return False
    return name.endswith(".cas") or name.endswith(".cas.gz") or name.endswith(".txt")


def parse_cas_file(path: Path) -> dict:
    reports: dict[str, dict] = {}
    wall_zones: list[str] = []
    source_line = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for i, line in enumerate(handle, 1):
            if "monitor/report-definitions" not in line and "force-vector" not in line:
                if "cfd-post-mesh-info" in line or "polygonal wall" in line:
                    extra = parse_report_blob(line)
                    for z in extra["wallZones"]:
                        if z not in wall_zones:
                            wall_zones.append(z)
                continue
            parsed = parse_report_blob(line)
            reports.update(parsed["reports"])
            for z in parsed["wallZones"]:
                if z not in wall_zones:
                    wall_zones.append(z)
            source_line = i
            if "cx" in reports and "cz" in reports:
                break
    return {
        "file": path.name,
        "path": str(path),
        "sourceLine": source_line,
        "reports": reports,
        "wallZones": wall_zones,
        "verified": "cx" in reports and "cz" in reports and "forceVector" in reports.get("cz", {}),
    }


def parse_cas_setup(paths: list[Path]) -> dict:
    merged = {"reports": {}, "wallZones": [], "files": [], "verified": False}
    for path in paths:
        if not _is_text_cas(path) or not path.exists():
            continue
        one = parse_cas_file(path)
        merged["files"].append(one["file"])
        merged["reports"].update(one["reports"])
        for z in one["wallZones"]:
            if z not in merged["wallZones"]:
                merged["wallZones"].append(z)
        if one["verified"]:
            merged["verified"] = True
            merged["source"] = one["file"]
            merged["sourceLine"] = one["sourceLine"]
    cz = merged["reports"].get("cz") or {}
    merged["czPositiveMeans"] = cz.get("positiveMeans")
    merged["czForceVector"] = cz.get("forceVector")
    merged["cxForceVector"] = (merged["reports"].get("cx") or {}).get("forceVector")
    return merged
