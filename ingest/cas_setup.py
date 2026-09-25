"""Parse Fluent report-definitions, reference values and wheel walls from case settings.

Settings are Scheme text. In .cas.h5 they live in /settings; in ASCII .cas they sit at
the start of the file, before the mesh, so only the head of a multi-GB file is read.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path

HEAD_BYTES = 64 << 20

NUM = r"([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)"
VEC_RE = re.compile(rf"force-vector\s+{NUM}\s+{NUM}\s+{NUM}")
MOM_CENTER_RE = re.compile(rf"\(mom-center\s+{NUM}\s+{NUM}\s+{NUM}\)")
MOM_AXIS_RE = re.compile(rf"\(mom-axis\s+{NUM}\s+{NUM}\s+{NUM}\)")
NAME_RE = re.compile(r'\(name \. "([^"]+)"\)')
TYPE_RE = re.compile(r'\btype\s+"([^"]+)"')
THREAD_PAREN_RE = re.compile(r"thread-names\s+\(([^)]+)\)")
THREAD_BARE_RE = re.compile(r"\(thread-names\s+([^)]+)\)")
ZONE_INFO_RE = re.compile(r"\(([A-Za-z0-9_.:-]+)\s+(wall|symmetry|velocity-inlet|pressure-outlet|interior)\b")
REFERENCE_RE = re.compile(rf"\(reference-(length|area|velocity|density|viscosity)\s+{NUM}\)")
THREAD_HEAD_RE = re.compile(r"\(\d+ \(\d+ (\S+) (\S+) \d+\)\(")
REPORTS_KEY = "(monitor/report-definitions"

REFERENCE_KEYS = {
    "length": "lengthM",
    "area": "areaM2",
    "velocity": "velocityMs",
    "density": "densityKgM3",
    "viscosity": "viscosityPaS",
}


def _scheme_bool(blob: str, key: str) -> bool | None:
    m = re.search(rf"{re.escape(key)}\s+\.\s+#([tf])", blob)
    if not m:
        m = re.search(rf"{re.escape(key)}\s+#([tf])", blob)
    if not m:
        return None
    return m.group(1) == "t"


def _scheme_value(blob: str, key: str) -> str | None:
    m = re.search(r"\(" + re.escape(key) + r" \. ([^)\s]+)\)", blob)
    return m.group(1) if m else None


def _float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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


def _balanced_end(text: str, start: int) -> int:
    depth = 0
    in_string = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if ch == '"' and text[i - 1] != "\\":
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


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
        cm = MOM_CENTER_RE.search(blob)
        if cm:
            rec["momentCenterM"] = [float(cm.group(1)), float(cm.group(2)), float(cm.group(3))]
        am = MOM_AXIS_RE.search(blob)
        if am:
            rec["momentAxis"] = [float(am.group(1)), float(am.group(2)), float(am.group(3))]
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
        if "forceVector" in rec or "momentCenterM" in rec or "threadNames" in rec or rec.get("type"):
            reports[name] = rec

    return {"reports": reports, "wallZones": zones}


def parse_reference_values(text: str) -> dict:
    out: dict[str, float] = {}
    for m in REFERENCE_RE.finditer(text):
        key = REFERENCE_KEYS[m.group(1)]
        if key not in out:
            out[key] = float(m.group(2))
    return out


def parse_wheel_walls(text: str) -> dict:
    """Rotating wheel walls: rotation origin and speed as the solver has them."""
    heads = list(THREAD_HEAD_RE.finditer(text))
    wheels: dict[str, dict] = {}
    for i, head in enumerate(heads):
        kind, name = head.group(1), head.group(2)
        low = name.lower()
        if kind != "wall" or "wheel" not in low:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        block = text[head.start() : end]
        if _scheme_value(block, "rotating?") != "#t":
            continue
        axle = "front" if "front" in low else "rear" if "rear" in low else None
        if axle is None or axle in wheels:
            continue
        wheels[axle] = {
            "zone": name,
            "originM": [
                _float(_scheme_value(block, "x-origin")),
                _float(_scheme_value(block, "y-origin")),
                _float(_scheme_value(block, "z-origin")),
            ],
            "axis": [
                _float(_scheme_value(block, "ai")),
                _float(_scheme_value(block, "aj")),
                _float(_scheme_value(block, "ak")),
            ],
            "omegaRadS": _float(_scheme_value(block, "omega")),
        }
    return wheels


def _is_case(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".cas", ".cas.gz", ".cas.h5", ".txt"))


def _h5_settings(path: Path) -> str:
    import h5py

    parts: list[str] = []
    with h5py.File(path, "r") as handle:
        settings = handle.get("settings")
        if settings is None:
            return ""
        for key in ("Rampant Variables", "Thread Variables"):
            if key not in settings:
                continue
            raw = settings[key][()]
            if hasattr(raw, "__len__") and not isinstance(raw, (bytes, str)):
                raw = raw[0]
            parts.append(raw.decode("latin1") if isinstance(raw, bytes) else str(raw))
    return "\n".join(parts)


def read_settings_text(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".cas.h5"):
        return _h5_settings(path)
    opener = gzip.open if name.endswith(".gz") else open
    with opener(path, "rb") as handle:
        return handle.read(HEAD_BYTES).decode("latin1")


def parse_settings_text(text: str) -> dict:
    reports: dict[str, dict] = {}
    source_line = None
    start = text.find(REPORTS_KEY)
    if start >= 0:
        section = text[start : _balanced_end(text, start)]
        reports = parse_report_blob(section)["reports"]
        source_line = text.count("\n", 0, start) + 1
    wall_zones: list[str] = []
    for line in text.splitlines():
        if "cfd-post-mesh-info" in line or "polygonal wall" in line:
            for zone in parse_report_blob(line)["wallZones"]:
                if zone not in wall_zones:
                    wall_zones.append(zone)
    return {
        "sourceLine": source_line,
        "reports": reports,
        "wallZones": wall_zones,
        "references": parse_reference_values(text),
        "wheels": parse_wheel_walls(text),
    }


def parse_cas_file(path: Path) -> dict:
    parsed = parse_settings_text(read_settings_text(path))
    reports = parsed["reports"]
    return {
        "file": path.name,
        "path": str(path),
        **parsed,
        "verified": "cx" in reports and "cz" in reports and "forceVector" in reports.get("cz", {}),
    }


def parse_cas_setup(paths: list[Path]) -> dict:
    merged = {
        "reports": {},
        "wallZones": [],
        "files": [],
        "verified": False,
        "references": {},
        "wheels": {},
        "errors": [],
    }
    for path in paths:
        if not _is_case(path) or not path.exists():
            continue
        try:
            one = parse_cas_file(path)
        except ImportError:
            merged["errors"].append(f"{path.name}: brak pakietu h5py, nie czytam ustawień z .cas.h5.")
            continue
        except OSError as exc:
            merged["errors"].append(f"{path.name}: {exc}")
            continue
        merged["files"].append(one["file"])
        for name, rec in one["reports"].items():
            merged["reports"].setdefault(name, rec)
        for z in one["wallZones"]:
            if z not in merged["wallZones"]:
                merged["wallZones"].append(z)
        if one["references"] and not merged["references"]:
            merged["references"] = one["references"]
            merged["referencesSource"] = one["file"]
        if one["wheels"] and not merged["wheels"]:
            merged["wheels"] = one["wheels"]
            merged["wheelsSource"] = one["file"]
        if one["verified"] and not merged["verified"]:
            merged["verified"] = True
            merged["source"] = one["file"]
            merged["sourceLine"] = one["sourceLine"]
    cz = merged["reports"].get("cz") or {}
    merged["czPositiveMeans"] = cz.get("positiveMeans")
    merged["czForceVector"] = cz.get("forceVector")
    merged["cxForceVector"] = (merged["reports"].get("cx") or {}).get("forceVector")
    return merged
