from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ingest.cas_setup import parse_cas_setup
from ingest.inventory import scan_folder
from ingest.pictures import index_pictures
from ingest.rfile import parse_rfiles
from ingest.slices import load_slices
from ingest.transcript import parse_transcripts
from ingest.wall_forces import group_for, load_component_forces

SCHEMA = "aeropack/v1"
TEMPLATE_GEOMETRY = Path(__file__).resolve().parent.parent / "templates" / "geometry.yaml"

# Właściciel: Aref 0.5 m² na połowę, Z do góry. cx/cz z rfile to już współczynniki.
AREF_M2 = 0.5
AREF_BASIS = "half"
Z_POSITIVE = "up"
SPEED_MS = 15.0
RHO = 1.225


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


def interpret_kpis(cx, cz, cm, setup: dict) -> tuple[dict, list[str]]:
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
        "frontalAreaM2": AREF_M2,
        "frontalAreaBasis": AREF_BASIS,
        "zPositive": Z_POSITIVE,
        "rho": RHO,
        "speedMs": SPEED_MS,
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
    images = index_pictures(case_root, files["pictures"], slices) if files["pictures"] else {
        "total": 0,
        "index": [],
        "heroCount": 0,
        "byAxis": {},
        "stationEncoded": False,
    }

    monitors = reports.get("monitors") or {}
    cx = (monitors.get("cx") or {}).get("averaged")
    cz = (monitors.get("cz") or {}).get("averaged")
    cm = (monitors.get("cm") or {}).get("averaged")
    kpis, kpi_warnings = interpret_kpis(cx, cz, cm, setup)
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
            "vehicle": "PM09",
            "halfModel": half,
            "yawDeg": 0,
            "speedMs": SPEED_MS,
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
            "turbulence": transcripts.get("turbulenceHit"),
            "mrfFan": transcripts.get("mrfFan"),
        },
        "mesh": {
            "cells": transcripts.get("cells"),
            "minOrthogonalQuality": transcripts.get("minOrthogonalQuality"),
            "hexcore": transcripts.get("hexcore"),
            "scopedPrisms": transcripts.get("scopedPrisms"),
            "prismStairstepLocations": transcripts.get("prismStairstepLocations"),
            "symmetryFaces": transcripts.get("symmetryFaces"),
            "inletFaces": transcripts.get("inletFaces"),
        },
        "reportDefinitions": setup.get("reports") or {},
        "monitors": reports,
        "kpis": kpis,
        "geometry": {"source": "templates/geometry.yaml", "status": "vehicle-filled, devices TBD"},
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
            "Half-model, yaw 0, jazda na wprost. Aref 0.5 m² na połowę bolidu.",
            cz_note,
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
    if TEMPLATE_GEOMETRY.exists():
        shutil.copy(TEMPLATE_GEOMETRY, out_dir / "geometry.yaml")
    slices_src = Path(__file__).resolve().parent.parent / "templates" / "slices.yaml"
    if slices_src.exists():
        shutil.copy(slices_src, out_dir / "slices.yaml")
    (out_dir / "aeropack.json").write_text(
        json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return pack
