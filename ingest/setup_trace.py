"""What the transcript actually records. This is not a Fluent journal."""

from __future__ import annotations

import re
from pathlib import Path

TUI_RE = re.compile(r"^>\s*(/[^\n]+)", re.M)
VALUE_RE = re.compile(
    r'RealEntry\d+\(([^)]+)\).*?\'\(\s*([^)]+?)\s*\)',
)
MODEL_RE = re.compile(r"k-omega \(2 eqn\)|k-epsilon \(2 eqn\)|Transition SST|Spalart-Allmaras")


def _dedupe(items: list[str], limit: int) -> list[str]:
    seen: list[str] = []
    for item in items:
        text = " ".join(item.split())
        if text in seen:
            continue
        seen.append(text)
        if len(seen) >= limit:
            break
    return seen


def extract_setup_trace(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    commands = _dedupe(TUI_RE.findall(text), 40)
    values = []
    for match in VALUE_RE.finditer(text):
        values.append(f"{match.group(1)} = {match.group(2)}")
    models = _dedupe(MODEL_RE.findall(text), 8)
    return {
        "file": path.name,
        "tui": commands,
        "values": _dedupe(values, 20),
        "models": models,
    }


def merge_traces(paths: list[Path]) -> dict:
    traces = [extract_setup_trace(path) for path in paths]
    return {
        "files": [item["file"] for item in traces],
        "tui": _dedupe([line for item in traces for line in item["tui"]], 40),
        "values": _dedupe([line for item in traces for line in item["values"]], 20),
        "models": _dedupe([line for item in traces for line in item["models"]], 8),
        "note": (
            "To nie jest journal. Brak .jou znaczy, że GUI nie zapisało skryptu do powtórzenia. "
            "Poniżej są komendy TUI i wartości wyklikane w transcriptcie. "
            "Siatkę powtarza plik .wft, a solver jest w .cas.h5."
        ),
    }
