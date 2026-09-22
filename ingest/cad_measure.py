from __future__ import annotations

import math
from pathlib import Path

try:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.Bnd import Bnd_Box
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    HAS_OCP = True
except ImportError:  # pragma: no cover - środowisko bez OpenCASCADE
    HAS_OCP = False


def _require_ocp() -> None:
    if not HAS_OCP:
        raise ImportError("cad_measure wymaga pakietu ocp (OpenCASCADE). Zainstaluj: pip install ocp")

FW_PREFIXES = (
    "PM09-A-FW-Main_Profile",
    "PM09-A-FW-Profile",
    "PM09-A-FW-End_plate",
    "PM09-A-FW-Middle_Plate",
    "PM09-A-FW-Back-Plate",
    "PM09-A-REF-EDGE-FW",
    "PM09-A-REF-BOX-Front_Wing",
)

SKIP_IF_CONTAINS = ("Lustro",)
SKIP_EXACT_BITS = ("Assembly",)
CHORD_HINTS = (
    "Main_Profile",
    "Main_plane",
    "Main_plane-CFD",
    "-Profile",
    "Plane1",
    "Plane2",
    "Plane3",
    "UT-CFD",
)


def _skip_name(name: str) -> bool:
    if not name or name == "unnamed":
        return True
    if any(s in name for s in SKIP_IF_CONTAINS):
        return True
    if "Assembly" in name and "^" not in name:
        return True
    return False


def wants_chord(name: str) -> bool:
    return any(h in name for h in CHORD_HINTS)


def _label_name(label) -> str:
    _require_ocp()
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return str(attr.Get().ToExtString())
    return ""


def _bbox(shape) -> dict:
    _require_ocp()
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return {
        "xmin": xmin,
        "ymin": ymin,
        "zmin": zmin,
        "xmax": xmax,
        "ymax": ymax,
        "zmax": zmax,
        "dx": xmax - xmin,
        "dy": ymax - ymin,
        "dz": zmax - zmin,
    }


def _walk_shapes(shape_tool, label, loc: TopLoc_Location, out: list) -> None:
    _require_ocp()
    name = _label_name(label)
    if XCAFDoc_ShapeTool.IsAssembly_s(label):
        comps = TDF_LabelSequence()
        XCAFDoc_ShapeTool.GetComponents_s(label, comps, False)
        for i in range(1, comps.Length() + 1):
            comp = comps.Value(i)
            referred = TDF_Label()
            if XCAFDoc_ShapeTool.IsReference_s(comp):
                XCAFDoc_ShapeTool.GetReferredShape_s(comp, referred)
            else:
                referred = comp
            child_loc = loc.Multiplied(XCAFDoc_ShapeTool.GetLocation_s(comp))
            _walk_shapes(shape_tool, referred, child_loc, out)
        return
    shape = XCAFDoc_ShapeTool.GetShape_s(label)
    if shape.IsNull():
        return
    if not loc.IsIdentity():
        shape = BRepBuilderAPI_Transform(shape, loc.Transformation(), True).Shape()
    out.append({"name": name or "unnamed", "shape": shape})


def load_named_solids(step_path: Path) -> list[dict]:
    _require_ocp()
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    status = reader.ReadFile(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Nie da się wczytać STEP: {step_path} (status {status})")
    reader.Transfer(doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)
    solids: list[dict] = []
    for i in range(1, free.Length() + 1):
        _walk_shapes(shape_tool, free.Value(i), TopLoc_Location(), solids)
    return solids


def _section_points(shape, y: float) -> list[tuple[float, float]]:
    _require_ocp()
    plane = gp_Pln(gp_Pnt(0.0, y, 0.0), gp_Dir(0.0, 1.0, 0.0))
    sec = BRepAlgoAPI_Section(shape, plane, True)
    pts: list[tuple[float, float]] = []
    if sec.IsDone():
        exp = TopExp_Explorer(sec.Shape(), TopAbs_EDGE)
        while exp.More():
            edge = exp.Current()
            try:
                curve = BRepAdaptor_Curve(edge)
                discret = GCPnts_QuasiUniformDeflection(curve, 0.8)
                if discret.IsDone():
                    for i in range(1, discret.NbPoints() + 1):
                        p = discret.Value(i)
                        pts.append((p.X(), p.Z()))
            except Exception:
                pass
            exp.Next()
    return pts


def _chord_from_points(pts: list[tuple[float, float]]) -> dict | None:
    if len(pts) < 4:
        return None
    if len(pts) > 400:
        step = max(1, len(pts) // 400)
        pts = pts[::step]
    best = 0.0
    le = te = pts[0]
    for i, a in enumerate(pts):
        ax, az = a
        for bx, bz in pts[i + 1 :]:
            d2 = (ax - bx) ** 2 + (az - bz) ** 2
            if d2 > best:
                best = d2
                le, te = a, (bx, bz)
    if le[0] > te[0]:
        le, te = te, le
    chord = math.sqrt(best)
    dx = te[0] - le[0]
    dz = te[1] - le[1]
    incidence = math.degrees(math.atan2(dz, dx))
    return {
        "chordMm": round(chord, 2),
        "incidenceDeg": round(incidence, 2),
        "le": {"xMm": round(le[0], 2), "zMm": round(le[1], 2)},
        "te": {"xMm": round(te[0], 2), "zMm": round(te[1], 2)},
    }


def measure_solid(item: dict, do_chord: bool = True) -> dict:
    bb = _bbox(item["shape"])
    if bb["ymin"] < 0:
        y_cut = 0.5 * (bb["ymin"] + min(bb["ymax"], 0.0))
    else:
        y_cut = bb["ymin"] + 0.5 * bb["dy"]
    half_span = round(abs(min(bb["ymin"], 0.0)), 2)
    pts: list = []
    chord = None
    section_method = None
    if do_chord:
        pts = _section_points(item["shape"], y_cut)
        section_method = "brep" if len(pts) >= 4 else "empty"
        chord = _chord_from_points(pts) if section_method == "brep" else None
    rec = {
        "name": item["name"],
        "bboxMm": {k: round(v, 2) for k, v in bb.items()},
        "spanMm": round(abs(bb["dy"]), 2),
        "halfSpanMm": half_span,
        "sectionYMm": round(y_cut, 2),
        "sectionPointCount": len(pts),
        "sectionMethod": section_method,
        "chord": chord,
    }
    if do_chord and section_method == "empty":
        rec["geometryCutError"] = (
            f"BRepAlgoAPI_Section puste na Y={round(y_cut, 2)} mm — "
            "nie zgaduję cięciwy z siatki."
        )
    return rec


def is_front_wing(name: str) -> bool:
    if _skip_name(name):
        return False
    return "FW" in name


def is_car_part(name: str) -> bool:
    if _skip_name(name):
        return False
    return name.startswith("PM09")


def measure_step(step_path: Path, only_fw: bool = True) -> list[dict]:
    solids = load_named_solids(step_path)
    if only_fw:
        chosen = [s for s in solids if is_front_wing(s["name"])]
    else:
        chosen = [s for s in solids if is_car_part(s["name"])]
    rows = []
    for s in chosen:
        rows.append(measure_solid(s, do_chord=wants_chord(s["name"])))
    return rows


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("step", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    rows = measure_step(args.step, only_fw=not args.all)
    text = json.dumps(rows, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
