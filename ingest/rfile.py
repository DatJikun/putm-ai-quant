from __future__ import annotations

from pathlib import Path

HISTORY_KEEP = 600
WINDOW = 200


def parse_rfile(path: Path) -> dict:
    """Columns after the header: iteration, report value (averaged if set), instantaneous."""
    rows: list[tuple[int, float, float]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2 or not parts[0].replace(".", "", 1).isdigit():
                continue
            try:
                value = float(parts[1])
                inst = float(parts[2]) if len(parts) > 2 else value
            except ValueError:
                continue
            rows.append((int(float(parts[0])), value, inst))
            if len(rows) > HISTORY_KEEP:
                del rows[: len(rows) - HISTORY_KEEP]
    if not rows:
        return {"file": path.name, "empty": True}
    iteration, averaged, instantaneous = rows[-1]
    name = path.name.replace("-rfile.out", "").replace(".out", "")
    return {
        "file": path.name,
        "monitor": name,
        "iterations": iteration,
        "averaged": averaged,
        "instantaneous": instantaneous,
        "stability": stability(rows),
    }


def stability(rows: list[tuple[int, float, float]], window: int = WINDOW) -> dict | None:
    """How much the monitor still moves over the last `window` iterations."""
    if len(rows) < 2:
        return None
    end_it, end_val, _ = rows[-1]
    start = next((row for row in rows if row[0] >= end_it - window), rows[0])
    span = [row for row in rows if row[0] >= start[0]]
    inst = [row[2] for row in span]
    mean = sum(inst) / len(inst)
    scale = abs(end_val) if abs(end_val) > 1e-9 else None
    return {
        "window": end_it - start[0],
        "fromIteration": start[0],
        "startValue": start[1],
        "endValue": end_val,
        "delta": round(end_val - start[1], 6),
        "driftPct": None if scale is None else round(100.0 * (end_val - start[1]) / scale, 3),
        "spreadPct": None if abs(mean) < 1e-9 else round(100.0 * (max(inst) - min(inst)) / abs(mean), 3),
    }


def parse_rfiles(paths: list[Path]) -> dict:
    monitors = [parse_rfile(p) for p in paths]
    by_name = {m["monitor"]: m for m in monitors if "monitor" in m}
    iterations = max((m.get("iterations") or 0 for m in monitors), default=0)
    return {"iterations": iterations, "monitors": by_name}
