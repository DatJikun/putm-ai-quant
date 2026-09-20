from __future__ import annotations

from pathlib import Path


def parse_rfile(path: Path) -> dict:
    last = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 2 and parts[0].replace(".", "", 1).isdigit():
                last = parts
    if last is None:
        return {"file": path.name, "empty": True}
    iteration = int(float(last[0]))
    averaged = float(last[1])
    instantaneous = float(last[2]) if len(last) > 2 else averaged
    name = path.name.replace("-rfile.out", "").replace(".out", "")
    return {
        "file": path.name,
        "monitor": name,
        "iterations": iteration,
        "averaged": averaged,
        "instantaneous": instantaneous,
    }


def parse_rfiles(paths: list[Path]) -> dict:
    monitors = [parse_rfile(p) for p in paths]
    by_name = {m["monitor"]: m for m in monitors if "monitor" in m}
    iterations = max((m.get("iterations") or 0 for m in monitors), default=0)
    return {"iterations": iterations, "monitors": by_name}
