"""Differences between two AeroPack JSON files. The model should not subtract these itself."""

from __future__ import annotations

import json
from pathlib import Path


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _dig(data: dict, *keys):
    cur = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _delta(new, old):
    a, b = _num(new), _num(old)
    if a is None or b is None:
        return None
    return round(a - b, 4)


def _cop_x(pack: dict):
    """Metres from the moment reference. Positive means the downforce sits further back."""
    cm = _num(_dig(pack, "kpis", "cm"))
    cz = _num(_dig(pack, "kpis", "cz"))
    length = _num(_dig(pack, "kpis", "references", "referenceLengthM", "value"))
    if length is None:
        length = _num(_dig(pack, "methods", "referenceLengthM"))
    if cm is None or cz is None or length is None or cz == 0:
        return None
    return cm * length / cz


def _groups(pack: dict) -> dict:
    groups = _dig(pack, "kpis", "components", "groups")
    return groups if isinstance(groups, dict) else {}


def diff_packs(baseline: dict, candidate: dict) -> dict:
    base_k = baseline.get("kpis") or {}
    new_k = candidate.get("kpis") or {}
    cop_old = _cop_x(baseline)
    cop_new = _cop_x(candidate)
    shared = sorted(set(_groups(baseline)) & set(_groups(candidate)))
    components = []
    for name in shared:
        old = _groups(baseline)[name] or {}
        new = _groups(candidate)[name] or {}
        components.append(
            {
                "nazwa": name,
                "delta_cd": _delta(new.get("Cd"), old.get("Cd")),
                "delta_docisk": _delta(new.get("downforceCoeff"), old.get("downforceCoeff")),
            }
        )
    return {
        "opis": (
            "Różnice liczone tutaj, nie w głowie modelu. "
            "Dodatnia delta docisku to więcej docisku w drugiej paczce. "
            "Środek parcia: cm * długość odniesienia / cz, w metrach od punktu momentu. "
            "Dodatnie przesunięcie znaczy, że docisk siadł bardziej z tyłu. "
            "Części są tylko te, które są w obu paczkach."
        ),
        "baza": _dig(baseline, "identity", "caseId"),
        "nowa": _dig(candidate, "identity", "caseId"),
        "delta_cd": _delta(new_k.get("Cd"), base_k.get("Cd")),
        "delta_cl": _delta(new_k.get("Cl"), base_k.get("Cl")),
        "delta_ld": _delta(new_k.get("LOverD"), base_k.get("LOverD")),
        "srodek_parcia_baza_m": None if cop_old is None else round(cop_old, 4),
        "srodek_parcia_nowa_m": None if cop_new is None else round(cop_new, 4),
        "przesuniecie_srodka_parcia_m": _delta(cop_new, cop_old),
        "komponenty": components,
    }


def write_diff(base_path: Path, new_path: Path, out: Path) -> dict:
    baseline = json.loads(base_path.read_text(encoding="utf-8"))
    candidate = json.loads(new_path.read_text(encoding="utf-8"))
    data = diff_packs(baseline, candidate)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
