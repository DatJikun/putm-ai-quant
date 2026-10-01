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
from ingest.mesh_study import write_study
from ingest.metapack import export_meta, render_from_meta, verify_meta
from ingest.pack import build_pack
from ingest.compare import compare
from ingest.conservation import write_conservation
from ingest.plane_images import render_all
from ingest.why import explain, render as render_why
from ingest.slices import load_slices
from ingest.viewer_export import export_viewer_package
from ingest.report import build_report
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

    rep = sub.add_parser(
        "report",
        help="Wszystko jednym poleceniem: pack, residua, bilans masy, siły na części, y+ i oderwania, raport z oceną",
    )
    rep.add_argument("root", type=Path)
    rep.add_argument("--out", type=Path)
    rep.add_argument("--bez-przeplywu", action="store_true", help="Pomiń skan przepływu, jakość siatki i obrazki (najdłuższe kroki)")
    rep.add_argument("--bez-obrazow", action="store_true", help="Pomiń obrazki przekrojów i galerię")

    ms = sub.add_parser(
        "mesh-study",
        help="Test niezależności od siatki: 2-3 paczki tego samego bolidu na różnych siatkach (GCI przy trzech)",
    )
    ms.add_argument("packs", nargs="+", type=Path, help="foldery paczek albo pliki aeropack.json")
    ms.add_argument("--out", type=Path, default=Path("quant"))

    img = sub.add_parser(
        "images",
        help="Obrazki przekrojów w tych samych płaszczyznach co w CFD-Post (150 na oś) i galeria HTML, z plików wyników",
    )
    img.add_argument("root", type=Path)
    img.add_argument("--out", type=Path)
    img.add_argument("--limit", type=int, help="Tylko pierwsze N płaszczyzn na oś (do próby)")
    img.add_argument("--bez-powierzchni", action="store_true", help="Pomiń widoki Cp, tarcia i y+ na ścianie")

    cmp_ = sub.add_parser(
        "compare",
        help="Porównanie dwóch lub więcej symulacji: tabele różnic, wykresy i strona HTML (pierwsza to punkt odniesienia)",
    )
    cmp_.add_argument("folders", nargs="+", type=Path, help="foldery paczek zrobione przez `report`")
    cmp_.add_argument("--out", type=Path, default=Path("quant") / "porownanie")
    cmp_.add_argument("--nazwy", help="Własne nazwy po przecinku, w tej samej kolejności")

    vw = sub.add_parser(
        "viewer",
        help="Eksport do przeglądarki 3D (CFD3DViewer): pole przepływu, powierzchnia bolidu i linie prądu jako folder <nazwa>.viewer",
    )
    vw.add_argument("root", type=Path)
    vw.add_argument("--out", type=Path)
    vw.add_argument("--krok", type=float, default=0.02, help="Rozmiar kafelka siatki objętościowej w metrach")

    mt = sub.add_parser(
        "meta",
        help="Metaplik: jeden folder z meta.json (wszystkie liczby i wnioski) i mapami w dwóch rozdzielczościach (1 cm i 3 mm) zamiast plików CFD-Post i zdjęć",
    )
    mt.add_argument("root", type=Path)
    mt.add_argument("--out", type=Path)

    mr = sub.add_parser("meta-render", help="Narysuj obrazki z samych map metapliku (dowód, że zdjęcia nie są potrzebne)")
    mr.add_argument("meta_dir", type=Path)
    mr.add_argument("--out", type=Path, required=True)
    mr.add_argument("--powierzchnia", default="3mm", choices=["1cm", "3mm"])

    mv = sub.add_parser("meta-verify", help="Sprawdź kompletność i sumy kontrolne folderu metapliku")
    mv.add_argument("meta_dir", type=Path)

    wy = sub.add_parser(
        "why",
        help="Dlaczego druga symulacja różni się od pierwszej: rozkład zmiany na części, miejsca, środek docisku, geometrię i przepływ (potrzebne metapliki)",
    )
    wy.add_argument("reference", type=Path, help="folder paczki punktu odniesienia")
    wy.add_argument("new", type=Path, help="folder paczki, o którą pytasz")
    wy.add_argument("--out", type=Path)

    cons = sub.add_parser("conservation", help="Residua i bilans masy z .dat.h5")
    cons.add_argument("root", type=Path)
    cons.add_argument("--out", type=Path)

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

    prof = sub.add_parser(
        "profiles",
        help="Cp wzdłuż cięciwy na FW, RW i podłodze (domyślnie do packs/<case>/profile.json, skąd czyta go ask)",
    )
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

    ask = sub.add_parser("ask", help="Jedno pytanie do paczki: forces, part, device, slice, findings, credibility, station, wall_value, explain_change, question")
    ask.add_argument("pack", type=Path)
    ask.add_argument("tool")
    ask.add_argument("--part")
    ask.add_argument("--device", help="id karty z geometry.yaml; bez niego lista id")
    ask.add_argument("--axis", default="x")
    ask.add_argument("--station", type=float, default=0.0)
    ask.add_argument("--field")
    ask.add_argument("--other", help="nazwa drugiej paczki (explain_change, question)")
    ask.add_argument("--pytanie", help="pytanie po polsku (tool question)")
    ask.add_argument("--limit", type=int, default=10)
    ask.add_argument("--waga")
    ask.add_argument("--x", type=float)
    ask.add_argument("--y", type=float)
    ask.add_argument("--z", type=float)

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
    elif args.cmd == "report":
        out = args.out or Path("packs") / args.root.name
        rep_data = build_report(args.root, out, flow=not args.bez_przeplywu, images=not args.bez_obrazow)
        verdict = rep_data["verdict"]
        print(json.dumps({"out": str(out), "skrot": str(out / "SKROT.md"), "pelny": str(out / "PELNY.md"), "galeria": str(out / "obrazy" / "galeria.html"), "werdykt": verdict["label"], "ocena": verdict["status"], "na_czerwono": verdict["bad"], "na_zolto": verdict["warn"], "bez_danych": verdict["missing"], "brakuje": rep_data["missing"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "mesh-study":
        result = write_study(args.packs, args.out / "siatka.json", args.out / "siatka.md")
        print(
            json.dumps(
                {
                    "out": str(args.out / "siatka.md"),
                    "porownywalne": result["comparable"],
                    "zastrzezenia": result["issues"],
                    "wyniki": {q["id"]: q.get("gciFinePct", q.get("relativeDifferencePct")) for q in result["quantities"]},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.cmd == "images":
        out = args.out or Path("packs") / args.root.name / "obrazy"
        pack_file = Path("packs") / args.root.name / "aeropack.json"
        if not pack_file.exists():
            build_pack(args.root, pack_file.parent)
        refs = json.loads(pack_file.read_text(encoding="utf-8"))["kpis"]["references"]
        index_file = pack_file.parent / "images" / "index.json"
        result = render_all(
            args.root,
            out,
            rho=refs["rho"]["value"],
            mu=refs["mu"]["value"],
            speed_ms=refs["speedMs"]["value"],
            template=load_slices(),
            images_index=json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else None,
            cache_dir=Path("quant") / args.root.name / ".cache",
            surface=not args.bez_powierzchni,
            limit=args.limit,
            title=f"Przekroje przepływu: {args.root.name}",
        )
        print(json.dumps({"out": str(out), "galeria": str(out / result["gallery"]), "obrazow": result["images"], "plaszczyzn": result["planes"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "compare":
        labels = [n.strip() for n in args.nazwy.split(",")] if args.nazwy else None
        result = compare(args.folders, args.out, labels)
        print(json.dumps({"out": str(args.out / "POROWNANIE.html"), "symulacje": result["names"], "zastrzezenia": result["issues"], "wykresow": result["charts"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "viewer":
        import re

        pack_file = Path("packs") / args.root.name / "aeropack.json"
        if not pack_file.exists():
            build_pack(args.root, pack_file.parent)
        pack = json.loads(pack_file.read_text(encoding="utf-8"))
        refs = pack["kpis"]["references"]
        ident = pack.get("identity") or {}
        case_id = re.sub(r"[^A-Za-z0-9_.-]", "_", ident.get("caseId") or args.root.name)
        out = args.out or Path("packs") / args.root.name / "viewer"
        package = export_viewer_package(
            args.root,
            out,
            case_id=case_id,
            display_name=f"{ident.get('vehicle', 'bolid')} {ident.get('caseId', args.root.name)}, {refs['speedMs']['value']:g} m/s",
            rho=refs["rho"]["value"],
            mu=refs["mu"]["value"],
            speed_ms=refs["speedMs"]["value"],
            length_m=(refs.get("referenceLengthM") or {}).get("value") or 1.53,
            cache_dir=Path("quant") / args.root.name / ".cache",
            spacing=args.krok,
        )
        print(json.dumps({"pakiet": str(package)}, ensure_ascii=False, indent=2))
    elif args.cmd == "meta":
        pack_dir = Path("packs") / args.root.name
        if not (pack_dir / "raport.json").exists():
            build_report(args.root, pack_dir)
        refs = json.loads((pack_dir / "aeropack.json").read_text(encoding="utf-8"))["kpis"]["references"]
        index_file = pack_dir / "images" / "index.json"
        result = export_meta(
            args.root,
            pack_dir,
            args.out or pack_dir / "meta",
            rho=refs["rho"]["value"],
            mu=refs["mu"]["value"],
            speed_ms=refs["speedMs"]["value"],
            template=load_slices(),
            images_index=json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else None,
            cache_dir=Path("quant") / args.root.name / ".cache",
        )
        mb = {k: round(v / 1e6, 2) for k, v in result["rozmiary_bajty"].items()}
        print(json.dumps({"meta": result["meta"], "rozmiary_MB": mb, "razem_MB": round(result["razem_bajty"] / 1e6, 2), "oryginaly_GB": round(result["oryginaly_bajty"] / 1e9, 2)}, ensure_ascii=False, indent=2))
    elif args.cmd == "meta-render":
        print(json.dumps(render_from_meta(args.meta_dir, args.out, surface_label=args.powierzchnia), ensure_ascii=False, indent=2))
    elif args.cmd == "meta-verify":
        problems = verify_meta(args.meta_dir)
        print(json.dumps({"ok": not problems, "problemy": problems}, ensure_ascii=False, indent=2))
    elif args.cmd == "why":
        meta_a = json.loads((args.reference / "meta" / "meta.json").read_text(encoding="utf-8"))
        meta_b = json.loads((args.new / "meta" / "meta.json").read_text(encoding="utf-8"))
        result = explain(meta_a, meta_b)
        out = args.out or Path("quant") / "dlaczego"
        out.mkdir(parents=True, exist_ok=True)
        (out / "DLACZEGO.md").write_text(render_why(result), encoding="utf-8")
        (out / "dlaczego.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"out": str(out / "DLACZEGO.md"), "pewnosc": result["pewnosc"]["poziom"], "wnioski": result["wnioski"]}, ensure_ascii=False, indent=2))
    elif args.cmd == "conservation":
        out = args.out or Path("quant") / args.root.name / "zachowanie.json"
        cons_data = write_conservation(args.root, out)
        print(json.dumps({"out": str(out), "residua_ponizej_limitu": (cons_data["residuals"] or {}).get("allBelowLimit"), "bilans_masy_zamyka": (cons_data["massBalance"] or {}).get("closes"), "brakuje": cons_data["missing"]}, ensure_ascii=False, indent=2))
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
            {
                "part": args.part,
                "device": args.device,
                "axis": args.axis,
                "station": args.station,
                "field": args.field,
                "other": args.other,
                "text": args.pytanie,
                "limit": args.limit,
                "waga": args.waga,
                "x": args.x,
                "y": args.y,
                "z": args.z,
            },
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
        out = args.out or Path("packs") / args.root.name / "profile.json"
        data = write_profiles(args.root, out)
        brief = []
        for wing in data["skrzydla"]:
            brief.append({"id": wing["id"], "przekroje": len(wing["przekroje"])})
        print(json.dumps({"out": str(out), "skrzydla": brief}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
