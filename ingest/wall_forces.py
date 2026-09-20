"""Parse Fluent wall-force dumps and group PUTM surface_* zones."""

from __future__ import annotations

import re
from pathlib import Path

DIR_RE = re.compile(
    r"Direction Vector\s*\(\s*([+-]?\d+(?:\.\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)",
    re.I,
)
TRIPLE_RE = re.compile(r"\(([^)]+)\)")

GROUP_ORDER = ("fw", "rw", "floor", "body", "wheels", "cooling")
EXCLUDED_PREFIXES = ("domain_",)
SKIP_PREFIXES = ("interior--", "interior")


def group_for(name: str) -> str | None:
    n = name.lower()
    if n.startswith(SKIP_PREFIXES):
        return None
    if n.startswith(EXCLUDED_PREFIXES):
        return None
    if "wheel" in n:
        return "wheels"
    if n.startswith("surface_fw"):
        return "fw"
    if n.startswith("surface_rw"):
        return "rw"
    if n.startswith("surface_ut"):
        return "floor"
    if n.startswith("surface_rd") or n.startswith("surface_fan"):
        return "cooling"
    if n.startswith("surface_mono") or n.startswith("surface_sw"):
        return "body"
    if n.startswith("surface_"):
        return "other"
    return None


def _floats(text: str) -> list[float]:
    out: list[float] = []
    for tok in text.split():
        try:
            out.append(float(tok))
        except ValueError:
            return []
    return out


def _zone_from_vector_line(line: str) -> tuple[str, dict] | None:
    triples = [_floats(m.group(1)) for m in TRIPLE_RE.finditer(line)]
    if len(triples) != 6 or any(len(t) != 3 for t in triples):
        return None
    name = line.split("(", 1)[0].strip()
    if not name:
        return None
    fp, fv, ft, cp, cv, ct = triples
    rec = {
        "Fx_pressure": fp[0],
        "Fy_pressure": fp[1],
        "Fz_pressure": fp[2],
        "Fx_viscous": fv[0],
        "Fy_viscous": fv[1],
        "Fz_viscous": fv[2],
        "Fx": ft[0],
        "Fy": ft[1],
        "Fz": ft[2],
        "Cx_pressure": cp[0],
        "Cy_pressure": cp[1],
        "Cz_pressure": cp[2],
        "Cx_viscous": cv[0],
        "Cy_viscous": cv[1],
        "Cz_viscous": cv[2],
        "Cx": ct[0],
        "Cy": ct[1],
        "Cz": ct[2],
        "Cd": ct[0],
        "Cl": ct[2],
        "downforceCoeff": -ct[2],
        "F_pressure": fp[0],
        "F_viscous": fv[0],
        "F_total": ft[0],
        "C_pressure": cp[0],
        "C_viscous": cv[0],
        "C_total": ct[0],
    }
    return name, rec


def _zone_from_scalar_line(line: str) -> tuple[str, dict] | None:
    parts = line.split()
    if len(parts) < 7:
        return None
    name = parts[0]
    nums: list[float] = []
    for tok in parts[1:]:
        try:
            nums.append(float(tok))
        except ValueError:
            break
    if len(nums) < 6:
        return None
    rec = {
        "F_pressure": nums[0],
        "F_viscous": nums[1],
        "F_total": nums[2],
        "C_pressure": nums[3],
        "C_viscous": nums[4],
        "C_total": nums[5],
        "Fx": nums[2],
        "Cd": nums[5],
    }
    return name, rec


def parse_force_report(text: str) -> dict:
    direction = None
    m = DIR_RE.search(text)
    if m:
        direction = [float(m.group(1)), float(m.group(2)), float(m.group(3))]

    vector_zones: dict[str, dict] = {}
    scalar_zones: dict[str, dict] = {}
    vector_net = None
    scalar_net = None
    vector_mode = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("-"):
            continue
        if line.lower().startswith("forces"):
            vector_mode = "direction vector" not in line.lower()
            continue
        if line.lower().startswith("zone"):
            vector_mode = "(" in raw and raw.count("(") >= 3
            continue
        if "direction vector" in line.lower():
            continue

        parsed_vec = _zone_from_vector_line(line)
        if parsed_vec:
            name, rec = parsed_vec
            if name.lower() == "net":
                vector_net = rec
            else:
                vector_zones[name] = rec
            continue
        if vector_mode:
            continue
        parsed_s = _zone_from_scalar_line(line)
        if not parsed_s:
            continue
        name, rec = parsed_s
        if name.lower() == "net":
            scalar_net = rec
        else:
            scalar_zones[name] = rec

    if vector_zones:
        return {
            "format": "vector",
            "direction": None,
            "zones": vector_zones,
            "net": vector_net,
            "fluentNetIncludesTunnel": True,
        }
    return {
        "format": "scalar",
        "direction": direction,
        "zones": scalar_zones,
        "net": scalar_net,
        "fluentNetIncludesTunnel": True,
    }


def parse_force_file(path: Path) -> dict:
    parsed = parse_force_report(path.read_text(encoding="utf-8", errors="replace"))
    parsed["file"] = path.name
    return parsed


def _sum_records(rows: list[dict], keys: tuple[str, ...]) -> dict:
    out = {k: 0.0 for k in keys}
    for row in rows:
        for k in keys:
            if k in row and row[k] is not None:
                out[k] += float(row[k])
    return {k: round(v, 8) for k, v in out.items()}


SUM_KEYS = (
    "Fx",
    "Fy",
    "Fz",
    "Cx",
    "Cy",
    "Cz",
    "Cd",
    "Cl",
    "downforceCoeff",
    "Cx_pressure",
    "Cx_viscous",
    "Cz_pressure",
    "Cz_viscous",
    "F_pressure",
    "F_viscous",
    "F_total",
    "C_pressure",
    "C_viscous",
    "C_total",
)


