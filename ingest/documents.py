"""The two documents of a case: a one-page summary and the one with absolutely everything.

`SKROT.md` is for a quick read: verdict, the numbers that matter, what to watch, what the car does
and what is missing. `PELNY.md` is the report plus appendices with every table behind those
numbers (all wall zones, forces along the car, every flow station and vortex, residuals, the whole
setup, the method). Both also come out as self-contained HTML, so they open in any browser.
"""

from __future__ import annotations

import html
import re

from ingest.report import (
    BAD,
    LIGHT,
    NONE,
    OK,
    PART_NAMES,
    SURFACE_GROUPS,
    WARN,
    _fmt,
    _get,
    _pct,
    references,
    render_markdown,
)

GLOSSARY = [
    ("Cd", "współczynnik oporu. Im mniejszy, tym mniejszy opór. Liczony na połowę auta, tak jak w solverze."),
    ("Docisk (współczynnik)", "siła w dół podzielona przez ciśnienie dynamiczne i powierzchnię odniesienia. Dodatni to docisk."),
    ("Cl", "ten sam współczynnik ze znakiem fizycznym: ujemny to docisk (oś Z do góry)."),
    ("Balans przód/tył", "jak docisk dzieli się między osie, liczony z momentu solvera."),
    ("Środek parcia", "punkt, w którym działa wypadkowa siła aerodynamiczna, mierzony od osi przedniej."),
    ("Residua", "miara tego, jak dobrze solver zbiegł. Mniejsze znaczy lepiej. Limit Fluenta to 1e-3."),
    ("y+", "jak blisko ściany leży pierwsza komórka siatki. Model SST bez funkcji ściany wymaga y+ poniżej ok. 5."),
    ("Cp", "współczynnik ciśnienia. Ujemny to podciśnienie (ssanie)."),
    ("Cpt", "ciśnienie całkowite podzielone przez dynamiczne. 1 to czyste powietrze, mniej to powietrze, które straciło energię."),
    ("Oderwanie", "miejsce, gdzie przepływ tuż przy ścianie płynie do przodu auta. Powierzchnia przestaje prowadzić powietrze."),
    ("Cyrkulacja wiru", "siła wiru w m²/s. Większa to silniejszy wir."),
    ("GCI", "niepewność wyniku wynikająca z gęstości siatki, w procentach."),
]


# --------------------------------------------------------------------- findings

def _findings(report: dict) -> list[str]:
    """A few plain sentences about what the car does, from the numbers."""
    walls = report.get("walls") or {}
    flow = report.get("flow") or {}
    out = []
    groups = walls.get("groups") or {}
    if groups:
        top_down = max(groups.items(), key=lambda kv: kv[1].get("shareDownforcePct") or -1e9)
        top_drag = max(groups.items(), key=lambda kv: kv[1].get("shareDragPct") or -1e9)
        neg = [(n, g) for n, g in groups.items() if (g.get("downforceCoeff") or 0) < 0]
        out.append(
            f"Najwięcej docisku daje {PART_NAMES.get(top_down[0], top_down[0])} ({_pct(top_down[1].get('shareDownforcePct'), 0)}), "
            f"najwięcej oporu {PART_NAMES.get(top_drag[0], top_drag[0])} ({_pct(top_drag[1].get('shareDragPct'), 0)})."
        )
        if neg:
            names = ", ".join(PART_NAMES.get(n, n) for n, _ in neg)
            out.append(f"Zmniejszają docisk, bo dają siłę w górę: {names}.")
    summary = (report.get("pack") or {}).get("flowSummary") or {}
    growth = summary.get("lossGrowth") or []
    if growth:
        g = growth[0]
        by = f", opór w tym pasie robi głównie {g['dragMostlyFrom']}" if g.get("dragMostlyFrom") else ""
        out.append(f"Powietrze traci najwięcej energii między x = {g['fromX_m']:.1f} a {g['toX_m']:.1f} m{by}.")
    tracks = summary.get("vortexTracks") or flow.get("vortexTracks") or []
    if tracks:
        t = tracks[0]
        out.append(
            f"Najsilniejszy wir ({abs(t['peakCirculationM2s']):.1f} m²/s) powstaje w miejscu: {t.get('region', 'brak opisu')}, "
            f"i biegnie od x = {t['fromX_m']:.1f} do {t['toX_m']:.1f} m."
        )
    rev = (summary.get("reverseFlow") or None)
    if rev:
        out.append(f"Przepływ się odrywa i wraca do tyłu na x = {rev['fromX_m']:.1f} do {rev['toX_m']:.1f} m (najbardziej przy {rev['atX_m']:.1f} m).")
    hot = []
    for zname, rec in (walls.get("zones") or {}).items():
        if rec.get("group") in SURFACE_GROUPS:
            for strip in (rec.get("reverseFlow") or {}).get("strips", []):
                if strip["reversedShare"] > 0.3 and strip["areaM2"] > 0.002:
                    hot.append(f"{PART_NAMES[rec['group']]} (x = {strip['x_m']:.2f} m)")
    if hot:
        out.append("Oderwanie na powierzchni: " + ", ".join(hot[:4]) + ".")
    return out


