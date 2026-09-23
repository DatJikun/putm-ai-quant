"""Half-car STEP for SpaceClaim: named groups, domain, fan and radiator pulled out.

Share topology is left for SpaceClaim. Bodies stay separate.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from OCP.BOPAlgo import BOPAlgo_BOP, BOPAlgo_COMMON
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Pnt

from ingest.cad_measure import _bbox, load_named_solids

Y_PLANE = 0.05  # mm, treats a face on Y=0 as already on the symmetry side
FRONT_WHEEL = (35.0, 205.0)
REAR_WHEEL = (1585.0, 215.0)

GROUP_ORDER = (
    "domain",
    "ref",
    "surface_fw",
    "surface_rw",
    "surface_ut",
    "surface_mono",
    "surface_front_wheel-rotary",
    "surface_front_wheel-steady",
    "surface_rear_wheel-rotary",
    "surface_rear_wheel-steady",
    "surface_rd",
    "surface_fan",
    "mrf_fan-body",
    "radiator_core-body",
)


def _count(shape, kind) -> int:
    exp = TopExp_Explorer(shape, kind)
    n = 0
    while exp.More():
        n += 1
        exp.Next()
    return n


def _solids(shape) -> list:
    out = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        out.append(TopoDS.Solid_s(exp.Current()))
        exp.Next()
    return out


def _half_tool():
    return BRepPrimAPI_MakeBox(
        gp_Pnt(-50000.0, -20000.0, -10000.0),
        gp_Pnt(50000.0, 0.0, 20000.0),
    ).Solid()


def _is_link(bb: dict) -> bool:
    small, mid, big = sorted((bb["dx"], bb["dy"], bb["dz"]))
    disc = small < 15 and mid > 100 and big < mid * 1.4
    if disc:
        return False
    return small < 50 and big > 150


def _wheel_group(bb: dict) -> str | None:
    if _is_link(bb):
        return None
    cx = 0.5 * (bb["xmin"] + bb["xmax"])
    cz = 0.5 * (bb["zmin"] + bb["zmax"])
    bands = (
        ("front", *FRONT_WHEEL, -920.0, -470.0),
        ("rear", *REAR_WHEEL, -805.0, -455.0),
    )
    for side, wx, wz, y0, y1 in bands:
        overlaps = bb["ymax"] >= y0 and bb["ymin"] <= y1
        if not overlaps:
            continue
        if abs(cx - wx) < 250 and abs(cz - wz) < 160:
            if bb["dz"] > 500 or bb["zmin"] < 0:
                return f"surface_{side}_wheel-rotary"
            return f"surface_{side}_wheel-steady"
    return None


def classify(parent: str, bb: dict, nfaces: int) -> str | None:
    if parent.startswith("Lustro") or bb["ymin"] >= Y_PLANE:
        return None
    if "REF-BOX" in parent or "REF-EDGE" in parent:
        return "ref"
    if parent == "DOMAIN":
        return "domain"
    if parent.startswith("PM09-A-FW"):
        return "surface_fw"
    if parent.startswith("PM09-A-RW"):
        return "surface_rw"
    if parent.startswith("PM09-A-UT"):
        return "surface_ut"
    if parent.startswith("PM09-A-CS-Fan"):
        if nfaces <= 6:
            return "mrf_fan-body"
        if nfaces >= 20:
            return "surface_fan"
        return "surface_rd"
    if parent.startswith("PM09-A-CS-Schrouds"):
        if nfaces <= 6 and bb["dx"] < 80:
            return "radiator_core-body"
        return "surface_rd"
    if parent.startswith("PM09-C"):
        return "surface_mono"
    wheel = _wheel_group(bb)
    if wheel:
        return wheel
    return "surface_mono"


def _vertex_y(shape) -> tuple[float, float] | None:
    exp = TopExp_Explorer(shape, TopAbs_VERTEX)
    ymin = ymax = None
    while exp.More():
        y = BRep_Tool.Pnt_s(TopoDS.Vertex_s(exp.Current())).Y()
        ymin = y if ymin is None else min(ymin, y)
        ymax = y if ymax is None else max(ymax, y)
        exp.Next()
    if ymin is None:
        return None
    return ymin, ymax


def _accept_half(shape) -> bool:
    bounds = _vertex_y(shape)
    return bounds is not None and bounds[1] <= 0.5 and _solids(shape)


def _keep_half(shape, bb: dict, half_tool):
    if bb["ymin"] >= Y_PLANE:
        return None
    if bb["ymax"] <= Y_PLANE:
        return shape
    tool = BRepBuilderAPI_Copy(half_tool).Shape()
    op = BRepAlgoAPI_Common(shape, tool)
    if op.IsDone() and _accept_half(op.Shape()):
        return op.Shape()
    # Dokładnie Y=0 kasuje bryły, które już mają ścianę na symetrii (monokok).
    tight = BRepPrimAPI_MakeBox(
        gp_Pnt(bb["xmin"] - 20.0, bb["ymin"] - 20.0, bb["zmin"] - 20.0),
        gp_Pnt(bb["xmax"] + 20.0, 0.02, bb["zmax"] + 20.0),
    ).Solid()
    fuzzy = BOPAlgo_BOP()
    fuzzy.SetOperation(BOPAlgo_COMMON)
    fuzzy.AddArgument(shape)
    fuzzy.AddTool(tight)
    fuzzy.SetFuzzyValue(0.01)
    fuzzy.Perform()
    if _accept_half(fuzzy.Shape()):
        return fuzzy.Shape()
    return None


def _compound(shapes) -> TopoDS_Compound:
    comp = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(comp)
    for shape in shapes:
        builder.Add(comp, shape)
    return comp


def _write_step(groups: dict[str, list], path: Path) -> None:
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    for name in GROUP_ORDER:
        items = groups.get(name) or []
        if not items:
            continue
        shape = items[0][1] if len(items) == 1 else _compound([s for _, s in items])
        label = shape_tool.AddShape(shape, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.Transfer(doc, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"zapis STEP nie doszedł (status {status})")


def prepare(step_path: Path, out_path: Path, report_path: Path, dry: bool) -> dict[str, list]:
    named = load_named_solids(step_path)
    half_tool = None if dry else _half_tool()
    groups: dict[str, list] = {name: [] for name in GROUP_ORDER}
    lines = [
        "Połowa Y<=0. Domain bez zmian. MRF i radiator osobno, bez share.",
        "Koło: opona (schodzi pod Z=0) = rotary, piasta i tarcza = steady.",
        "Wahacze idą do surface_mono.",
        "",
    ]
    for item in named:
        for index, solid in enumerate(_solids(item["shape"]), 1):
            bb = _bbox(solid)
            nfaces = _count(solid, TopAbs_FACE)
            group = classify(item["name"], bb, nfaces)
            tag = item["name"] if len(_solids(item["shape"])) == 1 else f"{item['name']}#{index}"
            if group is None:
                lines.append(f"DROP\t{tag}\tymin={bb['ymin']:.1f}")
                continue
            if not dry and bb["ymin"] < Y_PLANE < bb["ymax"]:
                print(f"cut {tag}", flush=True)
            kept = solid if dry else _keep_half(solid, bb, half_tool)
            if kept is None:
                kind = "FAIL" if bb["ymin"] < Y_PLANE < bb["ymax"] else "DROP"
                lines.append(f"{kind}\t{tag}\tymin={bb['ymin']:.1f}")
                continue
            pieces = _solids(kept) if not dry else [solid]
            if not pieces:
                lines.append(f"FAIL\t{tag}\tcięcie puste")
                continue
            for piece_i, piece in enumerate(pieces, 1):
                piece_bb = _bbox(piece) if not dry else bb
                y_bounds = _vertex_y(piece) if not dry else (bb["ymin"], bb["ymax"])
                if y_bounds is None or y_bounds[1] > 0.5:
                    lines.append(f"FAIL\t{tag}\tymax={y_bounds}")
                    continue
                piece_tag = tag if len(pieces) == 1 else f"{tag}.{piece_i}"
                groups[group].append((piece_tag, piece))
                lines.append(
                    f"{group}\t{piece_tag}\t"
                    f"X {piece_bb['xmin']:.0f}..{piece_bb['xmax']:.0f}\t"
                    f"Y {y_bounds[0]:.1f}..{y_bounds[1]:.1f}\t"
                    f"Z {piece_bb['zmin']:.0f}..{piece_bb['zmax']:.0f}"
                )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not dry:
        _write_step(groups, out_path)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "step",
        type=Path,
        nargs="?",
        default=Path(r"c:\Users\mwojn\Desktop\SYMULACJE\Baseline\BASELINEiter002\model\Baseline002.STEP"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(r"c:\Users\mwojn\Desktop\SYMULACJE\Baseline\BASELINEiter002\model\Baseline002_half.STEP"),
    )
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()
    report = args.out.with_suffix(".groups.txt")
    groups = prepare(args.step, args.out, report, args.dry)
    for name in GROUP_ORDER:
        print(f"{name}: {len(groups[name])}")
    print("report", report)
    if not args.dry:
        print("step", args.out)


if __name__ == "__main__":
    main()
