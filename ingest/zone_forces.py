"""Everything the wall faces tell about the car, read straight from the solver files.

Pressure sits on every face. The stored SV_WALL_SHEAR is not usable: it points
against the flow (it is the force of the wall on the fluid) and is four to five
orders of magnitude too small to be pascals. Wall shear is therefore rebuilt from
the friction-velocity y+ and the distance of the first cell,
tau = mu^2 y+^2 / (rho y^2), pointing along the near-wall velocity relative to
the wall. With the face geometry from the case file that gives, per wall zone and
without starting Fluent: forces as the "Forces" report prints them, y+, reversed
near-wall flow, and how all of it is spread along the car.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ingest.wall_forces import GROUP_ORDER, group_for
from ingest.wall_state import AIR_MU, AIR_RHO, area_vectors, checked_layout, face_geometry, wall_state  # noqa: F401

STRIP_M = 0.1
STRIP_ORIGIN_M = -2.0
# Faces whose normal is mostly vertical. Only there "reversed in x" means separation.
HORIZONTAL = 0.5
REVERSE_SPEED_FRACTION = 0.01
YPLUS_BANDS = (("le1", 0.0, 1.0), ("1to5", 1.0, 5.0), ("5to30", 5.0, 30.0), ("30to300", 30.0, 300.0), ("gt300", 300.0, np.inf))


def _yplus_stats(state: dict) -> dict:
    yp, w = state["yplus"], state["magnitude"]
    total = float(w.sum())
    shares = {
        name: round(float(w[(yp >= lo) & (yp < hi)].sum() / total), 4) if total > 0 else None
        for name, lo, hi in YPLUS_BANDS
    }
    worst = int(np.argmax(yp))
    return {
        "median": round(float(np.median(yp)), 3),
        "p95": round(float(np.percentile(yp, 95)), 3),
        "max": round(float(yp[worst]), 2),
        "maxAtM": [round(float(v), 3) for v in state["centers"][worst]],
        "areaShare": shares,
    }


def _strip_index(x: np.ndarray) -> np.ndarray:
    return np.floor((x - STRIP_ORIGIN_M) / STRIP_M).astype(np.int64)


def _strip_x(index: int) -> float:
    return round(STRIP_ORIGIN_M + (index + 0.5) * STRIP_M, 3)


def _reverse_flow(state: dict, speed_ms: float) -> dict:
    """Share of the near-horizontal wall area where the first cell flows backwards."""
    w, n = state["magnitude"], state["normal"]
    horizontal = np.abs(n[:, 2]) > HORIZONTAL
    area_h = float(w[horizontal].sum())
    if area_h <= 0:
        return {"areaShare": None, "strips": []}
    reversed_ = horizontal & (state["uTan"][:, 0] < -REVERSE_SPEED_FRACTION * speed_ms)
    idx = _strip_index(state["centers"][:, 0])
    base = idx.min()
    size = int(idx.max() - base) + 1
    on_all = np.bincount(idx[horizontal] - base, weights=w[horizontal], minlength=size)
    on_rev = np.bincount(idx[reversed_] - base, weights=w[reversed_], minlength=size)
    strips = [
        {"x_m": _strip_x(int(base) + i), "areaM2": round(float(on_all[i]), 4), "reversedShare": round(float(on_rev[i] / on_all[i]), 3)}
        for i in range(size)
        if on_all[i] > 1e-4
    ]
    return {"areaShare": round(float(w[reversed_].sum() / area_h), 4), "horizontalAreaM2": round(area_h, 4), "strips": strips}


def zone_force_table(
    case: Path,
    *,
    rho: float,
    mu: float,
    speed_ms: float,
    aref_m2: float,
    cx_vector=(1.0, 0.0, 0.0),
    cz_vector=(0.0, 0.0, -1.0),
) -> dict:
    """Per-zone forces, y+, reversed flow and distribution along x from the .cas.h5 + .dat.h5 pair."""
    import h5py

    cas = next(case.rglob("*.cas.h5"))
    dat = next(case.rglob("*.dat.h5"))
    scale = 0.5 * rho * speed_ms**2 * aref_m2
    cx_dir = np.asarray(cx_vector, dtype=np.float64)
    cz_dir = np.asarray(cz_vector, dtype=np.float64)
    zones: dict[str, dict] = {}
    with h5py.File(cas, "r") as mesh, h5py.File(dat, "r") as data:
        for name, packed_at, a, b in checked_layout(mesh, data):
            state = wall_state(mesh, data, packed_at, a, b, rho=rho, mu=mu)
            f_pressure_face = -state["pressure"][:, None] * state["area"]
            f_viscous_face = state["tau"] * state["magnitude"][:, None]
            f_pressure = f_pressure_face.sum(axis=0)
            f_viscous = f_viscous_face.sum(axis=0)
            force_face = f_pressure_face + f_viscous_face
            idx = _strip_index(state["centers"][:, 0])
            base = int(idx.min())
            size = int(idx.max()) - base + 1
            drag = np.bincount(idx - base, weights=force_face @ cx_dir, minlength=size) / scale
            down = np.bincount(idx - base, weights=force_face @ cz_dir, minlength=size) / scale
            zones[name] = {
                "faces": b - a + 1,
                "areaM2": float(state["magnitude"].sum()),
                "F": [float(v) for v in f_pressure + f_viscous],
                "Fpressure": [float(v) for v in f_pressure],
                "Fviscous": [float(v) for v in f_viscous],
                "group": group_for(name),
                "yplus": _yplus_stats(state),
                "reverseFlow": _reverse_flow(state, speed_ms),
                "strips": [
                    {"x_m": _strip_x(base + i), "Cd": round(float(drag[i]), 5), "downforceCoeff": round(float(down[i]), 5)}
                    for i in range(size)
                    if abs(drag[i]) > 1e-7 or abs(down[i]) > 1e-7
                ],
            }
    return _coefficients(zones, scale, cx_dir, cz_dir)


def _coefficients(zones: dict, scale: float, cx_dir, cz_dir) -> dict:
    """Turn the forces in newtons into coefficients. `scale` is q * Aref."""
    for rec in zones.values():
        total = np.asarray(rec["F"])
        pressure = np.asarray(rec["Fpressure"])
        viscous = np.asarray(rec["Fviscous"])
        rec["Cd"] = float(total @ cx_dir / scale)
        rec["Cd_pressure"] = float(pressure @ cx_dir / scale)
        rec["Cd_viscous"] = float(viscous @ cx_dir / scale)
        rec["downforceCoeff"] = float(total @ cz_dir / scale)
        rec["downforce_pressure"] = float(pressure @ cz_dir / scale)
        rec["downforce_viscous"] = float(viscous @ cz_dir / scale)
    return zones


def group_table(zones: dict) -> dict:
    """Sum zones into the same groups the Fluent-dump path uses."""
    groups: dict[str, dict] = {}
    for name, rec in zones.items():
        group = rec.get("group")
        if group is None:
            continue
        slot = groups.setdefault(
            group,
            {"zones": [], "Cd": 0.0, "downforceCoeff": 0.0, "Cd_pressure": 0.0, "Cd_viscous": 0.0, "areaM2": 0.0},
        )
        slot["zones"].append(name)
        for key in ("Cd", "downforceCoeff", "Cd_pressure", "Cd_viscous", "areaM2"):
            slot[key] += rec[key]
    order = [g for g in GROUP_ORDER if g in groups] + [g for g in groups if g not in GROUP_ORDER]
    return {g: groups[g] for g in order}


def strips_by_group(zones: dict) -> dict:
    """Drag and downforce of each group per 10 cm strip along the car."""
    acc: dict[str, dict[float, list[float]]] = {}
    for rec in zones.values():
        group = rec.get("group")
        if group is None:
            continue
        slot = acc.setdefault(group, {})
        for strip in rec.get("strips") or []:
            pair = slot.setdefault(strip["x_m"], [0.0, 0.0])
            pair[0] += strip["Cd"]
            pair[1] += strip["downforceCoeff"]
    return {
        group: [{"x_m": x, "Cd": round(v[0], 5), "downforceCoeff": round(v[1], 5)} for x, v in sorted(slot.items())]
        for group, slot in acc.items()
    }


def with_checksum(zones: dict, cd_total: float | None, downforce_total: float | None) -> dict:
    """Group sums plus the comparison with the monitor values for the whole car."""
    groups = group_table(zones)
    vehicle_cd = sum(g["Cd"] for g in groups.values())
    vehicle_df = sum(g["downforceCoeff"] for g in groups.values())
    for g in groups.values():
        g["shareDragPct"] = round(100.0 * g["Cd"] / vehicle_cd, 2) if abs(vehicle_cd) > 1e-12 else None
        g["shareDownforcePct"] = round(100.0 * g["downforceCoeff"] / vehicle_df, 2) if abs(vehicle_df) > 1e-12 else None
    checksum = {
        "vehicleCd": vehicle_cd,
        "vehicleDownforce": vehicle_df,
        "monitorCd": cd_total,
        "monitorDownforce": downforce_total,
        "tolerance": 0.01,
    }
    for key, mine, ref in (("cdRelErr", vehicle_cd, cd_total), ("downforceRelErr", vehicle_df, downforce_total)):
        checksum[key] = None if not ref else round(abs(mine - ref) / abs(ref), 6)
    errors = [checksum[k] for k in ("cdRelErr", "downforceRelErr") if checksum[k] is not None]
    checksum["ok"] = bool(errors) and max(errors) <= checksum["tolerance"]
    return {
        "groups": groups,
        "vehicle": {"Cd": vehicle_cd, "downforceCoeff": vehicle_df},
        "checksum": checksum,
        "strips": strips_by_group(zones),
    }


def write_zone_forces(case: Path, out: Path, **kwargs) -> dict:
    totals = {k: kwargs.pop(k, None) for k in ("cd_total", "downforce_total")}
    zones = zone_force_table(case, **kwargs)
    result = {"zones": zones, **with_checksum(zones, totals["cd_total"], totals["downforce_total"])}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
