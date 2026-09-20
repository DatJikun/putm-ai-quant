from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingest.cas_setup import parse_cas_setup
from ingest.fluent_dump import pick_cas_h5, run_fluent_dump, write_force_journal, find_fluent
from ingest.inventory import write_inventory
from ingest.pack import build_pack


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


if __name__ == "__main__":
    main()