def _ld(downforce: float | None, cd: float | None) -> float | None:
    if downforce is None or cd is None or abs(cd) < 1e-12:
        return None
    return round(downforce / cd, 6)


def _rel_err(got: float, ref: float) -> float:
    if abs(ref) < 1e-12:
        return 0.0 if abs(got) < 1e-12 else 1.0
    return abs(got - ref) / abs(ref)


def group_zones(parsed: dict) -> dict:
    buckets: dict[str, list[tuple[str, dict]]] = {g: [] for g in GROUP_ORDER}
    excluded: list[str] = []
    other: list[tuple[str, dict]] = []
    for name, rec in (parsed.get("zones") or {}).items():
        g = group_for(name)
        rec = {**rec, "group": g}
        if g is None:
            excluded.append(name)
            continue
        if g == "other":
            other.append((name, rec))
            continue
        buckets[g].append((name, rec))
    if other:
        buckets.setdefault("other", []).extend(other)

    groups = {}
    order = GROUP_ORDER + (("other",) if other else ())
    for g in order:
        items = buckets.get(g) or []
        if not items:
            continue
        summed = _sum_records([r for _, r in items], SUM_KEYS)
        summed["zones"] = [n for n, _ in items]
        summed["LOverD"] = _ld(summed.get("downforceCoeff"), summed.get("Cd"))
        groups[g] = summed

    vehicle_rows = [{k: v for k, v in payload.items() if k != "zones"} for payload in groups.values()]
    vehicle = _sum_records(vehicle_rows, SUM_KEYS) if vehicle_rows else None
    if vehicle:
        vehicle["LOverD"] = _ld(vehicle.get("downforceCoeff"), vehicle.get("Cd"))
    return {
        "format": parsed.get("format"),
        "direction": parsed.get("direction"),
        "file": parsed.get("file"),
        "groups": groups,
        "vehicle": vehicle,
        "excluded": excluded,
        "net": parsed.get("net"),
        "zoneCount": len(parsed.get("zones") or {}),
        "zones": parsed.get("zones") or {},
    }


def attach_shares(grouped: dict, cd_total: float, cl_total: float, downforce_total: float) -> dict:
    groups = grouped.get("groups") or {}
    vehicle = grouped.get("vehicle") or {}
    vehicle_cd = vehicle.get("Cd") or 0.0
    vehicle_df = vehicle.get("downforceCoeff") or 0.0
    drag_ref = vehicle_cd if abs(vehicle_cd) > 1e-12 else cd_total
    df_ref = vehicle_df if abs(vehicle_df) > 1e-12 else downforce_total

    out_groups = {}
    for name, g in groups.items():
        cd = g.get("Cd") or 0.0
        df = g.get("downforceCoeff") or 0.0
        rec = {
            "zones": g.get("zones"),
            "Fx": g.get("Fx"),
            "Fy": g.get("Fy"),
            "Fz": g.get("Fz"),
            "Cd": g.get("Cd"),
            "Cl": g.get("Cl"),
            "downforceCoeff": g.get("downforceCoeff"),
            "Cd_pressure": g.get("Cx_pressure", g.get("C_pressure")),
            "Cd_viscous": g.get("Cx_viscous", g.get("C_viscous")),
            "Cl_pressure": g.get("Cz_pressure"),
            "Cl_viscous": g.get("Cz_viscous"),
            "shareDragPct": round(100.0 * cd / drag_ref, 4) if abs(drag_ref) > 1e-12 else None,
            "shareDownforcePct": round(100.0 * df / df_ref, 4) if abs(df_ref) > 1e-12 else None,
            "LOverD": g.get("LOverD"),
        }
        out_groups[name] = rec

    cd_err = _rel_err(vehicle_cd, cd_total)
    cl_err = _rel_err(vehicle.get("Cl") or 0.0, cl_total)
    df_err = _rel_err(vehicle_df, downforce_total)
    ok = max(cd_err, cl_err, df_err) <= 0.01
    grouped["groups"] = out_groups
    grouped["checksum"] = {
        "vehicleCd": vehicle_cd,
        "vehicleCl": vehicle.get("Cl"),
        "vehicleDownforce": vehicle_df,
        "cdRelErr": round(cd_err, 6),
        "clRelErr": round(cl_err, 6),
        "downforceRelErr": round(df_err, 6),
        "tolerance": 0.01,
        "ok": ok,
        "note": "Porównanie sumy grup (bez domain_ground/domain_sky) do Cd_total/Cl_total. Fluent Net zawiera tunel.",
    }
    grouped["vehicle"] = {
        "Fx": vehicle.get("Fx"),
        "Fy": vehicle.get("Fy"),
        "Fz": vehicle.get("Fz"),
        "Cd": vehicle.get("Cd"),
        "Cl": vehicle.get("Cl"),
        "downforceCoeff": vehicle.get("downforceCoeff"),
        "LOverD": vehicle.get("LOverD"),
    }
    return grouped


def load_component_forces(paths: list[Path], cd_total: float | None = None, cl_total: float | None = None) -> dict | None:
    parsed_list = [parse_force_file(p) for p in paths if p.exists()]
    if not parsed_list:
        return None
    parsed_list.sort(key=lambda p: 0 if p.get("format") == "vector" else 1)
    chosen = parsed_list[0]
    grouped = group_zones(chosen)
    if cd_total is None:
        cd_total = (grouped.get("vehicle") or {}).get("Cd") or 0.0
    if cl_total is None:
        cl_total = (grouped.get("vehicle") or {}).get("Cl") or 0.0
    downforce_total = -cl_total if cl_total is not None else 0.0
    return attach_shares(grouped, cd_total, cl_total, downforce_total)
