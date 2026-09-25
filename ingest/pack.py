from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ingest.balance import aero_balance
from ingest.car_layout import stamp_frames
from ingest.cas_setup import parse_cas_setup
from ingest.inventory import scan_folder
from ingest.pictures import index_pictures
from ingest.rfile import parse_rfiles
from ingest.setup_trace import merge_traces
from ingest.slices import load_slices
from ingest.step_cards import cards_from_step
from ingest.transcript import parse_transcripts
from ingest.wall_forces import group_for, load_component_forces
from ingest.wft_mesh import ground_layer_warnings, parse_wft

SCHEMA = "aeropack/v1"
TEMPLATE_GEOMETRY = Path(__file__).resolve().parent.parent / "templates" / "geometry.yaml"

# Domyślne tylko gdy case ani geometry.yaml ich nie podają. Pack oznacza je jako assumed.
AREF_M2 = 0.5
AREF_BASIS = "half"
Z_POSITIVE = "up"
SPEED_MS = 15.0
RHO = 1.225
MU = 1.789e-5


def _load_yaml(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _num(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _geometry_summary(doc: dict, source: str) -> dict:
    devices = doc.get("devices") if isinstance(doc.get("devices"), list) else []
    cards = [item for item in devices if isinstance(item, dict)]
    with_chord = sum(1 for item in cards if _num(item.get("chordMm")) is not None)
    profiles_tbd = sum(
        1 for item in cards
        if "profile" in item and item.get("profile") in (None, "TBD")
    )
    if not cards:
        status = "brak kart urządzeń"
    else:
        card_word = "karta" if len(cards) == 1 else "kart"
        profile_word = "profil TBD" if profiles_tbd == 1 else "profili TBD"
        status = f"{len(cards)} {card_word}, {with_chord} z cięciwą, {profiles_tbd} {profile_word}"
    return {
        "source": source,
        "status": status,
        "deviceCount": len(cards),
        "withChord": with_chord,
        "profilesTbd": profiles_tbd,
    }


def _reference(case_value, case_source: str, yaml_value, default, default_source: str) -> dict:
    if _num(case_value) is not None:
        return {"value": float(case_value), "source": case_source}
    if _num(yaml_value) is not None:
        return {"value": float(yaml_value), "source": "geometry.yaml"}
    return {"value": default, "source": default_source}


def _axles(setup: dict, vehicle: dict, speed_ms: float | None) -> dict:
    wheels = setup.get("wheels") or {}
    front = (wheels.get("front") or {}).get("originM") or [None, None, None]
    rear = (wheels.get("rear") or {}).get("originM") or [None, None, None]
    out = {"frontXM": front[0], "rearXM": rear[0], "groundZM": None, "source": None}
    if out["frontXM"] is not None and out["rearXM"] is not None:
        out["source"] = f"case:{setup.get('wheelsSource')} (oś obrotu kół)"
    else:
        fx = _num(vehicle.get("frontAxleXMm"))
        rx = _num(vehicle.get("rearAxleXMm"))
        out["frontXM"] = None if fx is None else fx / 1000.0
        out["rearXM"] = None if rx is None else rx / 1000.0
        out["source"] = "geometry.yaml" if fx is not None and rx is not None else None
    ground = _num(vehicle.get("groundZMm"))
    if ground is not None:
        out["groundZM"] = ground / 1000.0
    else:
        omega = (wheels.get("front") or {}).get("omegaRadS")
        if front[2] is not None and omega and speed_ms:
            out["groundZM"] = round(front[2] - speed_ms / abs(omega), 4)
    return out


DRIFT_LIMIT_PCT = 0.5
BALANCE_LIMIT_PP = 0.5


def _force_convergence(monitors: dict, setup: dict, balance: dict, balance_kwargs: dict) -> dict:
    stab = {name: (monitors.get(name) or {}).get("stability") for name in ("cx", "cz", "cm")}
    out: dict = {
        "windowIterations": max((s or {}).get("window") or 0 for s in stab.values()),
        "cx": stab["cx"],
        "cz": stab["cz"],
        "cm": stab["cm"],
        "limits": {"driftPct": DRIFT_LIMIT_PCT, "balancePp": BALANCE_LIMIT_PP},
        "balanceShiftPp": None,
        "settled": None,
        "reasons": [],
    }
    if stab["cx"] and stab["cz"] and stab["cm"] and balance.get("frontPct") is not None:
        start_kpis, _ = interpret_kpis(
            stab["cx"]["startValue"], stab["cz"]["startValue"], stab["cm"]["startValue"], setup
        )
        start = aero_balance(
            cd=start_kpis.get("Cd"),
            downforce=start_kpis.get("downforceCoeff"),
            cm=stab["cm"]["startValue"],
            cx_vector=start_kpis.get("cxForceVector"),
            **balance_kwargs,
        )
        if start.get("frontPct") is not None:
            out["balanceStartPct"] = start["frontPct"]
            out["balanceShiftPp"] = round(balance["frontPct"] - start["frontPct"], 2)
    if not (stab["cx"] and stab["cz"]):
        out["reasons"].append("brak historii monitorów cx/cz")
        return out
    if out["windowIterations"] < 150:
        out["reasons"].append(f"za mało iteracji do oceny ({out['windowIterations']})")
        return out
    for name in ("cx", "cz"):
        drift = stab[name].get("driftPct")
        if drift is not None and abs(drift) > DRIFT_LIMIT_PCT:
            out["reasons"].append(
                f"{name} zmieniło się o {drift:+.2f}% w ostatnich {stab[name]['window']} iteracjach"
            )
    shift = out["balanceShiftPp"]
    if shift is not None and abs(shift) > BALANCE_LIMIT_PP:
        out["reasons"].append(f"balans przesunął się o {shift:+.2f} pp w tym samym oknie")
    out["settled"] = not out["reasons"]
    return out


def _abs(root: Path, rels: list[str]) -> list[Path]:
    return [root / rel for rel in rels]


def _force_files(case_root: Path, out_dir: Path, report_rels: list[str]) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for rel in report_rels:
        path = case_root / rel
        if "force" in path.name.lower() and path.suffix.lower() == ".txt" and path.exists():
            found.append(path)
            seen.add(path.name)
    for name in (
        "wall_forces_dump.txt",
        "dump_wall_forces.jou",
        "wall_forces_cx.txt",
        "wall_forces_cz.txt",
        "wall_forces_cl_zup.txt",
    ):
        path = out_dir / name
        if path.exists() and name not in seen:
            found.append(path)
    return found


def interpret_kpis(
    cx,
    cz,
    cm,
    setup: dict,
    *,
    aref_m2: float = AREF_M2,
    aref_basis: str = AREF_BASIS,
    speed_ms: float = SPEED_MS,
    rho: float = RHO,
) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    meaning = setup.get("czPositiveMeans")
    cx_vec = setup.get("cxForceVector")
    cz_vec = setup.get("czForceVector")
    verified = bool(setup.get("verified") and meaning)

    cd = cx
    cl = None
    downforce = None
    if meaning == "downforce":
        downforce = cz
        cl = -cz if cz is not None else None
    elif meaning == "lift":
        downforce = -cz if cz is not None else None
        cl = cz
    else:
        warnings.append(
            "Wektor cz niezweryfikowany z definicji raportu — nie liczę Cl/downforce."
        )

    l_over_d = None
    if cd and downforce is not None and cd != 0:
        l_over_d = abs(downforce) / cd

    kpis = {
        "forceConvention": "half",
        "frontalAreaM2": aref_m2,
        "frontalAreaBasis": aref_basis,
        "zPositive": Z_POSITIVE,
        "rho": rho,
        "speedMs": speed_ms,
        "cx": cx,
        "cz": cz,
        "cm": cm,
        "Cd": cd,
        "Cl": cl,
        "downforceCoeff": downforce,
        "LOverD": l_over_d,
        "cxForceVector": cx_vec,
        "czForceVector": cz_vec,
        "czPositiveMeans": meaning,
        "forceVectorVerified": verified,
        "forceVectorSource": setup.get("source"),
    }
    if cd is not None:
        kpis["Cd_total"] = round(cd, 3)
    if cl is not None:
        kpis["Cl_total"] = round(cl, 3)
    if downforce is not None:
        kpis["downforce_total"] = round(downforce, 3)
    return kpis, warnings


def build_pack(case_root: Path, out_dir: Path) -> dict:
    case_root = case_root.resolve()
    out_dir = out_dir.resolve()
    inventory = scan_folder(case_root)
    files = inventory["files"]
    transcripts = parse_transcripts(_abs(case_root, files["transcripts"])) if files["transcripts"] else {}
    reports = parse_rfiles(_abs(case_root, files["reports"])) if files["reports"] else {}
    setup = parse_cas_setup(_abs(case_root, files["cas"]))
    slices = load_slices()
    case_geom = _abs(case_root, files["geometryYaml"])
    geom_path = case_geom[0] if case_geom else (
        TEMPLATE_GEOMETRY if TEMPLATE_GEOMETRY.exists() else None
    )
    geometry_doc = _load_yaml(geom_path)
    step_paths = [
        case_root / rel for rel in files["cad"]
        if rel.lower().endswith((".step", ".stp"))
    ]
    step_cards = None
    step_error = None
    if step_paths:
        try:
            step_cards = cards_from_step(step_paths[0])
        except ImportError:
            step_error = "Jest STEP, ale brak pakietu ocp — stacje X zostają z geometry.yaml."
    if step_cards:
        vehicle_block = geometry_doc.get("vehicle") if isinstance(geometry_doc.get("vehicle"), dict) else {}
        geometry_doc = {
            "vehicle": vehicle_block,
            "devices": step_cards,
            "measuredFrom": step_paths[0].name,
        }
    wft_paths = sorted(case_root.rglob("*.wft"))
    wft_parsed = parse_wft(wft_paths[0]) if wft_paths else None
    trace = merge_traces(_abs(case_root, files["transcripts"])) if files["transcripts"] else None
    images = index_pictures(
        case_root, files["pictures"], slices, geometry_doc
    ) if files["pictures"] else {
        "total": 0,
        "index": [],
        "heroCount": 0,
        "byAxis": {},
        "stationEncoded": False,
    }
    if step_cards and images.get("index"):
        stamp_frames(images["index"], step_cards)
    vehicle = geometry_doc.get("vehicle") if isinstance(geometry_doc.get("vehicle"), dict) else {}
    vehicle_name = vehicle.get("name") if isinstance(vehicle.get("name"), str) and vehicle.get("name") else None
    aref_basis = vehicle.get("frontalAreaBasis") if isinstance(vehicle.get("frontalAreaBasis"), str) else AREF_BASIS
    case_refs = setup.get("references") or {}
    case_src = f"case:{setup.get('referencesSource')}"
    references = {
        "speedMs": _reference(case_refs.get("velocityMs"), case_src, vehicle.get("speedMs"), SPEED_MS, "assumed-constant"),
        "rho": _reference(case_refs.get("densityKgM3"), case_src, vehicle.get("rho"), RHO, "assumed-constant"),
        "mu": _reference(case_refs.get("viscosityPaS"), case_src, None, MU, "assumed-air"),
        "frontalAreaM2": _reference(case_refs.get("areaM2"), case_src, vehicle.get("frontalAreaM2"), AREF_M2, "assumed-constant"),
        "referenceLengthM": _reference(case_refs.get("lengthM"), case_src, None, None, "brak"),
    }
    reference_conflicts = []
    for key, yaml_key in (("frontalAreaM2", "frontalAreaM2"), ("speedMs", "speedMs"), ("rho", "rho")):
        yaml_value = _num(vehicle.get(yaml_key))
        used = references[key]["value"]
        if yaml_value is not None and used and references[key]["source"].startswith("case:"):
            if abs(yaml_value - used) / abs(used) > 0.02:
                reference_conflicts.append(f"{key}: case {used:.4g}, geometry.yaml {yaml_value:.4g}")

    monitors = reports.get("monitors") or {}
    cx = (monitors.get("cx") or {}).get("averaged")
    cz = (monitors.get("cz") or {}).get("averaged")
    cm = (monitors.get("cm") or {}).get("averaged")
    kpis, kpi_warnings = interpret_kpis(
        cx,
        cz,
        cm,
        setup,
        aref_m2=references["frontalAreaM2"]["value"],
        aref_basis=aref_basis,
        speed_ms=references["speedMs"]["value"],
        rho=references["rho"]["value"],
    )
    kpis["references"] = references
    moment_def = (setup.get("reports") or {}).get("cm") or {}
    axles = _axles(setup, vehicle, references["speedMs"]["value"])
    balance = aero_balance(
        cd=kpis.get("Cd"),
        downforce=kpis.get("downforceCoeff"),
        cm=cm,
        moment_center_m=moment_def.get("momentCenterM"),
        moment_axis=moment_def.get("momentAxis"),
        moment_scaled=moment_def.get("scaled"),
        reference_length_m=references["referenceLengthM"]["value"],
        front_axle_x_m=axles["frontXM"],
        rear_axle_x_m=axles["rearXM"],
        ground_z_m=axles["groundZM"],
        cx_vector=kpis.get("cxForceVector"),
    )
    balance["sources"] = {
        "moment": f"case:{', '.join(setup.get('files') or [])}" if moment_def else None,
        "referenceLength": references["referenceLengthM"]["source"],
        "axles": axles["source"],
    }
    kpis["aeroBalance"] = balance
    convergence = _force_convergence(monitors, setup, balance, balance_kwargs={
        "moment_center_m": moment_def.get("momentCenterM"),
        "moment_axis": moment_def.get("momentAxis"),
        "moment_scaled": moment_def.get("scaled"),
        "reference_length_m": references["referenceLengthM"]["value"],
        "front_axle_x_m": axles["frontXM"],
        "rear_axle_x_m": axles["rearXM"],
        "ground_z_m": axles["groundZM"],
    })
    last_session = next(
        (s for s in reversed(transcripts.get("sessions") or []) if s.get("lastIteration")),
        None,
    )
    if last_session:
        convergence["plannedIterations"] = last_session.get("plannedIterations")
        convergence["iterationsLeft"] = last_session.get("iterationsLeft")
        convergence["stoppedEarly"] = bool(last_session.get("iterationsLeft"))
        convergence["session"] = last_session["file"]
    kpis["convergence"] = convergence
    if transcripts.get("residuals"):
        reports["residuals"] = transcripts["residuals"]
    if transcripts.get("yPlus"):
        reports["yPlus"] = transcripts["yPlus"]
    kpis["iterations"] = reports.get("iterations")

    wall = load_component_forces(
        _force_files(case_root, out_dir, files["reports"]),
        cd_total=kpis.get("Cd_total"),
        cl_total=kpis.get("Cl_total"),
    )
    if wall:
        kpis["components"] = {
            "source": wall.get("file"),
            "excluded": wall.get("excluded"),
            "groups": wall.get("groups"),
            "vehicle": wall.get("vehicle"),
            "checksum": wall.get("checksum"),
        }
        pack_wall_zones = {}
        for zname, zrec in (wall.get("zones") or {}).items():
            if group_for(zname) is None:
                continue
            pack_wall_zones[zname] = {
                "group": zrec.get("group") or group_for(zname),
                "Fx": zrec.get("Fx"),
                "Fy": zrec.get("Fy"),
                "Fz": zrec.get("Fz"),
                "Cd": zrec.get("Cd"),
                "Cl": zrec.get("Cl"),
                "downforceCoeff": zrec.get("downforceCoeff"),
                "Cd_pressure": zrec.get("Cx_pressure", zrec.get("C_pressure")),
                "Cd_viscous": zrec.get("Cx_viscous", zrec.get("C_viscous")),
                "Cl_pressure": zrec.get("Cz_pressure"),
                "Cl_viscous": zrec.get("Cz_viscous"),
            }
        kpis["wallZones"] = pack_wall_zones

    warnings = list(inventory["warnings"])
    warnings.extend(kpi_warnings)
    warnings.extend(setup.get("errors") or [])
    if reference_conflicts:
        warnings.append(
            "Wartości odniesienia w geometry.yaml różnią się od case'a (użyto case'a): "
            + "; ".join(reference_conflicts) + "."
        )
    if convergence.get("settled") is False:
        warnings.append(
            "Siły jeszcze się nie ustabilizowały: " + "; ".join(convergence["reasons"])
            + ". Nie porównuj tej symulacji z innymi na poziomie pojedynczych procentów."
        )
    if convergence.get("stoppedEarly"):
        warnings.append(
            f"Liczenie zatrzymane przed planem: {convergence.get('iterationsLeft')} iteracji z "
            f"{convergence.get('plannedIterations') or '?'} nie zostało policzonych "
            f"({convergence.get('session')})."
        )
    if balance.get("frontPct") is None:
        warnings.append("Balans aero niepoliczony — brak: " + ", ".join(balance["missing"]) + ".")
    for session in (transcripts.get("sessions") or []):
        if session.get("crashed"):
            why = ", ".join(session.get("crashReasons") or []) or "BAD TERMINATION"
            warnings.append(f"Transcript {session['file']}: Fluent padł ({why}).")
        if session.get("divergence"):
            eqs = ", ".join(f"{eq} ×{n}" for eq, n in session["divergence"].items())
            warnings.append(f"Transcript {session['file']}: rozbieżność AMG ({eqs}).")
        if session.get("scriptErrorCount"):
            warnings.append(
                f"Transcript {session['file']}: Fluent odrzucił {session['scriptErrorCount']} "
                f"komend skryptu, np. „{session['scriptErrors'][0]}”. Sprawdź, czy ustawienia "
                "weszły ręcznie."
            )
        for item in session.get("wallMotionNormal") or []:
            warnings.append(
                f"Transcript {session['file']}: ruch ściany ma dużą składową normalną na "
                f"{item['faces']} ściankach strefy {item['zoneId']} — sprawdź oś obrotu kół."
            )
    if step_error:
        warnings.append(step_error)
    if step_cards:
        warnings.append(
            "Stacje klatek X są z STEP tego case'a. Szablon geometry.yaml nie ustawia pozycji skrzydeł."
        )
    elif geom_path == TEMPLATE_GEOMETRY:
        warnings.append(
            "Brak STEP w folderze case — pozycje skrzydeł biorą się z templates/geometry.yaml "
            "i mogą nie pasować do tej geometrii."
        )
    if wft_parsed:
        warnings.extend(ground_layer_warnings(wft_parsed))
    if not files["journals"]:
        warnings = [item for item in warnings if not item.startswith("Brak journala")]
        warnings.append(
            "Brak .jou. Nie składam journala z transcriptu — to nie odtworzy sesji 1:1. "
            "Kliknięcia są w methods.setupTrace. Siatkę powtarza .wft, solver jest w .cas.h5."
        )
    if images.get("warning"):
        warnings.append(images["warning"])
    if transcripts.get("memoryFailure"):
        warnings.append("Transcript: Memory allocation failed przy repartycji siatki (Metis).")
    if not setup.get("verified"):
        warnings.append(
            "Brak ASCII .cas z (force-vector) — znak cz nie jest twardo potwierdzony."
        )
    cz_def = (setup.get("reports") or {}).get("cz") or {}
    if cz_def.get("perZone") is False and not (wall and wall.get("groups")):
        warnings.append(
            "Monitor cz ma per-zone? #f i nie ma wall_forces_dump.txt — "
            "brak sił po strefach. Odpal: python -m ingest dump-forces <case>."
        )
    if wall and wall.get("checksum") and not wall["checksum"].get("ok"):
        warnings.append(
            "Suma sił grup rozjeżdża się z Cd_total/Cl_total o więcej niż 1%."
        )
    assumed = [
        f"{key}={item['value']} ({item['source']})"
        for key, item in references.items()
        if str(item["source"]).startswith("assumed")
    ]
    if assumed:
        warnings.append("Założenia nieodczytane z case'a: " + ", ".join(assumed) + ".")
    if vehicle_name is None:
        warnings.append("Brak vehicle.name w geometry.yaml — identity.vehicle ustawione na PM09.")
        vehicle_name = "PM09"

    half = bool(transcripts.get("halfModel"))
    cz_note = (
        "cz z definicji raportu ma wektor (0, 0, -1): dodatnie cz to downforce. "
        "Cl fizyczny (Z w górę) = -cz. Cd = cx."
        if kpis.get("czPositiveMeans") == "downforce"
        else (
            "cz z definicji raportu ma wektor (0, 0, 1): dodatnie cz to lift. "
            "downforceCoeff = -cz."
            if kpis.get("czPositiveMeans") == "lift"
            else "Znak cz niezweryfikowany — nie zgaduj downforce."
        )
    )
    pack = {
        "schema": SCHEMA,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "identity": {
            "caseId": case_root.name,
            "vehicle": vehicle_name,
            "halfModel": half,
            "yawDeg": 0,
            "speedMs": references["speedMs"]["value"],
            "kind": inventory["kind"],
            "zPositive": Z_POSITIVE,
        },
        "files": {
            "root": str(case_root),
            "cas": files["cas"],
            "dat": files["dat"],
            "mesh": files["mesh"],
            "transcripts": files["transcripts"],
            "journals": files["journals"],
            "picturesDir": "Baseline002 Post pro" if files["pictures"] else "",
            "cad": files["cad"],
            "geometryYaml": files["geometryYaml"] or ["geometry.yaml"],
        },
        "methods": {
            "fluentVersion": transcripts.get("fluentVersion"),
            "turbulence": (setup.get("turbulence") or {}).get("model") or transcripts.get("turbulenceHit"),
            "wallTreatment": (setup.get("turbulence") or {}).get("wallTreatment"),
            "turbulenceSource": (
                f"case:{setup['turbulence']['source']}" if setup.get("turbulence") else "transcript"
            ),
            "mrfFan": transcripts.get("mrfFan"),
            "wheelRotation": setup.get("wheels") or None,
            "solverSessions": transcripts.get("sessions") or [],
            "setupTrace": trace,
        },
        "mesh": {
            "cells": transcripts.get("cells"),
            "minOrthogonalQuality": transcripts.get("minOrthogonalQuality"),
            "maxAspectRatio": transcripts.get("maxAspectRatio"),
            "hexcore": transcripts.get("hexcore"),
            "scopedPrisms": transcripts.get("scopedPrisms"),
            "prismStairstepLocations": transcripts.get("prismStairstepLocations"),
            "symmetryFaces": transcripts.get("symmetryFaces"),
            "inletFaces": transcripts.get("inletFaces"),
            "boundaryLayers": None if wft_parsed is None else wft_parsed,
        },
        "reportDefinitions": setup.get("reports") or {},
        "monitors": reports,
        "kpis": kpis,
        "geometry": _geometry_summary(
            geometry_doc,
            geometry_doc.get("measuredFrom") or (str(geom_path) if geom_path else "brak"),
        ),
        "slices": {
            **(images.get("slices") or {}),
            "fields": slices.get("fields"),
        },
        "images": {
            "total": images.get("total", 0),
            "index": "images/index.json",
            "hero": [e for e in images.get("index", []) if e.get("hero")],
            "byAxis": images.get("byAxis", {}),
            "stationEncoded": images.get("stationEncoded", False),
        },
        "transcriptHits": transcripts.get("hits", [])[:60],
        "notesForAgent": [
            (
                "Half-model, yaw 0, jazda na wprost. "
                f"Aref {references['frontalAreaM2']['value']} m² "
                f"({references['frontalAreaM2']['source']}, basis {aref_basis}). "
                f"V∞ {references['speedMs']['value']} m/s ({references['speedMs']['source']})."
            ),
            cz_note,
            (
                f"Balans aero {balance['frontPct']}% przód z cm, punktu momentu i osi kół (kpis.aeroBalance). "
                "Nie licz go z udziału FW/RW."
                if balance.get("frontPct") is not None
                else "Balans aero niepoliczony — nie zgaduj go z udziału FW/RW."
            ),
            "Cd = cx. Siły i Aref są na połowę — nie mnoż ×2 do współczynników.",
            "Strefy: FW=surface_fw, RW=surface_rw, Floor=surface_ut, Body=surface_mono. "
            "domain_ground i domain_sky nie wchodzą do sumy auta.",
            "Klatki Velocity to NormalisedVelocity = V/Vinf, nie m/s. Legenda w slices.fields.",
            "Przekroje X: -1.1 m → 2.5 m, 150 klatek; na JPG jest napis x = …",
            "Nie odczytuj Cl/Cd z pikseli.",
            "Nie wnioskuj yaw z Cs — tego monitora nie ma.",
            "Nie łykaj .cas.h5/.dat.h5 do kontekstu.",
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    heroes_only_index = {
        "total": images.get("total", 0),
        "byAxis": images.get("byAxis", {}),
        "heroCount": images.get("heroCount", 0),
        "stationEncoded": images.get("stationEncoded", False),
        "index": images.get("index", []),
    }
    images_dir = out_dir / "images"
    images_dir.mkdir(exist_ok=True)
    (images_dir / "index.json").write_text(
        json.dumps(heroes_only_index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    dest_geom = out_dir / "geometry.yaml"
    if step_cards:
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml is not None:
            dest_geom.write_text(
                yaml.safe_dump(geometry_doc, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
    elif geom_path is not None and geom_path.exists() and geom_path.resolve() != dest_geom.resolve():
        shutil.copy(geom_path, dest_geom)
    slices_src = Path(__file__).resolve().parent.parent / "templates" / "slices.yaml"
    if slices_src.exists():
        shutil.copy(slices_src, out_dir / "slices.yaml")
    (out_dir / "aeropack.json").write_text(
        json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return pack
