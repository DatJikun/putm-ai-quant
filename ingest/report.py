"""One command, one case folder, one report. Nothing to type in and nothing to click.

`build_report` runs the whole ingest on a case: the pack, residuals and mass balance,
the forces per part rebuilt from the solver files, y+ and reversed flow on the walls.
It then grades the case with simple traffic lights and lists what is missing, so
that a forgotten file shows up as red and not as a quietly empty field.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ingest.chatbot_brief import write_brief
from ingest.conservation import conservation_report
from ingest.pack import build_pack

OK, WARN, BAD, NONE = "ok", "uwaga", "zle", "brak"
LIGHT = {OK: "🟢 OK", WARN: "🟡 UWAGA", BAD: "🔴 ŹLE", NONE: "⚪ BRAK DANYCH"}

# Thresholds. Plain numbers so that anyone can change them in one place.
FORCE_DRIFT_BAD_PCT = 2.0
RESIDUAL_BAD = 1e-2
MASS_IMBALANCE_OK = 1e-3
CHECKSUM_OK, CHECKSUM_WARN = 0.01, 0.03
ORTHO_OK, ORTHO_WARN = 0.1, 0.01
YPLUS_RESOLVED_OK, YPLUS_RESOLVED_WARN = 0.9, 0.6
YPLUS_WALL_FN_OK, YPLUS_WALL_FN_WARN = 0.8, 0.5
SURFACE_GROUPS = ("fw", "rw", "floor", "body")
PART_NAMES = {
    "fw": "przednie skrzydło",
    "rw": "tylne skrzydło",
    "floor": "podłoga i dyfuzor",
    "body": "kokpit i nadwozie",
    "wheels": "koła",
    "cooling": "chłodnica i wentylator",
    "other": "pozostałe",
}


def _get(data, *path):
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def references(pack: dict) -> dict | None:
    """rho, mu, speed and Aref of the case, or None when one of them is not known."""
    refs = _get(pack, "kpis", "references") or {}
    values = {
        "rho": _num(_get(refs, "rho", "value")),
        "mu": _num(_get(refs, "mu", "value")),
        "speed_ms": _num(_get(refs, "speedMs", "value")),
        "aref_m2": _num(_get(refs, "frontalAreaM2", "value")),
    }
    return values if all(v for v in values.values()) else None


# ---------------------------------------------------------------- wall analysis

def wall_analysis(case_root: Path, pack: dict) -> dict | None:
    """Forces per zone and group, y+ and reversed flow from the .cas.h5/.dat.h5."""
    if not (list(case_root.rglob("*.cas.h5")) and list(case_root.rglob("*.dat.h5"))):
        return None
    refs = references(pack)
    if refs is None:
        return None
    from ingest.zone_forces import with_checksum, zone_force_table

    kpis = pack.get("kpis") or {}
    zones = zone_force_table(
        case_root,
        rho=refs["rho"],
        mu=refs["mu"],
        speed_ms=refs["speed_ms"],
        aref_m2=refs["aref_m2"],
        cx_vector=kpis.get("cxForceVector") or (1.0, 0.0, 0.0),
        cz_vector=kpis.get("czForceVector") or (0.0, 0.0, -1.0),
    )
    summary = with_checksum(zones, kpis.get("Cd"), kpis.get("downforceCoeff"))
    summary["zones"] = zones
    summary["groupYplus"] = group_yplus(zones)
    return summary


def group_yplus(zones: dict) -> dict:
    """Area-weighted share of every y+ band on the aerodynamic surfaces, per group and for all."""
    totals: dict[str, dict] = {}
    for name, rec in zones.items():
        group = rec.get("group")
        if group not in SURFACE_GROUPS:
            continue
        shares = _get(rec, "yplus", "areaShare") or {}
        for key in (group, "all"):
            slot = totals.setdefault(key, {"area": 0.0, "bands": {}, "max": 0.0, "median": []})
            slot["area"] += rec["areaM2"]
            slot["max"] = max(slot["max"], _get(rec, "yplus", "max") or 0.0)
            slot["median"].append((_get(rec, "yplus", "median") or 0.0, rec["areaM2"]))
            for band, share in shares.items():
                if share is not None:
                    slot["bands"][band] = slot["bands"].get(band, 0.0) + share * rec["areaM2"]
    out = {}
    for key, slot in totals.items():
        area = slot["area"]
        if area <= 0:
            continue
        out[key] = {
            "areaM2": round(area, 3),
            "shares": {band: round(value / area, 4) for band, value in slot["bands"].items()},
            "max": round(slot["max"], 1),
            "median": round(sum(m * a for m, a in slot["median"]) / area, 2),
        }
    return out


def components_from_walls(walls: dict, speed_ms: float, aref_m2: float, rho: float) -> dict:
    """`kpis.components` in the shape the UI, `diff` and the chatbot brief already read."""
    scale = 0.5 * rho * speed_ms**2 * aref_m2
    groups = {}
    zones = walls["zones"]
    for name, rec in walls["groups"].items():
        members = [zones[z] for z in rec["zones"]]
        force = [sum(m["F"][i] for m in members) for i in range(3)]
        cd, df = rec["Cd"], rec["downforceCoeff"]
        groups[name] = {
            "zones": rec["zones"],
            "Fx": force[0],
            "Fy": force[1],
            "Fz": force[2],
            "Cd": cd,
            "Cl": -df,
            "downforceCoeff": df,
            "Cd_pressure": rec["Cd_pressure"],
            "Cd_viscous": rec["Cd_viscous"],
            "Cl_pressure": -sum(m["downforce_pressure"] for m in members),
            "Cl_viscous": -sum(m["downforce_viscous"] for m in members),
            "shareDragPct": rec["shareDragPct"],
            "shareDownforcePct": rec["shareDownforcePct"],
            "LOverD": df / cd if abs(cd) > 1e-12 else None,
        }
    check = walls["checksum"]
    vehicle = walls["vehicle"]
    return {
        "source": "obliczone z .cas.h5 i .dat.h5 (bez Fluenta)",
        "excluded": [name for name, rec in zones.items() if rec.get("group") is None],
        "groups": groups,
        "vehicle": {
            "Cd": vehicle["Cd"],
            "Cl": -vehicle["downforceCoeff"],
            "downforceCoeff": vehicle["downforceCoeff"],
            "LOverD": vehicle["downforceCoeff"] / vehicle["Cd"] if abs(vehicle["Cd"]) > 1e-12 else None,
        },
        "checksum": {
            "vehicleCd": check["vehicleCd"],
            "vehicleCl": -check["vehicleDownforce"],
            "vehicleDownforce": check["vehicleDownforce"],
            "cdRelErr": check["cdRelErr"],
            "clRelErr": check["downforceRelErr"],
            "downforceRelErr": check["downforceRelErr"],
            "tolerance": check["tolerance"],
            "ok": check["ok"],
            "note": "Suma sił z plików wyników (bez domain_*) kontra monitory Cd i Cl z solvera.",
        },
        "scale": scale,
    }


def attach_walls(pack: dict, walls: dict) -> None:
    """Put the forces per part into the pack so the UI, `diff` and the brief see them."""
    refs = references(pack)
    kpis = pack["kpis"]
    kpis["components"] = components_from_walls(walls, refs["speed_ms"], refs["aref_m2"], refs["rho"])
    kpis["wallZones"] = {
        name: {
            "group": rec["group"],
            "Fx": rec["F"][0],
            "Fy": rec["F"][1],
            "Fz": rec["F"][2],
            "Cd": rec["Cd"],
            "Cl": -rec["downforceCoeff"],
            "downforceCoeff": rec["downforceCoeff"],
            "Cd_pressure": rec["Cd_pressure"],
            "Cd_viscous": rec["Cd_viscous"],
            "Cl_pressure": -rec["downforce_pressure"],
            "Cl_viscous": -rec["downforce_viscous"],
        }
        for name, rec in walls["zones"].items()
        if rec.get("group")
    }
    pack["warnings"] = [w for w in pack.get("warnings", []) if not w.startswith("Monitor cz ma per-zone")]


# ---------------------------------------------------------------------- checks

def _check(cid: str, title: str, status: str, value: str, detail: str) -> dict:
    return {"id": cid, "title": title, "status": status, "value": value, "detail": detail}


def check_force_convergence(pack: dict) -> dict:
    conv = _get(pack, "kpis", "convergence") or {}
    settled = conv.get("settled")
    if settled is None:
        return _check("zbieznosc-sil", "Siły się ustabilizowały", NONE, "brak", "Brak monitorów cx, cz, cm albo ich historii.")
    drifts = {k: _num(_get(conv, k, "driftPct")) for k in ("cx", "cz", "cm")}
    shown = ", ".join(f"{k} {v:+.2f}%" for k, v in drifts.items() if v is not None)
    window = conv.get("windowIterations")
    detail = f"Zmiana w ostatnich {window} iteracjach: {shown}." if window else shown
    if settled:
        return _check("zbieznosc-sil", "Siły się ustabilizowały", OK, shown, detail)
    worst = max([abs(v) for k, v in drifts.items() if v is not None and k != "cm"] or [0.0])
    status = BAD if worst > FORCE_DRIFT_BAD_PCT else WARN
    return _check(
        "zbieznosc-sil",
        "Siły się ustabilizowały",
        status,
        shown,
        detail + " Siły jeszcze się zmieniają, więc wynik nie jest ostateczny.",
    )


def check_residuals(conservation: dict) -> dict:
    res = conservation.get("residuals")
    if not res:
        return _check("residua", "Residua poniżej 1e-3", NONE, "brak", "Brak historii residuów w .dat.h5.")
    eq = res["equations"]
    worst_name = max(eq, key=lambda n: eq[n]["final"])
    worst = eq[worst_name]["final"]
    value = f"najgorsze: {worst_name} {worst:.1e}"
    flat = [n for n in res["aboveLimit"] if eq[n]["trend"]["verdict"] != "spada"]
    if res["allBelowLimit"]:
        return _check("residua", "Residua poniżej 1e-3", OK, value, "Wszystkie równania są poniżej limitu 1e-3.")
    status = BAD if worst > RESIDUAL_BAD else WARN
    over = ", ".join(f"{n} {eq[n]['final']:.1e}" for n in res["aboveLimit"])
    note = " Nie spadają już, są płaskie." if flat else ""
    return _check("residua", "Residua poniżej 1e-3", status, value, f"Powyżej limitu: {over}.{note}")


def check_mass_balance(conservation: dict) -> dict:
    mb = conservation.get("massBalance")
    if not mb or mb.get("relativeImbalance") is None:
        return _check("bilans-masy", "Bilans masy się domyka", NONE, "brak", "Brak strumienia masy w .dat.h5.")
    rel = mb["relativeImbalance"]
    detail = f"Wlot {mb['inflowKgS']:.3f} kg/s, wylot {mb['outflowKgS']:.3f} kg/s (połowa auta)."
    if mb.get("radiatorKgS") is not None:
        detail += f" Przez chłodnicę płynie {mb['radiatorKgS']:.3f} kg/s."
    status = OK if rel <= MASS_IMBALANCE_OK else BAD
    return _check("bilans-masy", "Bilans masy się domyka", status, f"{rel:.1e}", detail)


def check_checksum(walls: dict | None) -> dict:
    if walls is None:
        return _check("suma-sil", "Siły na części sumują się do monitorów", NONE, "brak", "Brak plików .cas.h5/.dat.h5, więc nie policzono sił na części.")
    c = walls["checksum"]
    errs = [e for e in (c.get("cdRelErr"), c.get("downforceRelErr")) if e is not None]
    if not errs:
        return _check("suma-sil", "Siły na części sumują się do monitorów", NONE, "brak", "Brak monitorów Cd i Cl do porównania.")
    worst = max(errs)
    status = OK if worst <= CHECKSUM_OK else WARN if worst <= CHECKSUM_WARN else BAD
    detail = (
        f"Opór różni się o {100 * (c['cdRelErr'] or 0):.2f}%, docisk o {100 * (c['downforceRelErr'] or 0):.2f}%. "
        "Pliki wyników to stan z ostatniej iteracji, monitory to średnia z okna, więc przy niedokończonym liczeniu pewna różnica jest normalna."
    )
    return _check("suma-sil", "Siły na części sumują się do monitorów", status, f"{100 * worst:.2f}%", detail)


def check_yplus(pack: dict, walls: dict | None) -> dict:
    title = "y+ pasuje do modelu turbulencji"
    stats = _get(walls or {}, "groupYplus", "all")
    if not stats:
        return _check("yplus", title, NONE, "brak", "Brak pól y+ w plikach wyników.")
    treatment = str(_get(pack, "methods", "wallTreatment") or "").lower()
    model = str(_get(pack, "methods", "turbulence") or "")
    shares = stats["shares"]
    low = shares.get("le1", 0.0) + shares.get("1to5", 0.0)
    value = f"mediana {stats['median']}, max {stats['max']}"
    worst_zone = max(
        (z for z in walls["zones"].items() if z[1].get("group") in SURFACE_GROUPS),
        key=lambda item: _get(item[1], "yplus", "max") or 0.0,
        default=None,
    )
    where = ""
    if worst_zone:
        at = _get(worst_zone[1], "yplus", "maxAtM")
        peak = _get(worst_zone[1], "yplus", "max")
        if at:
            where = f" Największe y+ ({peak}) jest na {worst_zone[0]}, w punkcie x={at[0]}, y={at[1]}, z={at[2]} m."
    if "bez funkcji" in treatment:
        status = OK if low >= YPLUS_RESOLVED_OK else WARN if low >= YPLUS_RESOLVED_WARN else BAD
        return _check("yplus", title, status, value, f"{model}: siatka sięga do samej ściany, potrzebne y+ poniżej ok. 5. Tyle powierzchni mieści się w tym zakresie: {100 * low:.0f}%.{where}")
    if "enhanced" in treatment:
        fine = 1.0 - shares.get("gt300", 0.0)
        status = OK if fine >= 0.95 else WARN
        return _check("yplus", title, status, value, f"{model} z Enhanced Wall Treatment toleruje każde y+ do ok. 300. W zakresie: {100 * fine:.0f}% powierzchni. Przy y+ 5–30 ściana jest modelowana mniej dokładnie ({100 * shares.get('5to30', 0):.0f}% powierzchni).{where}")
    if treatment:
        good = shares.get("30to300", 0.0)
        status = OK if good >= YPLUS_WALL_FN_OK else WARN if good >= YPLUS_WALL_FN_WARN else BAD
        return _check("yplus", title, status, value, f"{model} z funkcją ściany wymaga y+ 30–300. W zakresie: {100 * good:.0f}% powierzchni.{where}")
    return _check("yplus", title, NONE, value, "Nie wiadomo, jakiego traktowania ściany użyto, więc nie da się ocenić y+.")


def check_mesh_quality(pack: dict) -> dict:
    title = "Jakość siatki"
    ortho = _num(_get(pack, "mesh", "minOrthogonalQuality"))
    cells = _num(_get(pack, "mesh", "cells"))
    if ortho is None:
        return _check("siatka", title, NONE, "brak", "Brak transkryptu siatki, więc nie znamy jakości najgorszej komórki.")
    status = OK if ortho >= ORTHO_OK else WARN if ortho >= ORTHO_WARN else BAD
    aspect = _num(_get(pack, "mesh", "maxAspectRatio"))
    detail = (f"{int(cells):,}".replace(",", " ") + " komórek. ") if cells else ""
    detail += f"Najgorsza komórka ma jakość ortogonalną {ortho}"
    if aspect:
        detail += f", największe wydłużenie {aspect:.0f}"
    return _check("siatka", title, status, f"{ortho:.3f}", detail + ". Zalecane powyżej 0,1.")


def check_boundary_layers(pack: dict) -> dict:
    title = "Warstwy przyścienne w aktualnym stanie"
    bl = _get(pack, "mesh", "boundaryLayers")
    if not bl:
        return _check("warstwy", title, NONE, "brak", "Brak pliku .wft, więc nie znamy przepisu na warstwy przyścienne.")
    stale = bl.get("staleControls") or []
    if stale:
        return _check("warstwy", title, WARN, f"nieaktualne: {', '.join(stale)}", "Przepis w .wft jest oznaczony jako nieaktualny. To zapis ustawień, a nie pomiar warstw w gotowej siatce.")
    return _check("warstwy", title, OK, "aktualne", "Przepis na warstwy jest zgodny z siatką.")


def check_run_health(pack: dict) -> dict:
    title = "Liczenie przeszło bez awarii"
    sessions = _get(pack, "methods", "solverSessions") or []
    conv = _get(pack, "kpis", "convergence") or {}
    if not sessions:
        return _check("przebieg", title, NONE, "brak", "Brak transkryptów solvera.")
    last = next((s for s in reversed(sessions) if s.get("lastIteration")), None)
    crashed = [s["file"] for s in sessions if s.get("crashed")]
    if last and last.get("crashed"):
        return _check("przebieg", title, BAD, "ostatnia sesja padła", f"Ostatnia sesja ({last['file']}) skończyła się awarią.")
    notes = []
    if conv.get("stoppedEarly"):
        notes.append(f"Liczenie zatrzymano przed planem: brakuje {conv.get('iterationsLeft')} z {conv.get('plannedIterations')} iteracji.")
    if crashed:
        notes.append(f"Wcześniejsze sesje z awarią: {len(crashed)}.")
    if notes:
        return _check("przebieg", title, WARN, f"{len(sessions)} sesji", " ".join(notes))
    return _check("przebieg", title, OK, f"{len(sessions)} sesji", "Brak awarii i przedwczesnego zatrzymania.")


def check_force_convention(pack: dict) -> dict:
    title = "Znak sił potwierdzony w case"
    verified = _get(pack, "kpis", "forceVectorVerified")
    if verified is None:
        return _check("znak-sil", title, NONE, "brak", "Nie odczytano wektorów sił z .cas.")
    return _check("znak-sil", title, OK if verified else WARN, "tak" if verified else "nie", "Wektory sił cx i cz odczytane z definicji raportów w case." if verified else "Znak docisku nie jest potwierdzony.")


def evaluate_checks(pack: dict, conservation: dict, walls: dict | None) -> list[dict]:
    return [
        check_force_convergence(pack),
        check_residuals(conservation),
        check_mass_balance(conservation),
        check_checksum(walls),
        check_yplus(pack, walls),
        check_mesh_quality(pack),
        check_boundary_layers(pack),
        check_run_health(pack),
        check_force_convention(pack),
    ]


def overall(checks: list[dict]) -> dict:
    statuses = {c["status"] for c in checks}
    bad = [c["title"] for c in checks if c["status"] == BAD]
    warn = [c["title"] for c in checks if c["status"] == WARN]
    none = [c["title"] for c in checks if c["status"] == NONE]
    if BAD in statuses:
        label = "Nie ufać wynikom bez poprawki"
    elif WARN in statuses:
        label = "Wyniki orientacyjne, są zastrzeżenia"
    else:
        label = "Wyniki wiarygodne"
    return {"status": BAD if bad else WARN if warn else OK, "label": label, "bad": bad, "warn": warn, "missing": none}


def missing_data(pack: dict, conservation: dict, walls: dict | None) -> list[str]:
    """Everything the report could not fill in, worded as what to do about it."""
    gaps = []
    files = pack.get("files") or {}
    if not files.get("cas"):
        gaps.append("Brak pliku .cas: nie ma ustawień solvera ani definicji raportów.")
    if not files.get("dat"):
        gaps.append("Brak pliku .dat: nie ma pól do analizy ani residuów.")
    if not files.get("transcripts"):
        gaps.append("Brak logu solvera (.trn): nie znamy jakości siatki, awarii ani przebiegu liczenia.")
    if not _get(pack, "monitors", "monitors"):
        gaps.append("Brak monitorów cx, cz, cm (pliki -rfile.out): nie da się ocenić zbieżności sił.")
    if not files.get("cad"):
        gaps.append("Brak geometrii STEP: wymiary skrzydeł pochodzą z szablonu, a nie z tego bolidu.")
    if not _get(pack, "mesh", "boundaryLayers"):
        gaps.append("Brak pliku .wft: nie znamy przepisu na warstwy przyścienne.")
    if not files.get("journals"):
        gaps.append("Brak journala .jou: ustawień nie da się odtworzyć 1:1, są tylko zapisane w logu.")
    if not _get(pack, "images", "total"):
        gaps.append("Brak zdjęć z CFD-Post: nie ma indeksu klatek.")
    if _get(pack, "mesh", "minOrthogonalQuality") is None:
        gaps.append("Brak jakości siatki: potrzebny transkrypt generowania siatki.")
    if not _get(pack, "methods", "turbulence"):
        gaps.append("Nie odczytano modelu turbulencji.")
    if walls is None:
        gaps.append("Nie policzono sił na części bolidu: brak .cas.h5/.dat.h5 lub brak wartości odniesienia (V, ρ, μ, Aref).")
    gaps.extend(conservation.get("missing") or [])
    return gaps


# ------------------------------------------------------------------- flow field

def flow_analysis(case_root: Path, pack: dict, cache_dir: Path) -> dict | None:
    """Station-by-station scan of the flow: losses, vortices, wheel wakes, reversed flow."""
    if not (list(case_root.rglob("*.cas.h5")) and list(case_root.rglob("*.dat.h5"))):
        return None
    refs = references(pack)
    if refs is None:
        return None
    from ingest.flow_field import scan_stations

    return scan_stations(
        case_root,
        rho=refs["rho"],
        speed_ms=refs["speed_ms"],
        wheels=_get(pack, "methods", "wheelRotation"),
        cache_dir=cache_dir,
    )


def loss_growth(flow: dict, walls: dict | None, top: int = 4) -> list[dict]:
    """The x intervals where the total-pressure loss grows most, and which part makes drag there."""
    stations = [s for s in flow["stations"] if s.get("lossIntegralM2") is not None]
    steps = []
    for a, b in zip(stations, stations[1:]):
        steps.append({"fromX_m": a["x_m"], "toX_m": b["x_m"], "growthM2": round(b["lossIntegralM2"] - a["lossIntegralM2"], 4)})
    steps.sort(key=lambda r: -r["growthM2"])
    strips = (walls or {}).get("strips") or {}
    for step in steps[:top]:
        centre = (step["fromX_m"] + step["toX_m"]) / 2
        best, best_cd = None, 0.0
        for group, rows in strips.items():
            for row in rows:
                if abs(row["x_m"] - centre) < 0.051 and abs(row["Cd"]) > abs(best_cd):
                    best, best_cd = group, row["Cd"]
        step["dragMostlyFrom"] = PART_NAMES.get(best, best) if best else None
    return steps[:top]


def _flow_section(flow: dict | None, walls: dict | None) -> list[str]:
    lines = ["## Przepływ wokół bolidu", ""]
    if flow is None:
        return lines + ["Nie policzono (brak plików wyników).", ""]
    stations = flow["stations"]
    lossy = [s for s in stations if s.get("lossIntegralM2") is not None]
    lines += [
        "Przekroje w poprzek auta co 10 cm, policzone z komórek solvera (to zastępuje oglądanie zdjęć). "
        "Strata to ubytek ciśnienia całkowitego: tam, gdzie powietrze straciło energię, rośnie. Jednostka m² to „pole straty”.",
        "",
    ]
    if lossy:
        last = lossy[-1]
        lines += [f"Za bolidem (x = {last['x_m']:.1f} m) całkowita strata to {last['lossIntegralM2']:.2f} m², a ślad zajmuje {last['lossAreaM2']:.2f} m².", ""]
    growth = loss_growth(flow, walls)
    if growth:
        lines += ["Tu strata rośnie najbardziej (czyli tu powietrze oddaje najwięcej energii):", ""]
        for g in growth:
            by = f", największy opór w tym pasie robi: {g['dragMostlyFrom']}" if g.get("dragMostlyFrom") else ""
            lines.append(f"- x = {g['fromX_m']:.1f} do {g['toX_m']:.1f} m: +{g['growthM2']:.3f} m²{by}")
        lines.append("")
    tracks = flow.get("vortexTracks") or []
    if tracks:
        lines += [
            "Najsilniejsze wiry (cyrkulacja w m²/s, im większa, tym silniejszy wir; widok z przodu auta):",
            "",
            "| Skąd dokąd (x) | Gdzie powstaje | Kręci się | Najsilniejszy przy x | Cyrkulacja | Start y, z → koniec y, z |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for t in tracks[:6]:
            lines.append(
                f"| {t['fromX_m']:.1f} → {t['toX_m']:.1f} m | {t.get('region', '')} | {t['turn']} | {t['strongestAtX_m']:.1f} m | "
                f"{abs(t['peakCirculationM2s']):.2f} | ({t['start']['y_m']:.2f}, {t['start']['z_m']:.2f}) → ({t['end']['y_m']:.2f}, {t['end']['z_m']:.2f}) |"
            )
        lines.append("")
    wake_lines = []
    for name, label in (("front", "przednim"), ("rear", "tylnym")):
        rows = [(s["x_m"], s["wheels"][name]) for s in stations if name in (s.get("wheels") or {})]
        if not rows:
            continue
        worst = max(rows, key=lambda r: r[1]["lossIntegralM2"])
        wake_lines.append(
            f"- za kołem {label}: największa strata w oknie koła {worst[1]['lossIntegralM2']:.3f} m² przy x = {worst[0]:.1f} m, "
            f"szerokość śladu {worst[1]['widthM']:.2f} m, najniższe Cpt {worst[1]['minCpt']}"
        )
    if wake_lines:
        lines += ["Ślady za kołami (okno ±35 cm wokół koła, do wysokości 60 cm):", ""] + wake_lines + [""]
    back = [s for s in stations if (s.get("reverseFlowAreaM2") or 0) > 0.03]
    if back:
        worst = max(back, key=lambda s: s["reverseFlowAreaM2"])
        lines += [
            f"Przepływ cofnięty (u < 0 względem auta) zajmuje ponad 0,03 m² na stacjach x = {back[0]['x_m']:.1f} do {back[-1]['x_m']:.1f} m. "
            f"Najwięcej przy x = {worst['x_m']:.1f} m ({worst['reverseFlowAreaM2']:.3f} m², prędkość do {worst['minU_ms']} m/s w tył).",
            "",
        ]
    return lines


# ---------------------------------------------------------------------- render

def _round(value, digits: int):
    return round(value, digits) if isinstance(value, (int, float)) else value


def _fmt(value, digits: int = 3) -> str:
    return "brak" if value is None else f"{value:.{digits}f}"


def _pct(value, digits: int = 1) -> str:
    return "brak" if value is None else f"{value:.{digits}f}%"


def _headline(pack: dict) -> list[str]:
    kpis = pack.get("kpis") or {}
    refs = references(pack)
    bal = kpis.get("aeroBalance") or {}
    lines = ["## Najważniejsze liczby", ""]
    rows = [
        ("Opór Cd", _fmt(kpis.get("Cd"))),
        ("Docisk (współczynnik, dodatni = w dół)", _fmt(kpis.get("downforceCoeff"))),
        ("Cl (Z do góry, ujemny = docisk)", _fmt(kpis.get("Cl"))),
        ("Docisk / opór", _fmt(kpis.get("LOverD"), 2)),
        ("Balans przód / tył", f"{_fmt(bal.get('frontPct'), 1)}% / {_fmt(bal.get('rearPct'), 1)}%"),
        ("Środek parcia od osi przedniej", "brak" if bal.get("copXM") is None else f"{bal['copXM']:.3f} m"),
    ]
    if refs:
        q = 0.5 * refs["rho"] * refs["speed_ms"] ** 2
        full = 2.0 if (pack.get("identity") or {}).get("halfModel") else 1.0
        down = kpis.get("downforceCoeff")
        drag = kpis.get("Cd")
        if down is not None:
            rows.append((f"Docisk całego auta przy {refs['speed_ms']:g} m/s", f"{full * down * q * refs['aref_m2']:.0f} N"))
        if drag is not None:
            rows.append((f"Opór całego auta przy {refs['speed_ms']:g} m/s", f"{full * drag * q * refs['aref_m2']:.0f} N"))
    lines += ["| | |", "| --- | --- |"] + [f"| {a} | {b} |" for a, b in rows] + [""]
    return lines


def _checks_table(checks: list[dict]) -> list[str]:
    lines = ["| Sprawdzenie | Ocena | Wartość | Co to znaczy |", "| --- | --- | --- | --- |"]
    for c in checks:
        lines.append(f"| {c['title']} | {LIGHT[c['status']]} | {c['value']} | {c['detail']} |")
    return lines + [""]


def _parts_section(walls: dict | None) -> list[str]:
    lines = ["## Siły na części bolidu", ""]
    if walls is None:
        return lines + ["Nie policzono (brak plików wyników).", ""]
    lines += [
        "Policzone z ciśnienia i tarcia na każdej ściance, bez Fluenta. Współczynniki są dla połowy auta, jak w solverze.",
        "",
        "| Część | Cd | Docisk | Udział oporu | Udział docisku | Tarcie w oporze części |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, g in walls["groups"].items():
        visc = g["Cd_viscous"] / g["Cd"] * 100 if abs(g["Cd"]) > 1e-9 else None
        lines.append(
            f"| {PART_NAMES.get(name, name)} | {g['Cd']:.4f} | {g['downforceCoeff']:.4f} | "
            f"{_pct(g['shareDragPct'])} | {_pct(g['shareDownforcePct'])} | {_pct(visc, 0)} |"
        )
    c = walls["checksum"]
    lines += [
        "",
        f"Suma: Cd {c['vehicleCd']:.4f}, docisk {c['vehicleDownforce']:.4f}. "
        f"Monitor z solvera: Cd {_fmt(c['monitorCd'], 4)}, docisk {_fmt(c['monitorDownforce'], 4)}.",
        "",
    ]
    strips = walls.get("strips") or {}
    peaks = []
    for name, rows in strips.items():
        if name not in SURFACE_GROUPS or not rows:
            continue
        top = sorted(rows, key=lambda r: -r["downforceCoeff"])[:3]
        peaks.append(f"- **{PART_NAMES.get(name, name)}**: najwięcej docisku w pasach x = " + ", ".join(f"{r['x_m']:.2f} m ({r['downforceCoeff']:.3f})" for r in top))
    if peaks:
        lines += ["Gdzie wzdłuż auta powstaje docisk (pasy po 10 cm, x rośnie do tyłu, w nawiasie wkład do współczynnika):", ""] + peaks + [""]
    return lines


def _surface_section(walls: dict | None) -> list[str]:
    lines = ["## Ściany: y+ i oderwanie", ""]
    if walls is None:
        return lines + ["Nie policzono (brak plików wyników).", ""]
    lines += [
        "y+ mówi, jak blisko ściany leży pierwsza komórka siatki. Oderwanie to miejsca, gdzie przepływ tuż przy ścianie płynie do przodu, "
        "czyli powierzchnia przestaje prowadzić powietrze (liczone na powierzchniach prawie poziomych).",
        "",
        "| Część | y+ mediana | y+ max | Powierzchnia z y+ ≤ 5 | z y+ 5–30 | z y+ 30–300 | Oderwany przepływ |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    by_group_rev: dict[str, list[tuple[float, float]]] = {}
    for rec in walls["zones"].values():
        g = rec.get("group")
        rf = rec.get("reverseFlow") or {}
        if g in SURFACE_GROUPS and rf.get("areaShare") is not None:
            by_group_rev.setdefault(g, []).append((rf["areaShare"], rf.get("horizontalAreaM2") or 0.0))
    for name in SURFACE_GROUPS:
        stats = walls["groupYplus"].get(name)
        if not stats:
            continue
        sh = stats["shares"]
        low = sh.get("le1", 0.0) + sh.get("1to5", 0.0)
        rev = by_group_rev.get(name) or []
        area = sum(a for _, a in rev)
        rev_share = sum(s * a for s, a in rev) / area if area > 0 else None
        lines.append(
            f"| {PART_NAMES[name]} | {stats['median']} | {stats['max']} | {100 * low:.0f}% | "
            f"{100 * sh.get('5to30', 0):.0f}% | {100 * sh.get('30to300', 0):.0f}% | {_pct(None if rev_share is None else 100 * rev_share)} |"
        )
    lines += [""]
    hot = []
    for zname, rec in walls["zones"].items():
        if rec.get("group") not in SURFACE_GROUPS:
            continue
        for strip in (rec.get("reverseFlow") or {}).get("strips", []):
            if strip["reversedShare"] > 0.3 and strip["areaM2"] > 0.002:
                hot.append(f"- {PART_NAMES[rec['group']]} ({zname}): pas x = {strip['x_m']:.2f} m, {100 * strip['reversedShare']:.0f}% powierzchni oderwane")
    if hot:
        lines += ["Miejsca, gdzie ponad 30% powierzchni w pasie ma przepływ cofnięty:", ""] + hot + [""]
    return lines


def _setup_section(pack: dict) -> list[str]:
    ident = pack.get("identity") or {}
    methods = pack.get("methods") or {}
    refs = _get(pack, "kpis", "references") or {}
    mesh = pack.get("mesh") or {}
    rows = [
        ("Bolid", ident.get("vehicle")),
        ("Model", "połowa auta (symetria)" if ident.get("halfModel") else "całe auto"),
        ("Kąt znoszenia", f"{ident.get('yawDeg')}°"),
        ("Prędkość", f"{_get(refs, 'speedMs', 'value')} m/s ({_get(refs, 'speedMs', 'source')})"),
        ("Powierzchnia odniesienia", f"{_round(_get(refs, 'frontalAreaM2', 'value'), 4)} m² ({_get(refs, 'frontalAreaM2', 'source')})"),
        ("Solver", methods.get("fluentVersion")),
        ("Model turbulencji", methods.get("turbulence")),
        ("Ściana", methods.get("wallTreatment")),
        ("Liczba komórek", None if not mesh.get("cells") else f"{mesh['cells']:,}".replace(",", " ")),
        ("Iteracje", _get(pack, "kpis", "iterations")),
    ]
    lines = ["## Ustawienia i siatka", "", "| | |", "| --- | --- |"]
    lines += [f"| {k} | {'brak' if v in (None, '') else v} |" for k, v in rows]
    layers = (mesh.get("boundaryLayers") or {}).get("boundaryLayers") or []
    if layers:
        lines += ["", "Warstwy przyścienne z przepisu:", ""]
        for item in layers:
            first = item.get("firstHeightM")
            lines.append(f"- {item['name']}: {item.get('layers')} warstw, pierwsza komórka {'brak' if first is None else f'{first * 1e6:.0f} µm'}, {item.get('state')}")
    return lines + [""]


def _convergence_section(pack: dict, conservation: dict) -> list[str]:
    conv = _get(pack, "kpis", "convergence") or {}
    lines = ["## Zbieżność i zachowanie masy", ""]
    if conv.get("cx"):
        lines += [f"Zmiana siły w ostatnich {conv.get('windowIterations')} iteracjach (limit {_get(conv, 'limits', 'driftPct')}%):", "", "| Wielkość | Początek okna | Koniec okna | Zmiana |", "| --- | --- | --- | --- |"]
        for key, name in (("cx", "opór (cx)"), ("cz", "docisk (cz)"), ("cm", "moment (cm)")):
            rec = conv.get(key)
            if rec:
                lines.append(f"| {name} | {rec['startValue']:.4f} | {rec['endValue']:.4f} | {rec['driftPct']:+.2f}% |")
        lines.append("")
    res = conservation.get("residuals")
    if res:
        lines += [f"Residua po {res['iterations']} iteracjach (limit {res['limit']:.0e}):", "", "| Równanie | Wartość | Spadek od startu | Trend w końcówce |", "| --- | --- | --- | --- |"]
        for name, rec in res["equations"].items():
            drop = rec["ordersDropped"]
            lines.append(f"| {name} | {rec['final']:.2e} | {'brak' if drop is None else f'{drop:.1f} rzędu'} | {rec['trend']['verdict']} |")
        lines.append("")
    mb = conservation.get("massBalance")
    if mb:
        lines.append(
            f"Bilans masy: wlot {mb['inflowKgS']:.4f} kg/s, wylot {mb['outflowKgS']:.4f} kg/s, różnica {mb['relativeImbalance']:.1e} "
            f"(limit {mb['limit']:.0e}). Przez chłodnicę {_fmt(mb.get('radiatorKgS'), 4)} kg/s, przez wentylator {_fmt(mb.get('fanKgS'), 4)} kg/s."
        )
        lines.append("")
    return lines


def render_markdown(report: dict) -> str:
    pack = report["pack"]
    ident = pack.get("identity") or {}
    verdict = report["verdict"]
    lines = [
        f"# Raport symulacji: {ident.get('caseId', 'brak nazwy')}",
        "",
        f"Wygenerowano {report['generatedAt'][:19].replace('T', ' ')} UTC. Wszystko policzone automatycznie z plików case'a, nic nie było wpisywane ręcznie.",
        "",
        f"## Werdykt: {LIGHT[verdict['status']]}. {verdict['label']}",
        "",
    ]
    if verdict["bad"]:
        lines += ["Na czerwono: " + "; ".join(verdict["bad"]) + ".", ""]
    if verdict["warn"]:
        lines += ["Na żółto: " + "; ".join(verdict["warn"]) + ".", ""]
    if verdict["missing"]:
        lines += ["Bez danych: " + "; ".join(verdict["missing"]) + ".", ""]
    lines += _checks_table(report["checks"])
    lines += _headline(pack)
    lines += _parts_section(report["walls"])
    lines += _surface_section(report["walls"])
    lines += _flow_section(report.get("flow"), report["walls"])
    lines += _convergence_section(pack, report["conservation"])
    lines += _setup_section(pack)
    lines += ["## Czego brakuje", ""]
    gaps = report["missing"]
    lines += [f"- 🔴 {g}" for g in gaps] if gaps else ["Niczego: wszystkie potrzebne pliki były w folderze."]
    lines += [""]
    warnings = [w for w in pack.get("warnings", []) if w]
    if warnings:
        lines += ["## Ostrzeżenia z odczytu plików", ""] + [f"- {w}" for w in warnings] + [""]
    return "\n".join(lines)


# ------------------------------------------------------------------------ main

def build_report(case_root: Path, out_dir: Path, *, flow: bool = True, cache_dir: Path | None = None) -> dict:
    case_root = case_root.resolve()
    out_dir = out_dir.resolve()
    pack = build_pack(case_root, out_dir)
    conservation = conservation_report(case_root)
    walls = wall_analysis(case_root, pack)
    if walls is not None:
        attach_walls(pack, walls)
        (out_dir / "aeropack.json").write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
        write_brief(pack, out_dir)
    flow_data = flow_analysis(case_root, pack, cache_dir or Path("quant") / case_root.name / ".cache") if flow else None
    checks = evaluate_checks(pack, conservation, walls)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "caseId": (pack.get("identity") or {}).get("caseId"),
        "verdict": overall(checks),
        "checks": checks,
        "missing": missing_data(pack, conservation, walls),
        "conservation": conservation,
        "walls": walls,
        "flow": flow_data,
        "pack": pack,
    }
    (out_dir / "raport.json").write_text(json.dumps({k: v for k, v in report.items() if k != "pack"}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "raport.md").write_text(render_markdown(report), encoding="utf-8")
    return report
