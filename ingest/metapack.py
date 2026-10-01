"""One small folder that holds everything a solved case says, instead of CFD-Post files and pictures.

`meta.json` carries every number: the settings, forces per part and along the car, y+ and
separation, residuals and mass balance, the flow stations and vortices, the checks and the
credibility grade, ranked findings with their evidence, and where each number came from.
The maps sit beside it as compressed arrays:

* `powierzchnia_1cm.npz` and `powierzchnia_3mm.npz`: Cp, wall shear, y+ and reversed flow on the
  car's walls, one value per voxel of that size (positions are integer voxel indices, values are
  half precision). The coarse one is for reading, the fine one shows the flap gaps;
* `przekroje.npz`: Cp, total-pressure coefficient and relative velocity on the same 150 planes per
  axis as CFD-Post, on a 2 cm grid.

Everything in the maps can be drawn again (`render_from_meta`), so the pictures need not be kept.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SCHEMA = "aeropack-meta/v1"
SURFACE_VOXELS = {"1cm": 0.01, "3mm": 0.003}
PLANE_PITCH_M = 0.02
SURFACE_ORIGIN = np.array([-1.6, -1.3, -0.1])
ZONE_BITS, AXIS_BITS = 54, 18
SEVERITY_ORDER = {"wysoka": 0, "srednia": 1, "niska": 2, "info": 3}


# ----------------------------------------------------------------- surface maps

def bin_surface(xyz: np.ndarray, zone: np.ndarray, values: dict[str, np.ndarray], voxel: float, origin: np.ndarray = SURFACE_ORIGIN) -> dict:
    """Average face values inside voxels, per zone. Positions come out as integer voxel indices."""
    ijk = np.floor((xyz - origin) / voxel).astype(np.int64)
    if ijk.min() < 0 or ijk.max() >= (1 << AXIS_BITS):
        raise ValueError("punkt poza zakresem mapy")
    code = (zone.astype(np.int64) << ZONE_BITS) | (ijk[:, 0] << (2 * AXIS_BITS)) | (ijk[:, 1] << AXIS_BITS) | ijk[:, 2]
    unique, inverse = np.unique(code, return_inverse=True)
    members = np.bincount(inverse, minlength=unique.size).astype(np.float64)
    mask = (1 << AXIS_BITS) - 1
    out = {
        "ijk": np.stack([(unique >> (2 * AXIS_BITS)) & mask, (unique >> AXIS_BITS) & mask, unique & mask], axis=1).astype(np.uint16),
        "zone": (unique >> ZONE_BITS).astype(np.uint8),
        "faces": members.astype(np.uint16),
    }
    for name, v in values.items():
        mean = np.bincount(inverse, weights=v.astype(np.float64), minlength=unique.size) / members
        out[name] = mean
    return out


def quantize_surface(binned: dict) -> dict:
    """Half precision values, reversed flow as a whole percent."""
    return {
        "ijk": binned["ijk"],
        "zone": binned["zone"],
        "faces": binned["faces"],
        "cp": binned["cp"].astype(np.float16),
        "wss": binned["wss"].astype(np.float16),
        "yplus": binned["yplus"].astype(np.float16),
        "rev": np.clip(np.rint(100.0 * binned["rev"]), 0, 100).astype(np.uint8),
    }


def surface_positions(ijk: np.ndarray, voxel: float, origin: np.ndarray = SURFACE_ORIGIN) -> np.ndarray:
    return origin + (ijk.astype(np.float64) + 0.5) * voxel


def read_wall_faces(case: Path, *, rho: float, mu: float, speed_ms: float) -> dict:
    """One value set per wall face of the car: centre, Cp, wall shear, y+, reversed flow, zone index."""
    import h5py

    from ingest.wall_forces import group_for
    from ingest.wall_state import checked_layout, wall_state

    cas, dat = next(case.rglob("*.cas.h5")), next(case.rglob("*.dat.h5"))
    q = 0.5 * rho * speed_ms**2
    names, parts = [], {k: [] for k in ("xyz", "cp", "wss", "yplus", "rev", "zone")}
    with h5py.File(cas, "r") as mesh, h5py.File(dat, "r") as data:
        for name, packed_at, a, b in checked_layout(mesh, data):
            if group_for(name) is None:
                continue
            s = wall_state(mesh, data, packed_at, a, b, rho=rho, mu=mu)
            horizontal = np.abs(s["normal"][:, 2]) > 0.5
            parts["xyz"].append(s["centers"])
            parts["cp"].append(s["pressure"] / q)
            parts["wss"].append(np.linalg.norm(s["tau"], axis=1))
            parts["yplus"].append(s["yplus"])
            parts["rev"].append((horizontal & (s["uTan"][:, 0] < -0.01 * speed_ms)).astype(np.float64))
            parts["zone"].append(np.full(s["centers"].shape[0], len(names), dtype=np.uint8))
            names.append(name)
    return {"names": names, **{k: np.concatenate(v) for k, v in parts.items()}}


# ------------------------------------------------------------------ plane maps

def plane_maps(centers: np.ndarray, p: np.ndarray, u: np.ndarray, v: np.ndarray, w: np.ndarray, rho: float, speed_ms: float, positions: dict[str, list[float]], pitch: float = PLANE_PITCH_M) -> dict:
    """Cp, total-pressure coefficient and relative velocity on every plane of every axis (float16, NaN = no cells)."""
    from ingest.plane_images import Slicer

    q = 0.5 * rho * speed_ms**2
    speed2 = u * u + v * v + w * w
    slicer = Slicer(centers, {"cp": p / q, "cpt": (p + 0.5 * rho * speed2) / q, "vel": np.sqrt(speed2) / speed_ms})
    out = {}
    for axis, plist in positions.items():
        step = float(np.median(np.abs(np.diff(plist)))) if len(plist) > 1 else 0.02
        half = max(step / 2.0, 0.006)
        stacks = {k: [] for k in ("cp", "cpt", "vel")}
        for pos in plist:
            grid = slicer.grid(axis, pos, half, pitch)
            for k in stacks:
                stacks[k].append(grid[k].astype(np.float16))
        out[axis] = {"pos": np.asarray(plist, dtype=np.float32), **{k: np.stack(v) for k, v in stacks.items()}}
    return out


# --------------------------------------------------------------------- findings

def build_findings(report: dict) -> list[dict]:
    """What a person would conclude, ranked, each with the place in `meta.json` that proves it."""
    out: list[dict] = []

    def add(fid: str, severity: str, text: str, evidence: str) -> None:
        out.append({"id": fid, "waga": severity, "tekst": text, "dowod": evidence})

    for c in report.get("checks") or []:
        if c["status"] == "zle":
            add(f"sprawdzenie:{c['id']}", "wysoka", f"{c['title']}: {c['detail']}", f"raport.checks[id={c['id']}]")
        elif c["status"] == "uwaga":
            add(f"sprawdzenie:{c['id']}", "srednia", f"{c['title']}: {c['detail']}", f"raport.checks[id={c['id']}]")
    cred = report.get("credibility") or {}
    if cred.get("score") is not None:
        sev = "wysoka" if cred["score"] < 60 else "srednia" if cred["score"] < 85 else "niska"
        add("wiarygodnosc", sev, f"Wiarygodność {cred['score']} na 100 (pokrycie {cred['coverage']}%): {cred['label']}.", "raport.credibility")
    for name in cred.get("unknown") or []:
        add(f"nieznane:{name}", "srednia", f"Nie dało się sprawdzić: {name}.", "raport.credibility.unknown")
    groups = (report.get("walls") or {}).get("groups") or {}
    if groups:
        down = max(groups.items(), key=lambda kv: kv[1].get("shareDownforcePct") or -1e9)
        drag = max(groups.items(), key=lambda kv: kv[1].get("shareDragPct") or -1e9)
        add("docisk-glowny", "info", f"Najwięcej docisku: {down[0]} ({down[1].get('shareDownforcePct')}%). Najwięcej oporu: {drag[0]} ({drag[1].get('shareDragPct')}%).", "raport.walls.groups")
        for name, g in groups.items():
            if (g.get("downforceCoeff") or 0) < 0:
                add(f"unosi:{name}", "niska", f"{name} daje siłę w górę (docisk {g['downforceCoeff']:.3f}).", f"raport.walls.groups.{name}")
    summary = (report.get("pack") or {}).get("flowSummary") or {}
    for g in (summary.get("lossGrowth") or [])[:2]:
        add(f"strata:{g['fromX_m']}", "info", f"Strata energii rośnie o {g['growthM2']} m² między x = {g['fromX_m']} a {g['toX_m']} m, opór w pasie robi głównie: {g.get('dragMostlyFrom')}.", "raport.flow.stations")
    for t in (summary.get("vortexTracks") or [])[:3]:
        add(f"wir:{t['fromX_m']}", "info", f"Wir {abs(t['peakCirculationM2s']):.1f} m²/s, {t.get('region', '')}, x {t['fromX_m']} do {t['toX_m']}.", "raport.flow.vortexTracks")
    rev = summary.get("reverseFlow")
    if rev:
        add("oderwanie-w-sladzie", "srednia", f"Cofnięty przepływ na x = {rev['fromX_m']} do {rev['toX_m']} m (do {rev['maxAreaM2']} m²).", "raport.flow.stations[*].reverseFlowAreaM2")
    out.sort(key=lambda f: (SEVERITY_ORDER[f["waga"]], f["id"]))
    return out


def build_provenance(pack: dict) -> dict:
    """Where each part of `meta.json` came from and how exact it is."""
    conv = (pack.get("kpis") or {}).get("convergence") or {}
    rfile = not str(conv.get("source") or "").startswith("dat.h5") and bool((pack.get("monitors") or {}).get("monitors"))
    mesh = pack.get("mesh") or {}
    return {
        "sily_na_czesci": {"zrodlo": ".cas.h5 + .dat.h5", "metoda": "ciśnienie z każdej ścianki razy pole, tarcie odtworzone z y+ i odległości pierwszej komórki", "dokladnosc": "dokładne (zgodność z monitorem Fluenta w raporcie)"},
        "stabilnosc_sil": {"zrodlo": "pliki -rfile.out" if rfile else ".dat.h5", "metoda": "dryf w ostatnich 200 iteracjach" if rfile else "różnica między wartością chwilową a średnią", "dokladnosc": "dokładne" if rfile else "przybliżenie"},
        "residua": {"zrodlo": ".dat.h5", "metoda": "historia residuów znormalizowana jak w logu", "dokladnosc": "dokładne"},
        "bilans_masy": {"zrodlo": ".dat.h5", "metoda": "suma strumienia masy po brzegach domeny", "dokladnosc": "dokładne"},
        "jakosc_siatki": {"zrodlo": "log siatkowania" if mesh.get("minOrthogonalQuality") is not None else ".cas.h5", "metoda": "z logu" if mesh.get("minOrthogonalQuality") is not None else "z geometrii, środki komórek ze średniej środków ścianek", "dokladnosc": "dokładne" if mesh.get("minOrthogonalQuality") is not None else "przybliżenie, przesadza w spłaszczonych komórkach"},
        "przekroje_i_wiry": {"zrodlo": ".cas.h5 + .dat.h5", "metoda": "średnia z komórek w pasie, siła wirowania w płaszczyźnie", "dokladnosc": "dokładne w granicach siatki 2 cm"},
        "mapy_powierzchni": {"zrodlo": ".cas.h5 + .dat.h5", "metoda": "średnia z ścianek w kostce 1 cm albo 3 mm", "dokladnosc": "dokładne w granicach kostki, wartości w połowie precyzji"},
        "wiarygodnosc": {"zrodlo": "raport + literatura", "metoda": "ważona lista sprawdzeń ze źródłami", "dokladnosc": "ocena metodyki, nie dowód zgodności z rzeczywistością"},
    }


def originals_size(pack: dict) -> dict:
    """Sizes of the case files the meta pack stands in for."""
    given = (pack.get("files") or {}).get("root")
    root = Path(given) if given else Path()
    total, rows = 0, []
    if given and root.exists():
        for path in root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        for key in ("cas", "dat", "mesh", "transcripts", "cad"):
            for rel in (pack.get("files") or {}).get(key) or []:
                f = root / rel
                if f.exists():
                    rows.append({"plik": rel, "bajty": f.stat().st_size})
    return {"folder": str(root), "bajtyRazem": total, "wazne": rows}


# ------------------------------------------------------------------------ files

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_surface_files(out_dir: Path, faces: dict, voxels: dict[str, float] = SURFACE_VOXELS) -> dict:
    index = {}
    values = {"cp": faces["cp"], "wss": faces["wss"], "yplus": faces["yplus"], "rev": faces["rev"]}
    for label, voxel in voxels.items():
        q = quantize_surface(bin_surface(faces["xyz"], faces["zone"], values, voxel))
        path = out_dir / f"powierzchnia_{label}.npz"
        np.savez_compressed(path, voxel=np.float64(voxel), origin=SURFACE_ORIGIN, zone_names=np.array(faces["names"]), **q)
        index[label] = {"plik": path.name, "bajty": path.stat().st_size, "sha256": sha256(path), "voxel_m": voxel, "punktow": int(q["ijk"].shape[0]), "pola": ["cp", "wss", "yplus", "rev"], "strefy": faces["names"]}
    return index


def write_plane_file(out_dir: Path, planes: dict, pitch: float = PLANE_PITCH_M) -> dict:
    from ingest.plane_images import BOX

    arrays = {}
    for axis, stack in planes.items():
        arrays[f"{axis}_pos"] = stack["pos"]
        for k in ("cp", "cpt", "vel"):
            arrays[f"{axis}_{k}"] = stack[k]
    path = out_dir / "przekroje.npz"
    np.savez_compressed(path, pitch=np.float64(pitch), **arrays)
    return {"plik": path.name, "bajty": path.stat().st_size, "sha256": sha256(path), "pitch_m": pitch, "osie": {a: {"plaszczyzn": int(s["cp"].shape[0]), "ksztalt": list(s["cp"].shape[1:])} for a, s in planes.items()}, "pola": ["cp", "cpt", "vel"], "zakres_m": {a: list(BOX[a]) for a in BOX}}


def build_meta(report: dict, maps: dict) -> dict:
    """Everything in one dictionary. `report` is the saved raport.json plus the pack under `pack`."""
    pack = report.get("pack") or {}
    return {
        "schemat": SCHEMA,
        "wygenerowano": datetime.now(timezone.utc).isoformat(),
        "caseId": report.get("caseId") or (pack.get("identity") or {}).get("caseId"),
        "jak_czytac": [
            "Najpierw `wnioski` (posortowane, każdy ze wskazaniem dowodu), potem `werdykt` i `wiarygodnosc`.",
            "`zrodla` mówi, skąd jest każda część i czy to liczba dokładna, czy przybliżenie.",
            "`mapy` opisuje pliki .npz obok: wczytanie i rysowanie robi `python -m ingest meta-render`.",
            "Współczynniki są na połowę auta, tak jak liczy solver. Docisk dodatni to siła w dół.",
        ],
        "wnioski": build_findings(report),
        "werdykt": report.get("verdict"),
        "wiarygodnosc": report.get("credibility"),
        "zrodla": build_provenance(pack),
        "oryginaly": originals_size(pack),
        "mapy": maps,
        "raport": {k: v for k, v in report.items() if k not in ("pack", "credibility", "images")},
        "paczka": pack,
    }


def write_meta(out_dir: Path, meta: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")
    return path


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"{type(value)} nie jest zapisywalne")


# ------------------------------------------------------------------------ reading

def load_meta(folder: Path) -> dict:
    return json.loads((Path(folder) / "meta.json").read_text(encoding="utf-8"))


def verify_meta(folder: Path) -> list[str]:
    """Problems found in a meta folder (empty list = fine): missing files and wrong checksums."""
    folder = Path(folder)
    problems = []
    if not (folder / "meta.json").exists():
        return ["brak meta.json"]
    meta = load_meta(folder)
    if meta.get("schemat") != SCHEMA:
        problems.append(f"nieznany schemat {meta.get('schemat')}")
    files = [v for k, v in (meta.get("mapy") or {}).get("powierzchnia", {}).items()] + [(meta.get("mapy") or {}).get("przekroje")]
    for info in files:
        if not info:
            continue
        path = folder / info["plik"]
        if not path.exists():
            problems.append(f"brak pliku {info['plik']}")
        elif sha256(path) != info["sha256"]:
            problems.append(f"zła suma kontrolna {info['plik']}")
    return problems


def load_surface(folder: Path, label: str) -> dict:
    z = np.load(Path(folder) / f"powierzchnia_{label}.npz")
    voxel = float(z["voxel"])
    return {
        "xyz": surface_positions(z["ijk"], voxel, z["origin"]),
        "zone": z["zone"],
        "zone_names": [str(n) for n in z["zone_names"]],
        "cp": z["cp"].astype(np.float32),
        "wss": z["wss"].astype(np.float32),
        "yplus": z["yplus"].astype(np.float32),
        "rev": z["rev"].astype(np.float32) / 100.0,
        "voxel": voxel,
    }


def load_planes(folder: Path) -> dict:
    z = np.load(Path(folder) / "przekroje.npz")
    out = {}
    for axis in "xyz":
        if f"{axis}_pos" in z:
            out[axis] = {"pos": z[f"{axis}_pos"], **{k: z[f"{axis}_{k}"].astype(np.float32) for k in ("cp", "cpt", "vel")}}
    return out


def render_from_meta(folder: Path, out_dir: Path, *, surface_label: str = "3mm", every: int = 10) -> dict:
    """Draw the pictures again from the maps alone. Shows that nothing else is needed."""
    from ingest.plane_images import FIELDS, SURFACE_FIELDS, VIEWS, draw_plane, draw_surface

    folder, out_dir = Path(folder), Path(out_dir)
    s = load_surface(folder, surface_label)
    written = 0
    for field in SURFACE_FIELDS:
        for view in VIEWS:
            draw_surface(s["xyz"], s[field], view, field, out_dir / "powierzchnia" / f"{field}_{view}.png")
            written += 1
    for axis, stack in load_planes(folder).items():
        for i in range(0, len(stack["pos"]), every):
            for field in FIELDS:
                draw_plane(stack[field][i], axis, float(stack["pos"][i]), field, out_dir / "przekroje" / axis / field / f"{axis}_{stack['pos'][i]:.3f}.png")
                written += 1
    return {"obrazow": written, "out": str(out_dir)}


# -------------------------------------------------------------------------- main

def export_meta(case: Path, pack_dir: Path, out_dir: Path, *, rho: float, mu: float, speed_ms: float, template: dict | None, images_index: dict | None, cache_dir: Path | None) -> dict:
    """Build the maps from the solver files and write the whole meta folder. The report must already exist."""
    import h5py

    from ingest.flow_field import cell_centers
    from ingest.plane_images import plane_positions

    out_dir.mkdir(parents=True, exist_ok=True)
    faces = read_wall_faces(case, rho=rho, mu=mu, speed_ms=speed_ms)
    surface_index = write_surface_files(out_dir, faces)
    del faces
    cas, dat = next(case.rglob("*.cas.h5")), next(case.rglob("*.dat.h5"))
    centers = cell_centers(cas, None if cache_dir is None else cache_dir / "cell_centers.npy")
    with h5py.File(dat, "r") as data:
        cells = data["results/1/phase-1/cells"]
        p, u, v, w = (np.asarray(cells[f"{n}/1"][:], dtype=np.float32) for n in ("SV_P", "SV_U", "SV_V", "SV_W"))
    planes = plane_maps(centers, p, u, v, w, rho, speed_ms, plane_positions(template, images_index))
    plane_index = write_plane_file(out_dir, planes)
    report = json.loads((pack_dir / "raport.json").read_text(encoding="utf-8"))
    report["pack"] = json.loads((pack_dir / "aeropack.json").read_text(encoding="utf-8"))
    meta = build_meta(report, {"powierzchnia": surface_index, "przekroje": plane_index})
    path = write_meta(out_dir, meta)
    sizes = {p.name: p.stat().st_size for p in out_dir.iterdir() if p.is_file()}
    return {"meta": str(path), "rozmiary_bajty": sizes, "razem_bajty": sum(sizes.values()), "oryginaly_bajty": meta["oryginaly"]["bajtyRazem"]}