# ------------------------------------------------------------------------ short

def render_short(report: dict) -> str:
    pack = report["pack"]
    ident = pack.get("identity") or {}
    kpis = pack.get("kpis") or {}
    bal = kpis.get("aeroBalance") or {}
    verdict = report["verdict"]
    refs = references(pack)
    mesh = pack.get("mesh") or {}
    lines = [
        f"# {ident.get('caseId', 'Symulacja')}: skrót",
        "",
        f"**Werdykt: {LIGHT[verdict['status']]}. {verdict['label']}.**",
        "",
    ]
    cred = report.get("credibility")
    if cred and cred.get("score") is not None:
        lines += [f"**Wiarygodność: {cred['label']}, {cred['score']} na 100** (pokrycie danymi {cred['coverage']}%). Szczegóły i źródła w `WIARYGODNOSC.md`.", ""]
    bad = [c for c in report["checks"] if c["status"] == BAD]
    warn = [c for c in report["checks"] if c["status"] == WARN]
    if bad or warn:
        lines += ["## Na co uważać", ""]
        for c in bad + warn:
            first = c["detail"].split(". ")[0].rstrip(".")
            lines.append(f"- {LIGHT[c['status']].split(' ')[0]} **{c['title']}**: {first}.")
        lines.append("")
    lines += ["## Najważniejsze liczby", "", "| | |", "| --- | --- |"]
    rows = [
        ("Opór Cd", _fmt(kpis.get("Cd"))),
        ("Docisk (współczynnik)", _fmt(kpis.get("downforceCoeff"))),
        ("Docisk / opór", _fmt(kpis.get("LOverD"), 2)),
        ("Balans przód / tył", f"{_fmt(bal.get('frontPct'), 1)}% / {_fmt(bal.get('rearPct'), 1)}%"),
        ("Środek parcia od osi przedniej", "brak" if bal.get("copXM") is None else f"{bal['copXM']:.2f} m"),
    ]
    if refs:
        q = 0.5 * refs["rho"] * refs["speed_ms"] ** 2
        full = 2.0 if ident.get("halfModel") else 1.0
        if kpis.get("downforceCoeff") is not None:
            rows.append((f"Docisk całego auta przy {refs['speed_ms']:g} m/s", f"{full * kpis['downforceCoeff'] * q * refs['aref_m2']:.0f} N"))
        if kpis.get("Cd") is not None:
            rows.append((f"Opór całego auta przy {refs['speed_ms']:g} m/s", f"{full * kpis['Cd'] * q * refs['aref_m2']:.0f} N"))
    rows += [
        ("Model turbulencji", _get(pack, "methods", "turbulence") or "brak"),
        ("Komórek siatki", "brak" if not mesh.get("cells") else f"{mesh['cells']:,}".replace(",", " ")),
        ("Iteracje", _get(pack, "kpis", "iterations") or "brak"),
    ]
    lines += [f"| {a} | {b} |" for a, b in rows] + [""]
    parts = (report.get("walls") or {}).get("groups") or {}
    if parts:
        lines += ["## Skąd się biorą siły", "", "| Część | Udział docisku | Udział oporu |", "| --- | --- | --- |"]
        for name, g in parts.items():
            lines.append(f"| {PART_NAMES.get(name, name)} | {_pct(g.get('shareDownforcePct'), 0)} | {_pct(g.get('shareDragPct'), 0)} |")
        lines.append("")
    found = _findings(report)
    if found:
        lines += ["## Co robi bolid", ""] + [f"- {f}" for f in found] + [""]
    if report["missing"]:
        lines += ["## Czego brakuje", ""] + [f"- 🔴 {m}" for m in report["missing"]] + [""]
    lines += [
        "## Więcej",
        "",
        "- `PELNY.md`: absolutnie wszystko (każda tabela, każda strefa, każdy przekrój, ustawienia, metoda).",
        "- `obrazy/galeria.html`: przekroje przepływu z suwakiem, w tych samych płaszczyznach co CFD-Post.",
        "- `dla-chatbota.md`: skrót do wklejenia w czat.",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------------- full

def _table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return out + [""]


def _appendix_zones(walls: dict) -> list[str]:
    rows = []
    for name, z in walls["zones"].items():
        y = z.get("yplus") or {}
        rf = z.get("reverseFlow") or {}
        fc = z.get("firstCellHeightM") or {}
        rows.append(
            [
                name,
                PART_NAMES.get(z.get("group"), "poza autem" if z.get("group") is None else z.get("group")),
                z["faces"],
                f"{z['areaM2']:.3f}",
                f"{z['Cd']:.4f}",
                f"{z['downforceCoeff']:.4f}",
                f"{z['Cd_pressure']:.4f}",
                f"{z['Cd_viscous']:.4f}",
                y.get("median"),
                y.get("p95"),
                y.get("max"),
                None if not fc else f"{1e6 * fc['median']:.0f}",
                _pct(None if rf.get("areaShare") is None else 100 * rf["areaShare"]),
            ]
        )
    return ["## Dodatek A. Wszystkie strefy ścian", "", "Każda ściana siatki, także tunel (domain_*), który nie wchodzi do sumy auta."] + [""] + _table(
        ["Strefa", "Część", "Ścianek", "Pole m²", "Cd", "Docisk", "Cd z ciśnienia", "Cd z tarcia", "y+ med.", "y+ p95", "y+ max", "1. komórka µm", "Oderwane"], rows
    )


def _appendix_strips(walls: dict) -> list[str]:
    strips = walls.get("strips") or {}
    if not strips:
        return []
    xs = sorted({r["x_m"] for rows in strips.values() for r in rows})
    names = list(strips)
    index = {n: {r["x_m"]: r for r in rows} for n, rows in strips.items()}
    headers = ["x [m]"] + [f"{PART_NAMES.get(n, n)}: Cd | docisk" for n in names]
    rows = []
    for x in xs:
        row = [f"{x:.2f}"]
        for n in names:
            r = index[n].get(x)
            row.append("" if not r else f"{r['Cd']:.4f} | {r['downforceCoeff']:.4f}")
        rows.append(row)
    return ["## Dodatek B. Siły wzdłuż auta (pasy po 10 cm)", "", "x rośnie do tyłu. Wartości to wkład pasa do współczynnika danej części."] + [""] + _table(headers, rows)


def _appendix_flow(flow: dict | None) -> list[str]:
    if not flow:
        return ["## Dodatek C. Przekroje przepływu", "", "Nie policzono.", ""]
    rows = []
    for s in flow["stations"]:
        w = s.get("wheels") or {}
        rows.append(
            [
                f"{s['x_m']:.2f}",
                s.get("cells"),
                s.get("lossIntegralM2"),
                s.get("lossAreaM2"),
                s.get("minCpt"),
                s.get("reverseFlowAreaM2"),
                s.get("minU_ms"),
                None if "front" not in w else w["front"]["lossIntegralM2"],
                None if "rear" not in w else w["rear"]["lossIntegralM2"],
                len(s.get("vortices") or []),
            ]
        )
    out = ["## Dodatek C. Przekroje przepływu", "", "Jeden wiersz to jedna płaszczyzna w poprzek auta."] + [""]
    out += _table(["x [m]", "Komórek", "Strata m²", "Pole straty m²", "Min Cpt", "Cofnięty m²", "Min u m/s", "Okno koła przód", "Okno koła tył", "Wirów"], rows)
    vortices = []
    for s in flow["stations"]:
        for v in s.get("vortices") or []:
            vortices.append([f"{s['x_m']:.2f}", v["y_m"], v["z_m"], v["circulationM2s"], v["turn"].split(" (")[0], v["coreRadiusM"], v["swirlSpeedMs"], v.get("minCpt"), v.get("region", "")])
    out += ["### Każdy znaleziony wir", ""] + _table(["x [m]", "y [m]", "z [m]", "Cyrkulacja m²/s", "Obrót", "Promień rdzenia m", "Prędkość obrotu m/s", "Min Cpt", "Gdzie"], vortices)
    tracks = flow.get("vortexTracks") or []
    out += ["### Ślady wirów (ten sam wir od przekroju do przekroju)", ""]
    for i, t in enumerate(tracks, 1):
        out.append(f"**Ślad {i}**: {t['turn']}, x od {t['fromX_m']} do {t['toX_m']}, najsilniejszy przy {t['strongestAtX_m']} m ({t['peakCirculationM2s']} m²/s), {t.get('region', '')}.")
        out.append("")
        out += _table(["x", "y", "z", "Cyrkulacja"], [[p["x_m"], p["y_m"], p["z_m"], p["circulationM2s"]] for p in t["points"]])
    return out


def _appendix_conservation(cons: dict) -> list[str]:
    out = ["## Dodatek D. Residua i bilans masy", ""]
    res = cons.get("residuals")
    if res:
        rows = [[n, f"{r['final']:.3e}", r["belowLimit"], r["ordersDropped"], r["trend"]["verdict"], r["trend"]["log10Per100"]] for n, r in res["equations"].items()]
        out += _table(["Równanie", "Wartość końcowa", "Poniżej limitu", "Spadek (rzędy)", "Trend", "Nachylenie log10 / 100 iteracji"], rows)
    mb = cons.get("massBalance")
    if mb:
        out += [f"Wlot {mb['inflowKgS']:.5f} kg/s, wylot {mb['outflowKgS']:.5f} kg/s, różnica {mb['relativeImbalance']:.2e}. Chłodnica {_fmt(mb.get('radiatorKgS'), 4)} kg/s, wentylator {_fmt(mb.get('fanKgS'), 4)} kg/s.", ""]
        out += _table(["Brzeg", "Strumień masy kg/s"], [[z["name"], f"{z['fluxKgS']:.5f}"] for z in mb["zones"]])
    return out


def _appendix_setup(pack: dict) -> list[str]:
    out = ["## Dodatek E. Całe ustawienie", ""]
    refs = _get(pack, "kpis", "references") or {}
    out += _table(["Wartość odniesienia", "Wartość", "Skąd"], [[k, v.get("value"), v.get("source")] for k, v in refs.items()])
    wheels = _get(pack, "methods", "wheelRotation") or {}
    if wheels:
        out += ["Obrót kół:", ""] + _table(["Koło", "Strefa", "Środek [m]", "Oś", "Prędkość kątowa rad/s"], [[n, w.get("zone"), w.get("originM"), w.get("axis"), w.get("omegaRadS")] for n, w in wheels.items()])
    sessions = _get(pack, "methods", "solverSessions") or []
    if sessions:
        out += ["Sesje solvera (z logów):", ""] + _table(
            ["Plik", "Ostatnia iteracja", "Planowane", "Awaria", "Powód", "Odrzucone komendy"],
            [[s.get("file"), s.get("lastIteration"), s.get("plannedIterations"), s.get("crashed"), ", ".join(s.get("crashReasons") or []), s.get("scriptErrorCount")] for s in sessions],
        )
    trace = _get(pack, "methods", "setupTrace")
    if trace:
        out += [f"Ślad ustawień z logu: {len(trace) if hasattr(trace, '__len__') else 'jest'} wpisów (w `aeropack.json`, pole `methods.setupTrace`).", ""]
    mesh = pack.get("mesh") or {}
    out += _table(
        ["Siatka", "Wartość"],
        [
            ["Komórek", mesh.get("cells")],
            ["Najgorsza jakość ortogonalna (log)", mesh.get("minOrthogonalQuality")],
            ["Największe wydłużenie", mesh.get("maxAspectRatio")],
            ["Ścianek symetrii", mesh.get("symmetryFaces")],
            ["Ścianek wlotu", mesh.get("inletFaces")],
        ],
    )
    layers = (mesh.get("boundaryLayers") or {}).get("boundaryLayers") or []
    if layers:
        out += _table(["Przepis na warstwy", "Warstw", "Pierwsza komórka m", "Stan", "Strefy"], [[b.get("name"), b.get("layers"), b.get("firstHeightM"), b.get("state"), ", ".join(b.get("zones") or [])] for b in layers])
    return out


def _appendix_geometry(pack: dict) -> list[str]:
    geom = pack.get("geometry") or {}
    devices = geom.get("devices") or geom.get("cards") or []
    out = ["## Dodatek F. Geometria i zdjęcia", ""]
    if devices:
        out += [f"Karty geometrii: {len(devices)} (szczegóły w `geometry.yaml`).", ""]
    images = pack.get("images") or {}
    out += [f"Zdjęcia z CFD-Post: {images.get('total', 0)}. Osie: {images.get('byAxis')}.", ""]
    return out


def _appendix_credibility(cred: dict | None) -> list[str]:
    if not cred:
        return []
    from ingest.credibility import LIGHT as CRED_LIGHT

    out = ["## Dodatek I. Wiarygodność względem literatury", "", f"**{cred['label']}: {cred['score']} na 100**, pokrycie danymi {cred['coverage']}%. Pełne źródła w `WIARYGODNOSC.md`.", ""]
    out += _table(["Sprawdzenie", "Waga", "Ocena", "Wartość", "Co to znaczy"], [[c["title"], c["weight"], CRED_LIGHT[c["status"]], c["value"], c["detail"]] for c in cred["checks"]])
    return out


def _appendix_method() -> list[str]:
    return [
        "## Dodatek G. Jak to jest policzone",
        "",
        "- **Siły na części**: ciśnienie z każdej ścianki razy jej pole (wektor), plus tarcie odtworzone z y+ i odległości pierwszej komórki, tau = mu² y+² / (rho y²). Zapisane w pliku tarcie (`SV_WALL_SHEAR`) ma odwrócony znak i złe jednostki, więc nie jest używane.",
        "- **Zgodność z solverem**: suma sił porównana z monitorami Cd i Cl. Pliki wyników to stan z ostatniej iteracji, monitory to średnia, więc przy niedokończonym liczeniu różnica rzędu 1% jest normalna.",
        "- **Stabilność sił**: z plików `.out` (dryf w ostatnich 200 iteracjach). Bez nich z różnicy między wartością chwilową a średnią z `.dat.h5`, co jest przybliżeniem.",
        "- **Residua**: historia z `.dat.h5`, wartość znormalizowana tak jak w logu Fluenta.",
        "- **Bilans masy**: suma strumienia masy po brzegach domeny (`SV_FLUX`).",
        "- **Przekroje**: komórki solvera w pasie przy płaszczyźnie, uśrednione w kafelkach 2 cm. Środki komórek odtworzone ze środków ścianek.",
        "- **Wiry**: siła wirowania w płaszczyźnie przekroju (część urojona wartości własnych gradientu prędkości). W czystym ścinaniu przy ścianie jest zerowa, więc warstwy przyścienne nie są wirami.",
        "- **Oderwanie**: kierunek prędkości w pierwszej komórce przy ścianie wskazuje do przodu auta, na powierzchniach prawie poziomych.",
        "- **Jakość siatki bez logu**: przybliżenie z geometrii, przesadza w skrajnie spłaszczonych komórkach.",
        "",
        "Czego to nie mówi: czy symulacja zgadza się z rzeczywistością. Do tego trzeba pomiaru z tunelu lub toru.",
        "",
    ]


def _glossary() -> list[str]:
    return ["## Dodatek H. Słowniczek", ""] + [f"- **{k}**: {v}" for k, v in GLOSSARY] + [""]


def render_full(report: dict) -> str:
    base = render_markdown(report)
    parts = [base.rstrip(), ""]
    walls = report.get("walls")
    if walls:
        parts += _appendix_zones(walls) + _appendix_strips(walls)
    parts += _appendix_flow(report.get("flow"))
    parts += _appendix_conservation(report.get("conservation") or {})
    parts += _appendix_setup(report["pack"])
    parts += _appendix_geometry(report["pack"])
    parts += _appendix_credibility(report.get("credibility"))
    parts += _appendix_method()
    parts += _glossary()
    return "\n".join(parts).rstrip() + "\n"


# ------------------------------------------------------------------------- html

CSS = """
body{font-family:system-ui,Segoe UI,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#1c1c1c;line-height:1.5;background:#fafaf8}
h1{font-size:26px}h2{margin-top:32px;border-bottom:1px solid #ddd;padding-bottom:4px}h3{margin-top:22px}
table{border-collapse:collapse;margin:10px 0;font-size:13px;display:block;overflow-x:auto}
th,td{border:1px solid #d8d8d4;padding:4px 8px;text-align:left;vertical-align:top}th{background:#efefea}
code{background:#eee;padding:1px 4px;border-radius:3px}li{margin:3px 0}
@media (prefers-color-scheme: dark){body{background:#161616;color:#e6e6e6}th{background:#262626}th,td{border-color:#3a3a3a}code{background:#2a2a2a}h2{border-color:#3a3a3a}}
"""


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def markdown_to_html(text: str, title: str) -> str:
    """Just enough markdown for these documents: headings, tables, bullets, bold and code."""
    out, lines, i = [], text.split("\n"), 0
    in_list = False
    while i < len(lines):
        line = lines[i]
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-|]+\|$", lines[i + 1]):
            if in_list:
                out.append("</ul>")
                in_list = False
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(line[2:])}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            m = re.match(r"^(#{1,3}) (.*)", line)
            if m:
                level = len(m.group(1))
                out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            elif line.strip():
                out.append(f"<p>{_inline(line)}</p>")
        i += 1
    if in_list:
        out.append("</ul>")
    return f'<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{CSS}</style></head><body>' + "\n".join(out) + "</body></html>"
