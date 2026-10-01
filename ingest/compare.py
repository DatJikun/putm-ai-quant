"""Compare two or more solved cases and show it: tables with differences and charts side by side.

Input is the folder `report` wrote for each case (it holds `raport.json` and `aeropack.json`).
The result is `POROWNANIE.md` and `POROWNANIE.html` (charts drawn inline, nothing to install).
The first case is the baseline: every difference is given against it.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from ingest.documents import markdown_to_html
from ingest.mesh_study import differences
from ingest.report import LIGHT, PART_NAMES, _get

PALETTE = ["#2a6fbb", "#d9541e", "#2f9e6f", "#8a5cc2", "#c9a227", "#5a5a5a"]


# ------------------------------------------------------------------------ loading

def load_case(folder: Path, label: str | None = None) -> dict:
    """Everything `report` saved for one case. Missing files are fine: those parts are skipped."""
    folder = Path(folder)
    pack_file = folder / "aeropack.json" if folder.is_dir() else folder
    folder = pack_file.parent
    pack = json.loads(pack_file.read_text(encoding="utf-8"))
    report_file = folder / "raport.json"
    report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.exists() else {}
    name = label or (pack.get("identity") or {}).get("caseId") or folder.name
    pack["_name"] = name
    return {"name": name, "folder": str(folder), "pack": pack, "report": report}


# ------------------------------------------------------------------------ numbers

def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _delta(value, base) -> tuple[float | None, float | None]:
    value, base = _num(value), _num(base)
    if value is None or base is None:
        return None, None
    diff = value - base
    return diff, None if abs(base) < 1e-12 else 100.0 * diff / abs(base)


def headline(case: dict) -> dict:
    pack = case["pack"]
    kpis = pack.get("kpis") or {}
    refs = kpis.get("references") or {}
    ident = pack.get("identity") or {}
    rho, v, aref = (_num(_get(refs, k, "value")) for k in ("rho", "speedMs", "frontalAreaM2"))
    full = 2.0 if ident.get("halfModel") else 1.0
    q = 0.5 * rho * v * v if rho and v else None

    def newtons(coeff):
        return None if coeff is None or q is None or aref is None else full * coeff * q * aref

    bal = kpis.get("aeroBalance") or {}
    return {
        "Cd": _num(kpis.get("Cd")),
        "downforce": _num(kpis.get("downforceCoeff")),
        "LOverD": _num(kpis.get("LOverD")),
        "frontPct": _num(bal.get("frontPct")),
        "copXM": _num(bal.get("copXM")),
        "downforceN": newtons(_num(kpis.get("downforceCoeff"))),
        "dragN": newtons(_num(kpis.get("Cd"))),
    }


HEADLINE_ROWS = (
    ("Cd", "Opór Cd", 3),
    ("downforce", "Docisk (współczynnik)", 3),
    ("LOverD", "Docisk / opór", 2),
    ("frontPct", "Balans: przód [%]", 1),
    ("copXM", "Środek parcia od osi przedniej [m]", 3),
    ("downforceN", "Docisk całego auta [N]", 0),
    ("dragN", "Opór całego auta [N]", 0),
)


def group_table(cases: list[dict]) -> dict[str, list[dict | None]]:
    """group -> one record per case (Cd, downforce, shares) or None."""
    names: list[str] = []
    for c in cases:
        for g in (_get(c["pack"], "kpis", "components", "groups") or {}):
            if g not in names:
                names.append(g)
    out = {}
    for g in names:
        out[g] = [((_get(c["pack"], "kpis", "components", "groups") or {}).get(g)) for c in cases]
    return out


def series_strips(cases: list[dict], group: str | None = None) -> dict[str, list[tuple[float, float]]]:
    """Downforce along x per strip, for one group or for all groups together."""
    out = {}
    for c in cases:
        strips = _get(c["report"], "walls", "strips") or {}
        acc: dict[float, float] = {}
        for name, rows in strips.items():
            if group is not None and name != group:
                continue
            for r in rows:
                acc[r["x_m"]] = acc.get(r["x_m"], 0.0) + r["downforceCoeff"]
        if acc:
            out[c["name"]] = sorted(acc.items())
    return out


def series_loss(cases: list[dict]) -> dict[str, list[tuple[float, float]]]:
    out = {}
    for c in cases:
        stations = _get(c["report"], "flow", "stations") or []
        pts = [(s["x_m"], s["lossIntegralM2"]) for s in stations if s.get("lossIntegralM2") is not None]
        if pts:
            out[c["name"]] = pts
    return out


def check_matrix(cases: list[dict]) -> tuple[list[str], list[list[str]]]:
    titles: list[str] = []
    for c in cases:
        for ch in c["report"].get("checks") or []:
            if ch["title"] not in titles:
                titles.append(ch["title"])
    rows = []
    for title in titles:
        row = []
        for c in cases:
            found = next((ch for ch in c["report"].get("checks") or [] if ch["title"] == title), None)
            row.append("" if not found else LIGHT[found["status"]])
        rows.append(row)
    return titles, rows


# ---------------------------------------------------------------------------- SVG

def _nice(lo: float, hi: float) -> tuple[float, float]:
    if hi - lo < 1e-12:
        return lo - 0.5, hi + 0.5
    pad = 0.05 * (hi - lo)
    return lo - pad, hi + pad


def line_chart(series: dict[str, list[tuple[float, float]]], title: str, xlabel: str, ylabel: str, width: int = 860, height: int = 300) -> str:
    left, right, top, bottom = 62, 150, 34, 44
    xs = [p[0] for pts in series.values() for p in pts]
    ys = [p[1] for pts in series.values() for p in pts]
    x0, x1 = _nice(min(xs), max(xs))
    y0, y1 = _nice(min(ys + [0.0]), max(ys + [0.0]))
    pw, ph = width - left - right, height - top - bottom

    def px(x):
        return left + (x - x0) / (x1 - x0) * pw

    def py(y):
        return top + (1 - (y - y0) / (y1 - y0)) * ph

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}" style="max-width:100%;background:transparent;font-family:system-ui,sans-serif">']
    parts.append(f'<text x="{left}" y="20" font-size="14" font-weight="600" fill="currentColor">{html.escape(title)}</text>')
    for i in range(6):
        gy = y0 + (y1 - y0) * i / 5
        parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{py(gy):.1f}" y2="{py(gy):.1f}" stroke="currentColor" stroke-opacity="0.15"/>')
        parts.append(f'<text x="{left - 6}" y="{py(gy) + 4:.1f}" font-size="11" text-anchor="end" fill="currentColor">{gy:.2f}</text>')
        gx = x0 + (x1 - x0) * i / 5
        parts.append(f'<text x="{px(gx):.1f}" y="{top + ph + 16}" font-size="11" text-anchor="middle" fill="currentColor">{gx:.1f}</text>')
    if y0 < 0 < y1:
        parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{py(0):.1f}" y2="{py(0):.1f}" stroke="currentColor" stroke-opacity="0.5"/>')
    parts.append(f'<text x="{left + pw / 2}" y="{height - 6}" font-size="12" text-anchor="middle" fill="currentColor">{html.escape(xlabel)}</text>')
    parts.append(f'<text x="14" y="{top + ph / 2}" font-size="12" text-anchor="middle" fill="currentColor" transform="rotate(-90 14 {top + ph / 2})">{html.escape(ylabel)}</text>')
    for i, (name, pts) in enumerate(series.items()):
        color = PALETTE[i % len(PALETTE)]
        path = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in pts)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{path}"/>')
        ly = top + 8 + 18 * i
        parts.append(f'<line x1="{left + pw + 12}" x2="{left + pw + 34}" y1="{ly}" y2="{ly}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{left + pw + 40}" y="{ly + 4}" font-size="12" fill="currentColor">{html.escape(name)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def bar_chart(categories: list[str], series: dict[str, list[float | None]], title: str, ylabel: str, width: int = 860, height: int = 320) -> str:
    left, right, top, bottom = 62, 150, 34, 56
    values = [v for vals in series.values() for v in vals if v is not None]
    y0, y1 = _nice(min(values + [0.0]), max(values + [0.0]))
    pw, ph = width - left - right, height - top - bottom

    def py(y):
        return top + (1 - (y - y0) / (y1 - y0)) * ph

    group_w = pw / max(len(categories), 1)
    bar_w = group_w * 0.8 / max(len(series), 1)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}" style="max-width:100%;font-family:system-ui,sans-serif">']
    parts.append(f'<text x="{left}" y="20" font-size="14" font-weight="600" fill="currentColor">{html.escape(title)}</text>')
    for i in range(6):
        gy = y0 + (y1 - y0) * i / 5
        parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{py(gy):.1f}" y2="{py(gy):.1f}" stroke="currentColor" stroke-opacity="0.15"/>')
        parts.append(f'<text x="{left - 6}" y="{py(gy) + 4:.1f}" font-size="11" text-anchor="end" fill="currentColor">{gy:.2f}</text>')
    parts.append(f'<line x1="{left}" x2="{left + pw}" y1="{py(0):.1f}" y2="{py(0):.1f}" stroke="currentColor" stroke-opacity="0.6"/>')
    parts.append(f'<text x="14" y="{top + ph / 2}" font-size="12" text-anchor="middle" fill="currentColor" transform="rotate(-90 14 {top + ph / 2})">{html.escape(ylabel)}</text>')
    for ci, cat in enumerate(categories):
        gx = left + ci * group_w + group_w * 0.1
        for si, (name, vals) in enumerate(series.items()):
            v = vals[ci]
            if v is None:
                continue
            x = gx + si * bar_w
            top_y, base_y = sorted((py(v), py(0)))
            parts.append(f'<rect x="{x:.1f}" y="{top_y:.1f}" width="{bar_w - 2:.1f}" height="{max(base_y - top_y, 0.5):.1f}" fill="{PALETTE[si % len(PALETTE)]}"/>')
        parts.append(f'<text x="{left + ci * group_w + group_w / 2:.1f}" y="{top + ph + 16}" font-size="11" text-anchor="middle" fill="currentColor">{html.escape(cat)}</text>')
    for si, name in enumerate(series):
        ly = top + 8 + 18 * si
        parts.append(f'<rect x="{left + pw + 12}" y="{ly - 7}" width="14" height="12" fill="{PALETTE[si % len(PALETTE)]}"/>')
        parts.append(f'<text x="{left + pw + 32}" y="{ly + 4}" font-size="12" fill="currentColor">{html.escape(name)}</text>')
    parts.append("</svg>")
    return "".join(parts)


# ----------------------------------------------------------------------- document

def _fmtv(value, digits):
    return "brak" if value is None else f"{value:.{digits}f}"


def _fmtd(diff, pct, digits):
    if diff is None:
        return "brak"
    text = f"{diff:+.{digits}f}"
    return text if pct is None else f"{text} ({pct:+.0f}%)"


def reading(cases: list[dict], issues: list[str]) -> list[str]:
    """What changed, in words. The first case is the baseline."""
    base, others = cases[0], cases[1:]
    out = []
    groups = group_table(cases)
    for k, case in enumerate(others, 1):
        changes = []
        for g, recs in groups.items():
            b, n = recs[0], recs[k]
            if not b or not n:
                continue
            d, pct = _delta(n.get("downforceCoeff"), b.get("downforceCoeff"))
            dc, _ = _delta(n.get("Cd"), b.get("Cd"))
            if d is not None:
                changes.append((abs(d), g, d, pct, dc))
        changes.sort(reverse=True)
        h0, h1 = headline(base), headline(case)
        dd, dp = _delta(h1["downforce"], h0["downforce"])
        dcd, dcp = _delta(h1["Cd"], h0["Cd"])
        line = f"**{case['name']}** względem {base['name']}: docisk {_fmtd(dd, dp, 2)}, opór {_fmtd(dcd, dcp, 2)}."
        if changes:
            top = changes[:3]
            line += " Największe zmiany docisku: " + "; ".join(f"{PART_NAMES.get(g, g)} {d:+.2f}" + ("" if pct is None else f" ({pct:+.0f}%)") for _, g, d, pct, _ in top) + "."
        bal = _delta(h1["frontPct"], h0["frontPct"])[0]
        if bal is not None:
            line += f" Balans przesunął się o {bal:+.1f} pkt w stronę {'przodu' if bal > 0 else 'tyłu'}."
        out.append(line)
    if issues:
        out.append("**Uwaga:** te symulacje różnią się czymś poza geometrią (patrz niżej), więc część zmian może wynikać z metody, a nie z bolidu.")
    return out


def build_document(cases: list[dict]) -> tuple[str, list[tuple[str, str]], dict]:
    """Markdown text, charts as (caption, svg) pairs, and the raw result."""
    names = [c["name"] for c in cases]
    packs = [c["pack"] for c in cases]
    issues = differences(packs)
    lines = ["# Porównanie symulacji", "", "Pierwsza symulacja jest punktem odniesienia. Wszystkie różnice są liczone względem niej.", ""]
    lines += ["## Co to za symulacje", "", "| | " + " | ".join(names) + " |", "| --- |" + " --- |" * len(names)]
    info = (
        ("Model turbulencji", lambda p: _get(p, "methods", "turbulence")),
        ("Ściana", lambda p: _get(p, "methods", "wallTreatment")),
        ("Komórek", lambda p: None if not _get(p, "mesh", "cells") else f"{_get(p, 'mesh', 'cells'):,}".replace(",", " ")),
        ("Iteracje", lambda p: _get(p, "kpis", "iterations")),
        ("Prędkość [m/s]", lambda p: _get(p, "kpis", "references", "speedMs", "value")),
        ("Powierzchnia odniesienia [m²]", lambda p: None if _get(p, "kpis", "references", "frontalAreaM2", "value") is None else round(_get(p, "kpis", "references", "frontalAreaM2", "value"), 4)),
    )
    for label, get in info:
        lines.append(f"| {label} | " + " | ".join(str(get(p) if get(p) is not None else "brak") for p in packs) + " |")
    verdicts = []
    for c in cases:
        v = c["report"].get("verdict")
        verdicts.append(f"{LIGHT[v['status']]}" if v else "brak raportu")
    lines.append("| Werdykt | " + " | ".join(verdicts) + " |")
    lines.append("")
    if issues:
        lines += ["## Czy to uczciwe porównanie?", "", "Nie do końca. Poza geometrią różni się:", ""] + [f"- {i}" for i in issues] + [""]
    else:
        lines += ["## Czy to uczciwe porównanie?", "", "Tak: ten sam model, ściana, prędkość i powierzchnia odniesienia.", ""]
    for sentence in reading(cases, issues):
        lines += [f"- {sentence}"]
    lines.append("")

    heads = [headline(c) for c in cases]
    lines += ["## Najważniejsze liczby", ""]
    header = "| | " + " | ".join(names[:1] + [f"{n}" for n in names[1:]]) + " |"
    lines += [header, "| --- |" + " --- |" * len(names)]
    for key, label, digits in HEADLINE_ROWS:
        cells = [_fmtv(heads[0][key], digits)]
        for h in heads[1:]:
            d, p = _delta(h[key], heads[0][key])
            cells.append(f"{_fmtv(h[key], digits)} ({_fmtd(d, p, digits)})")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")

    groups = group_table(cases)
    charts: list[tuple[str, str]] = []
    if groups:
        lines += ["## Siły na części", "", "Docisk (współczynnik) i opór Cd każdej części. W nawiasie zmiana względem punktu odniesienia.", ""]
        lines += ["| Część | " + " | ".join(f"Docisk: {n}" for n in names) + " | " + " | ".join(f"Cd: {n}" for n in names) + " |", "| --- |" + " --- |" * (2 * len(names))]
        for g, recs in groups.items():
            row = [PART_NAMES.get(g, g)]
            for key in ("downforceCoeff", "Cd"):
                base_v = (recs[0] or {}).get(key)
                for k, rec in enumerate(recs):
                    v = (rec or {}).get(key)
                    if k == 0:
                        row.append(_fmtv(v, 3))
                    else:
                        d, p = _delta(v, base_v)
                        row.append(f"{_fmtv(v, 3)} ({_fmtd(d, p, 2)})")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
        cats = [PART_NAMES.get(g, g) for g in groups]
        charts.append(("Docisk każdej części", bar_chart(cats, {n: [((recs[i] or {}).get("downforceCoeff")) for recs in groups.values()] for i, n in enumerate(names)}, "Docisk każdej części (współczynnik)", "docisk")))
        charts.append(("Opór każdej części", bar_chart(cats, {n: [((recs[i] or {}).get("Cd")) for recs in groups.values()] for i, n in enumerate(names)}, "Opór każdej części (Cd)", "Cd")))
    along = series_strips(cases)
    if along:
        lines += ["## Gdzie wzdłuż auta powstaje docisk", "", "Wykresy w pliku HTML. Pasy po 10 cm, x rośnie do tyłu.", ""]
        charts.append(("Docisk wzdłuż auta, całe auto", line_chart(along, "Docisk w pasach po 10 cm, całe auto", "x [m]", "wkład do współczynnika docisku")))
        for g in ("fw", "floor", "rw"):
            per = series_strips(cases, g)
            if per:
                charts.append((f"Docisk wzdłuż auta: {PART_NAMES[g]}", line_chart(per, f"Docisk wzdłuż auta: {PART_NAMES[g]}", "x [m]", "wkład do współczynnika")))
    loss = series_loss(cases)
    if loss:
        lines += ["## Gdzie powietrze traci energię", "", "Strata ciśnienia całkowitego w przekrojach w poprzek auta (m²). Im szybciej rośnie, tym więcej energii oddaje powietrze w tym miejscu.", ""]
        charts.append(("Strata ciśnienia całkowitego wzdłuż auta", line_chart(loss, "Strata ciśnienia całkowitego w przekrojach", "x [m]", "strata [m²]")))
        rows = []
        for c in cases:
            summary = _get(c["pack"], "flowSummary") or {}
            tracks = (summary.get("vortexTracks") or [])[:3]
            rows.append("; ".join(f"{t.get('region', '')} ({abs(t['peakCirculationM2s']):.1f} m²/s, x {t['fromX_m']}→{t['toX_m']})" for t in tracks) or "brak")
        lines += ["Najsilniejsze wiry:", ""] + [f"- **{n}**: {r}" for n, r in zip(names, rows)] + [""]
    titles, matrix = check_matrix(cases)
    if titles:
        lines += ["## Wiarygodność każdej symulacji", "", "| Sprawdzenie | " + " | ".join(names) + " |", "| --- |" + " --- |" * len(names)]
        lines += [f"| {t} | " + " | ".join(row) + " |" for t, row in zip(titles, matrix)] + [""]
    raw = {"names": names, "issues": issues, "headline": dict(zip(names, heads)), "groups": {g: dict(zip(names, recs)) for g, recs in groups.items()}}
    return "\n".join(lines), charts, raw


def compare(folders: list[Path], out_dir: Path, labels: list[str] | None = None) -> dict:
    if len(folders) < 2:
        raise ValueError("do porównania potrzeba co najmniej dwóch symulacji")
    cases = [load_case(f, (labels or [None] * len(folders))[i]) for i, f in enumerate(folders)]
    text, charts, raw = build_document(cases)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "POROWNANIE.md").write_text(text, encoding="utf-8")
    page = markdown_to_html(text, "Porównanie symulacji")
    figures = "".join(f"<figure style='margin:18px 0'>{svg}<figcaption style='font-size:12px;opacity:.7'>{html.escape(cap)}</figcaption></figure>" for cap, svg in charts)
    page = page.replace("</body>", f"<h2>Wykresy</h2>{figures}</body>")
    (out_dir / "POROWNANIE.html").write_text(page, encoding="utf-8")
    (out_dir / "porownanie.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"out": str(out_dir), "names": raw["names"], "issues": raw["issues"], "charts": len(charts)}
