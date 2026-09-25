from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingest.ask import answer
from ingest.chatbot_brief import write_brief
from ingest.cas_setup import parse_cas_setup
from ingest.diff_pack import write_diff
from ingest.fluent_dump import pick_cas_h5, run_fluent_dump, write_force_journal, find_fluent
from ingest.inventory import write_inventory
from ingest.pack import build_pack
from ingest.field_grid import write_grid
from ingest.surface_field import write_profiles, write_surfaces
from ingest.screen_quant import write_quant


def main() -> None:
    parser = argparse.ArgumentParser(description="AeroPack ingest: inventory + pack")
    sub = parser.add_subparsers(dest="cmd", required=True)

    inv = sub.add_parser("inventory", help="Skan folderów case/mesh")
    inv.add_argument("roots", nargs="+", type=Path)
    inv.add_argument("--out", type=Path, default=Path("packs"))

    pk = sub.add_parser("pack", help="Złóż aeropack.json z jednego case'a")
    pk.add_argument("root", type=Path)
    pk.add_argument("--out", type=Path)

    dump = sub.add_parser(
        "dump-forces",
        help="Fluent TUI: siły per strefa z istniejącego .cas.h5/.dat.h5",
    )
    dump.add_argument("root", type=Path)
    dump.add_argument("--out", type=Path)
    dump.add_argument("--procs", type=int, default=4)
    dump.add_argument("--timeout", type=int, default=900)
    dump.add_argument(
        "--journal-only",
        action="store_true",
        help="Tylko zapisz dump_wall_forces.jou, nie odpalaj Fluenta",
    )

    screens = sub.add_parser("screens", help="Kolory klatek postpro na liczby")
    screens.add_argument("root", type=Path)
    screens.add_argument("--out", type=Path)

    grid = sub.add_parser("grid", help="Rzadka siatka parametru z pola wyników")
    grid.add_argument("root", type=Path)
    grid.add_argument("--axis", default="x")
    grid.add_argument("--station", type=float, required=True)
    grid.add_argument("--quantity", default="cp")
    grid.add_argument("--pitch", type=float, default=0.025)
    grid.add_argument("--out", type=Path)

    surf = sub.add_parser("surfaces", help="Mapa 3D Cp, y+ i tarcia na FW, UT i RW")
    surf.add_argument("root", type=Path)
    surf.add_argument("--pitch", type=float, default=0.01)
    surf.add_argument("--out", type=Path)

    prof = sub.add_parser("profiles", help="Cp wzdłuż cięciwy na FW, RW i podłodze")
    prof.add_argument("root", type=Path)
    prof.add_argument("--out", type=Path)

    wake = sub.add_parser("wake", help="Dziura Cp i obrót prędkości na płaszczyźnie za skrzydłem")
    wake.add_argument("root", type=Path)
    wake.add_argument("--station", type=float, required=True)
    wake.add_argument("--y-min", type=float, required=True)
    wake.add_argument("--y-max", type=float, required=True)
    wake.add_argument("--z-min", type=float, required=True)
    wake.add_argument("--z-max", type=float, required=True)
    wake.add_argument("--name", default="slad")
    wake.add_argument("--out", type=Path)

    diff = sub.add_parser("diff", help="Różnice dwóch paczek aeropack.json")
    diff.add_argument("baseline", type=Path)
    diff.add_argument("candidate", type=Path)
    diff.add_argument("--out", type=Path)

    brief = sub.add_parser("brief", help="Markdown dla chatbota z gotowego aeropack.json")
    brief.add_argument("pack_dir", type=Path)

    ask = sub.add_parser("ask", help="Jedno pytanie do paczki: forces, part, slice")
    ask.add_argument("pack", type=Path)
    ask.add_argument("tool")
    ask.add_argument("--part")
    ask.add_argument("--axis", default="x")
    ask.add_argument("--station", type=float, default=0.0)
    ask.add_argument("--field")

    args = parser.parse_args()
    if args.cmd == "inventory":
        args.out.mkdir(parents=True, exist_ok=True)
        for root in args.roots:
            dest = args.out / f"{root.name}.inventory.json"
            data = write_inventory(root, dest)
            print(json.dumps({"root": data["root"], "kind": data["kind"], "warnings": data["warnings"], "out": str(dest)}, ensure_ascii=False, indent=2))
    elif args.cmd == "pack":
        out = args.out or Path("packs") / args.root.name
        pack = build_pack(args.root, out)
        print(json.dumps({"out": str(out), "kind": pack["identity"]["kind"], "warnings": pack["warnings"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "dump-forces":
        out = args.out or Path("packs") / args.root.name
        out.mkdir(parents=True, exist_ok=True)
        from ingest.inventory import scan_folder

        inv_data = scan_folder(args.root)
        cas_paths = [args.root / rel for rel in inv_data["files"]["cas"]]
        setup = parse_cas_setup(cas_paths)
        cx_vec = setup.get("cxForceVector") or [1.0, 0.0, 0.0]
        cz_vec = setup.get("czForceVector") or [0.0, 0.0, -1.0]
        cas_h5 = pick_cas_h5(cas_paths)
        result = {"journalOnly": args.journal_only, "cxForceVector": cx_vec, "czForceVector": cz_vec}
        if cas_h5 is None:
            result["ok"] = False
            result["reason"] = "Brak .cas.h5"
        elif args.journal_only:
            journal = write_force_journal(cas_h5, out, cx_vec, cz_vec)
            result.update({"ok": True, "journal": str(journal), "fluent": str(find_fluent())})
        else:
            result.update(run_fluent_dump(cas_h5, out, cx_vec, cz_vec, procs=args.procs, timeout_s=args.timeout))
            if result.get("ok"):
                pack = build_pack(args.root, out)
                result["pack"] = str(out / "aeropack.json")
                result["componentAxes"] = list((pack.get("kpis") or {}).get("components") or {})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "screens":
        out = args.out or Path("quant") / args.root.name / "ekrany.json"
        data = write_quant(args.root, out)
        print(json.dumps({"out": str(out), "images": data["images"], "skipped": data["skipped"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "grid":
        out = args.out or Path("quant") / args.root.name / f"grid-{args.axis}-{args.station}-{args.quantity}.json"
        data = write_grid(
            args.root,
            out,
            axis=args.axis,
            station=args.station,
            quantity=args.quantity,
            pitch=args.pitch,
        )
        print(json.dumps({"out": str(out), "cells": data["cells"], "ny": data["ny"], "nz": data["nz"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "wake":
        out = args.out or Path("quant") / args.root.name / f"slad-{args.name}.json"
        data = write_grid(
            args.root,
            out,
            axis="x",
            station=args.station,
            quantity="wake",
            search_box=(args.y_min, args.y_max, args.z_min, args.z_max),
        )
        print(json.dumps({"out": str(out), "wir": data.get("wir"), "cells": data.get("cells")}, ensure_ascii=False, indent=2))
    elif args.cmd == "diff":
        out = args.out or Path("quant") / "diff.json"
        data = write_diff(args.baseline, args.candidate, out)
        print(json.dumps({"out": str(out), "delta_cd": data["delta_cd"], "delta_cl": data["delta_cl"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "brief":
        pack = json.loads((args.pack_dir / "aeropack.json").read_text(encoding="utf-8"))
        dest = write_brief(pack, args.pack_dir)
        print(json.dumps({"out": str(dest)}, ensure_ascii=False, indent=2))
    elif args.cmd == "ask":
        payload = answer(
            args.pack,
            args.tool,
            {"part": args.part, "axis": args.axis, "station": args.station, "field": args.field},
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.cmd == "surfaces":
        out = args.out or Path("quant") / args.root.name / "powierzchnie.json"
        data = write_surfaces(args.root, out, pitch=args.pitch)
        summary = [
            {"id": item["id"], "punktow": item["punktow"], "scianek": item["scianek"]}
            for item in data["powierzchnie"]
        ]
        print(json.dumps({"out": str(out), "powierzchnie": summary}, ensure_ascii=False, indent=2))
    elif args.cmd == "profiles":
        out = args.out or Path("quant") / args.root.name / "profile.json"
        data = write_profiles(args.root, out)
        brief = []
        for wing in data["skrzydla"]:
            brief.append({"id": wing["id"], "przekroje": len(wing["przekroje"])})
        print(json.dumps({"out": str(out), "skrzydla": brief}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
