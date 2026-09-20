from __future__ import annotations

import json
from pathlib import Path

SUFFIX_BUCKETS = {
    "cas": {".cas.h5", ".cas.gz", ".cas"},
    "dat": {".dat.h5", ".dat.gz", ".dat", ".cdat"},
    "mesh": {".msh.h5", ".msh.gz", ".msh"},
    "transcripts": {".trn"},
    "journals": {".jou"},
    "prisms": {".pzmcontrol"},
    "pictures": {".png", ".jpg", ".jpeg"},
    "cad": {".step", ".stp", ".stl", ".scdoc"},
}


def _suffix(path: Path) -> str:
    name = path.name.lower()
    for extra in (".cas.h5", ".dat.h5", ".msh.h5", ".cas.gz", ".dat.gz", ".msh.gz"):
        if name.endswith(extra):
            return extra
    return path.suffix.lower()


def _bucket_for(path: Path) -> str | None:
    suf = _suffix(path)
    for key, suffixes in SUFFIX_BUCKETS.items():
        if suf in suffixes:
            return key
    low = path.name.lower()
    if low.endswith("-rfile.out") or "forces" in low or low.startswith("report"):
        if suf in {".out", ".txt", ".csv"}:
            return "reports"
    if low == "geometry.yaml":
        return "geometryYaml"
    return None


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def scan_folder(root: Path) -> dict:
    root = root.resolve()
    files: list[dict] = []
    buckets: dict[str, list[str]] = {
        "cas": [],
        "dat": [],
        "mesh": [],
        "transcripts": [],
        "journals": [],
        "prisms": [],
        "pictures": [],
        "cad": [],
        "reports": [],
        "geometryYaml": [],
        "other": [],
    }

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in {".DS_Store"} or path.suffix == ".7z":
            continue
        rec = {
            "path": _rel(root, path),
            "bytes": path.stat().st_size,
            "suffix": _suffix(path),
        }
        files.append(rec)
        key = _bucket_for(path)
        if key:
            buckets[key].append(rec["path"])
        else:
            buckets["other"].append(rec["path"])

    kind = "incomplete"
    if buckets["cas"] and buckets["dat"]:
        kind = "full_case"
    elif buckets["mesh"] and not buckets["dat"]:
        kind = "mesh_only"

    warnings = _warnings(kind, buckets)
    return {
        "root": str(root),
        "kind": kind,
        "counts": {k: len(v) for k, v in buckets.items() if k != "other"},
        "pictureCount": len(buckets["pictures"]),
        "files": buckets,
        "warnings": warnings,
        "fileCount": len(files),
        "bytes": sum(f["bytes"] for f in files),
    }


def _warnings(kind: str, buckets: dict[str, list[str]]) -> list[str]:
    warnings: list[str] = []
    if kind == "mesh_only":
        warnings.append("Brak .cas/.dat — to mesh, nie rozwiązanie. Pack bez sił i residuali.")
    if not buckets["cas"] and not buckets["mesh"]:
        warnings.append("Brak .cas.h5 i .msh.h5.")
    if not buckets["transcripts"]:
        warnings.append("Brak transcriptu .trn.")
    if not buckets["journals"]:
        warnings.append("Brak journala .jou — metody tylko z .trn / CFF.")
    if not buckets["geometryYaml"]:
        warnings.append("Brak geometry.yaml — karty płatów TBD.")
    if not buckets["pictures"]:
        warnings.append("Brak PNG/JPG.")
    if buckets["pictures"] and not any(
        "AnimationFrame" in p or "_" in Path(p).stem for p in buckets["pictures"]
    ):
        warnings.append("Nazwy zdjęć nie kodują stacji (oś_stacja_pole).")
    if not buckets["prisms"]:
        warnings.append("Brak .pzmcontrol — warstwy przyścienne tylko z transcriptu.")
    if kind == "full_case" and not buckets["reports"]:
        warnings.append("Brak report-definitions / rfile — siły mogą być tylko z transcriptu.")
    return warnings


def write_inventory(root: Path, out_path: Path) -> dict:
    inv = scan_folder(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    return inv
