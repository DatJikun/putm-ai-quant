"""Residual history and mass balance read from the solver files.

Both come from the .dat.h5: residuals are stored per iteration (value and its
normalisation), and Fluent keeps the mass flux of every face, so the balance of
the boundaries and the flow through the radiator are plain sums.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from ingest.h5_mesh import text_of as _text

# Fluent's default convergence criterion for every scaled residual.
RESIDUAL_LIMIT = 1e-3
# Relative mass imbalance above which the case does not close.
IMBALANCE_LIMIT = 1e-3
INTERIOR, WALL, SYMMETRY = 2, 3, 7
EQUATION_ORDER = ("continuity", "x-velocity", "y-velocity", "z-velocity", "k", "epsilon", "omega")


def scaled_residuals(rows: np.ndarray) -> np.ndarray:
    """Scaled residual per iteration: value divided by its normalisation."""
    rows = np.asarray(rows, dtype=np.float64)
    norm = np.where(rows[:, 1] > 0, rows[:, 1], np.nan)
    return rows[:, 0] / norm


def _trend(iterations: np.ndarray, scaled: np.ndarray, window: int) -> dict:
    """Slope of log10(residual) over the last `window` iterations, per 100 iterations."""
    keep = np.isfinite(scaled) & (scaled > 0)
    iterations, scaled = iterations[keep], scaled[keep]
    if iterations.size < 10:
        return {"window": 0, "log10Per100": None, "verdict": "brak danych"}
    cut = iterations >= iterations[-1] - window
    x, y = iterations[cut], np.log10(scaled[cut])
    if x.size < 10:
        x, y = iterations, np.log10(scaled)
    slope = float(np.polyfit(x, y, 1)[0] * 100.0)
    if slope < -0.1:
        verdict = "spada"
    elif slope > 0.1:
        verdict = "rośnie"
    else:
        verdict = "płaskie"
    return {"window": int(x[-1] - x[0]), "log10Per100": round(slope, 3), "verdict": verdict}


def summarize_residuals(history: dict[str, tuple[np.ndarray, np.ndarray]], window: int = 200) -> dict:
    """history: equation -> (iterations, rows[n, 4]). Returns one record per equation."""
    equations = {}
    for name in sorted(history, key=lambda n: EQUATION_ORDER.index(n) if n in EQUATION_ORDER else 99):
        iterations, rows = history[name]
        scaled = scaled_residuals(rows)
        finite = scaled[np.isfinite(scaled) & (scaled > 0)]
        if finite.size == 0:
            continue
        final = float(scaled[np.isfinite(scaled)][-1])
        equations[name] = {
            "final": final,
            "belowLimit": bool(final <= RESIDUAL_LIMIT),
            "ordersDropped": round(math.log10(float(finite[: max(1, min(5, finite.size))].max()) / final), 2)
            if final > 0
            else None,
            "trend": _trend(np.asarray(iterations, dtype=np.float64), scaled, window),
        }
    over = [n for n, rec in equations.items() if not rec["belowLimit"]]
    return {
        "iterations": int(max(np.asarray(it)[-1] for it, _ in history.values())) if history else 0,
        "limit": RESIDUAL_LIMIT,
        "equations": equations,
        "allBelowLimit": bool(equations) and not over,
        "aboveLimit": over,
    }


def read_residuals(dat_path: Path) -> dict | None:
    import h5py

    with h5py.File(dat_path, "r") as data:
        if "results/residuals/phase-1" not in data:
            return None
        group = data["results/residuals/phase-1"]
        history = {
            name: (group[name]["iterations"][:], group[name]["data"][:])
            for name in group
            if "data" in group[name]
        }
    return summarize_residuals(history) if history else None


def mass_balance_from_zones(zones: list[dict], limit: float = IMBALANCE_LIMIT) -> dict:
    """zones: {name, type, flux} with flux = sum of the face mass flux, outward positive."""
    boundary = [z for z in zones if z["type"] not in (INTERIOR, WALL, SYMMETRY)]
    inflow = -sum(z["flux"] for z in boundary if z["flux"] < 0)
    outflow = sum(z["flux"] for z in boundary if z["flux"] > 0)
    net = sum(z["flux"] for z in boundary)
    relative = abs(net) / inflow if inflow > 0 else None
    return {
        "inflowKgS": inflow,
        "outflowKgS": outflow,
        "netKgS": net,
        "relativeImbalance": relative,
        "limit": limit,
        "closes": None if relative is None else bool(relative <= limit),
        "zones": [
            {"name": z["name"], "fluxKgS": z["flux"]} for z in boundary if abs(z["flux"]) > 0
        ],
    }


def _porous_flows(zones: list[dict]) -> dict:
    """Mass flow through the radiator core and the fan, from their child (shadow) zones."""
    out = {}
    for key, token in (("radiatorKgS", "radiator_core"), ("fanKgS", "mrf_fan")):
        sides = [abs(z["flux"]) for z in zones if token in z["name"] and z["name"].count(":") >= 1 and z["type"] == INTERIOR]
        out[key] = float(np.mean(sides)) if sides else None
    return out


def read_mass_balance(cas_path: Path, dat_path: Path) -> dict | None:
    import h5py

    with h5py.File(cas_path, "r") as mesh, h5py.File(dat_path, "r") as data:
        flux_path = "results/1/phase-1/faces/SV_FLUX/1"
        if flux_path not in data:
            return None
        flux = data[flux_path]
        top = mesh["meshes/1/faces/zoneTopology"]
        names = _text(top["name"][()]).split(";")
        zones = []
        for name, kind, a, b in zip(names, top["zoneType"][()], top["minId"][()], top["maxId"][()]):
            zones.append(
                {
                    "name": name,
                    "type": int(kind),
                    "flux": float(np.asarray(flux[int(a) - 1 : int(b)], dtype=np.float64).sum()),
                }
            )
    balance = mass_balance_from_zones(zones)
    balance.update(_porous_flows(zones))
    balance["note"] = (
        "Strumień masy liczony na połowę auta. Bilans to suma po brzegach domeny "
        "(wlot, wylot); ściany i symetria nie przepuszczają. "
        "Przepływ przez chłodnicę i wentylator to średnia z ich dwóch stron."
    )
    return balance


def conservation_report(case: Path) -> dict:
    cas = next(case.rglob("*.cas.h5"), None)
    dat = next(case.rglob("*.dat.h5"), None)
    out: dict = {"residuals": None, "massBalance": None, "missing": []}
    if dat is None:
        out["missing"].append("Brak .dat.h5 — nie ma residuów ani strumieni masy.")
        return out
    out["residuals"] = read_residuals(dat)
    if out["residuals"] is None:
        out["missing"].append("W .dat.h5 nie ma historii residuów.")
    if cas is None:
        out["missing"].append("Brak .cas.h5 — nie da się przypisać strumieni do stref.")
    else:
        out["massBalance"] = read_mass_balance(cas, dat)
        if out["massBalance"] is None:
            out["missing"].append("W .dat.h5 nie ma strumienia masy (SV_FLUX).")
    return out


def write_conservation(case: Path, out: Path) -> dict:
    data = conservation_report(case)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
