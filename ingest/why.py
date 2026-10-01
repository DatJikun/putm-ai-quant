"""Why did it change? Two meta packs in, a ranked explanation out, with the numbers behind each sentence.

The difference is taken apart in layers, each of which adds up to the one above:

1. the total (drag, downforce, balance, centre of pressure);
2. the parts of the car: how much of the change each one accounts for (this is a decomposition, so
   "mostly because of the floor" is a statement of fact, not a guess);
3. the places along the car where a part changed most (strips of 10 cm);
4. the centre of pressure, shifted part by part;
5. what changed in the geometry (from the outline of every wall zone);
6. what changed in the flow around it: losses, vortices, separation, y+. These sit next to the
   change and are offered as evidence, not as proven causes.

Last comes how far to trust it: a different turbulence model or an unfinished run makes the
difference partly a difference of method, and the answer says so.
"""

from __future__ import annotations

from ingest.mesh_study import differences
from ingest.report import PART_NAMES

GEOMETRY_STEP_M = 0.01
MIN_STRIP_SHARE = 0.05


def _get(data, *path):
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _delta(new, old):
    if _num(new) is None or _num(old) is None:
        return None
    d = new - old
    return {"a": old, "b": new, "delta": d, "pct": None if abs(old) < 1e-12 else 100.0 * d / abs(old)}


def name_of(meta: dict) -> str:
    return meta.get("caseId") or _get(meta, "paczka", "identity", "caseId") or "?"


def part_name(group: str) -> str:
    return PART_NAMES.get(group, group)


# ------------------------------------------------------------------- layers

def totals(a: dict, b: dict) -> dict:
    ka, kb = _get(a, "paczka", "kpis") or {}, _get(b, "paczka", "kpis") or {}
    return {
        "Cd": _delta(kb.get("Cd"), ka.get("Cd")),
        "downforce": _delta(kb.get("downforceCoeff"), ka.get("downforceCoeff")),
        "LOverD": _delta(kb.get("LOverD"), ka.get("LOverD")),
        "frontPct": _delta(_get(kb, "aeroBalance", "frontPct"), _get(ka, "aeroBalance", "frontPct")),
        "copXM": _delta(_get(kb, "aeroBalance", "copXM"), _get(ka, "aeroBalance", "copXM")),
    }


def parts(a: dict, b: dict) -> list[dict]:
    """Each part's share of the change in downforce and drag. Shares add up to 100% of the total change."""
    ga, gb = _get(a, "raport", "walls", "groups") or {}, _get(b, "raport", "walls", "groups") or {}
    rows = []
    for g in [g for g in ga if g in gb]:
        rows.append(
            {
                "czesc": g,
                "nazwa": part_name(g),
                "df_a": ga[g]["downforceCoeff"],
                "df_b": gb[g]["downforceCoeff"],
                "d_df": gb[g]["downforceCoeff"] - ga[g]["downforceCoeff"],
                "cd_a": ga[g]["Cd"],
                "cd_b": gb[g]["Cd"],
                "d_cd": gb[g]["Cd"] - ga[g]["Cd"],
            }
        )
    total_df = sum(r["d_df"] for r in rows)
    total_cd = sum(r["d_cd"] for r in rows)
    for r in rows:
        r["udzial_df_pct"] = None if abs(total_df) < 1e-9 else 100.0 * r["d_df"] / total_df
        r["udzial_cd_pct"] = None if abs(total_cd) < 1e-9 else 100.0 * r["d_cd"] / total_cd
    rows.sort(key=lambda r: -abs(r["d_df"]))
    return rows


def _strips(meta: dict) -> dict[str, dict[float, dict]]:
    out = {}
    for g, rows in (_get(meta, "raport", "walls", "strips") or {}).items():
        out[g] = {r["x_m"]: r for r in rows}
    return out


def along_x(a: dict, b: dict, groups: list[str], top: int = 3) -> dict[str, list[dict]]:
    """Where along the car each of the given parts changed most (downforce, per 10 cm strip)."""
    sa, sb = _strips(a), _strips(b)
    out = {}
    for g in groups:
        xs = sorted(set(sa.get(g, {})) | set(sb.get(g, {})))
        rows = []
        for x in xs:
            da = (sa.get(g, {}).get(x) or {}).get("downforceCoeff", 0.0)
            db = (sb.get(g, {}).get(x) or {}).get("downforceCoeff", 0.0)
            rows.append({"x_m": x, "a": da, "b": db, "delta": db - da})
        rows.sort(key=lambda r: -abs(r["delta"]))
        out[g] = rows[:top]
    return out


def _centroid(meta: dict) -> dict | None:
    """Centre of the downforce along the car, whole and per part, from the strips."""
    strips = _get(meta, "raport", "walls", "strips") or {}
    weights, per = {}, {}
    for g, rows in strips.items():
        d = sum(r["downforceCoeff"] for r in rows)
        m = sum(r["x_m"] * r["downforceCoeff"] for r in rows)
        per[g] = (d, m)
    total = sum(d for d, _ in per.values())
    if abs(total) < 1e-9:
        return None
    return {"cop": sum(m for _, m in per.values()) / total, "total": total, "per": per}


def centre_of_pressure(a: dict, b: dict) -> dict | None:
    """The shift of the centre of pressure, split by part. Contributions add up to the shift exactly."""
    ca, cb = _centroid(a), _centroid(b)
    if not ca or not cb:
        return None
    groups = sorted(set(ca["per"]) | set(cb["per"]))
    rows = []
    for g in groups:
        da, ma = ca["per"].get(g, (0.0, 0.0))
        db, mb = cb["per"].get(g, (0.0, 0.0))
        rows.append({"czesc": g, "nazwa": part_name(g), "wklad_m": mb / cb["total"] - ma / ca["total"]})
    rows.sort(key=lambda r: -abs(r["wklad_m"]))
    return {"a": ca["cop"], "b": cb["cop"], "delta": cb["cop"] - ca["cop"], "wklady": rows, "uwaga": "z rozkładu docisku w pasach po 10 cm, może różnić się od środka parcia z momentu solvera"}


def geometry(a: dict, b: dict) -> list[dict]:
    """Outline of each part (from the wall zones) in both cases, where it moved by 1 cm or more."""
    def boxes(meta):
        out = {}
        for z in (_get(meta, "raport", "walls", "zones") or {}).values():
            if z.get("group") and z.get("bboxM"):
                lo, hi = z["bboxM"]
                cur = out.setdefault(z["group"], [list(lo), list(hi)])
                cur[0] = [min(p, q) for p, q in zip(cur[0], lo)]
                cur[1] = [max(p, q) for p, q in zip(cur[1], hi)]
        return out

    ba, bb = boxes(a), boxes(b)
    names = ("x od", "y od", "z od", "x do", "y do", "z do")
    rows = []
    for g in [g for g in ba if g in bb]:
        va, vb = ba[g][0] + ba[g][1], bb[g][0] + bb[g][1]
        for label, p, q in zip(names, va, vb):
            if abs(q - p) >= GEOMETRY_STEP_M:
                rows.append({"czesc": g, "nazwa": part_name(g), "wymiar": label, "a": p, "b": q, "delta": q - p})
    rows.sort(key=lambda r: -abs(r["delta"]))
    return rows


def flow(a: dict, b: dict) -> dict:
    """What changed in the flow next to the difference in forces. Evidence, not proof."""
    out: dict = {}
    fa, fb = _get(a, "raport", "flow", "stations") or [], _get(b, "raport", "flow", "stations") or []
    la = {s["x_m"]: s["lossIntegralM2"] for s in fa if s.get("lossIntegralM2") is not None}
    lb = {s["x_m"]: s["lossIntegralM2"] for s in fb if s.get("lossIntegralM2") is not None}
    xs = sorted(set(la) & set(lb))
    if len(xs) > 1:
        steps = [{"fromX_m": x0, "toX_m": x1, "a": la[x1] - la[x0], "b": lb[x1] - lb[x0], "delta": (lb[x1] - lb[x0]) - (la[x1] - la[x0])} for x0, x1 in zip(xs, xs[1:])]
        steps.sort(key=lambda s: -abs(s["delta"]))
        out["strata"] = {"za_autem": {"x_m": xs[-1], "a": la[xs[-1]], "b": lb[xs[-1]]}, "najwieksze_roznice_przyrostu": steps[:3]}
    ta = (_get(a, "paczka", "flowSummary", "vortexTracks") or [])[:4]
    tb = (_get(b, "paczka", "flowSummary", "vortexTracks") or [])[:4]
    matched, new, gone = [], [], []
    used = set()
    for t in tb:
        hit = next((i for i, u in enumerate(ta) if i not in used and u.get("region") == t.get("region") and abs(u["fromX_m"] - t["fromX_m"]) <= 0.3), None)
        if hit is None:
            new.append(t)
        else:
            used.add(hit)
            matched.append({"region": t.get("region"), "a": abs(ta[hit]["peakCirculationM2s"]), "b": abs(t["peakCirculationM2s"])})
    gone = [u for i, u in enumerate(ta) if i not in used]
    out["wiry"] = {"wspolne": matched, "nowe": new, "znikniete": gone}
    za, zb = _get(a, "raport", "walls", "zones") or {}, _get(b, "raport", "walls", "zones") or {}

    def share(zones, group):
        rows = [z.get("reverseFlow") or {} for z in zones.values() if z.get("group") == group]
        area = sum(r.get("horizontalAreaM2") or 0.0 for r in rows)
        return None if area <= 0 else sum((r.get("areaShare") or 0.0) * (r.get("horizontalAreaM2") or 0.0) for r in rows) / area

    rev = []
    for g in ("fw", "rw", "floor", "body"):
        sa, sb = share(za, g), share(zb, g)
        if sa is not None and sb is not None:
            rev.append({"czesc": g, "nazwa": part_name(g), "a_pct": 100 * sa, "b_pct": 100 * sb, "delta_pp": 100 * (sb - sa)})
    out["oderwania"] = rev
    return out


def trust(a: dict, b: dict) -> dict:
    """How far the explanation can be trusted: method differences, unfinished runs, missing evidence."""
    pa, pb = dict(a.get("paczka") or {}), dict(b.get("paczka") or {})
    pa["_name"], pb["_name"] = name_of(a), name_of(b)
    issues = differences([pa, pb])
    method = [i for i in issues if i.startswith(("Różni się model", "Różni się traktowanie"))]
    other = [i for i in issues if i not in method]
    level = "niska" if method else "srednia" if other else "wysoka"
    return {"poziom": level, "powody": issues, "metoda_rozni_sie": bool(method)}


def sentences(result: dict) -> list[str]:
    """The explanation in plain sentences, most important first."""
    t = result["calkowite"]
    out = []
    df, cd = t.get("downforce"), t.get("Cd")
    if df and cd:
        out.append(f"Docisk zmienił się o {df['delta']:+.2f} ({df['pct']:+.0f}%), opór o {cd['delta']:+.2f} ({cd['pct']:+.0f}%).")
    rows = result["czesci"]
    if rows:
        top = rows[0]
        share = top["udzial_df_pct"]
        if share is not None and abs(share) >= 1:
            out.append(f"Za zmianę docisku odpowiada głównie: {top['nazwa']} ({top['d_df']:+.2f}, czyli {share:.0f}% całej zmiany).")
        others = [f"{r['nazwa']} {r['d_df']:+.2f}" for r in rows[1:4] if abs(r["d_df"]) >= 0.05]
        if others:
            out.append("Dalej: " + "; ".join(others) + ".")
        by_drag = max(rows, key=lambda r: abs(r["d_cd"]))
        out.append(f"Opór zmienił się najbardziej na: {by_drag['nazwa']} ({by_drag['d_cd']:+.2f}).")
    where = result["gdzie_wzdluz"].get(rows[0]["czesc"]) if rows else None
    if where:
        out.append(f"Na części „{rows[0]['nazwa']}” zmiana jest największa w pasach: " + ", ".join(f"x = {w['x_m']:.2f} m ({w['delta']:+.2f})" for w in where) + ".")
    cop = result.get("srodek_parcia")
    if cop:
        lead = cop["wklady"][0]
        out.append(f"Środek docisku przesunął się o {cop['delta']:+.2f} m (z {cop['a']:.2f} na {cop['b']:.2f} m), najbardziej przez: {lead['nazwa']} ({lead['wklad_m']:+.2f} m).")
    bal = t.get("frontPct")
    if bal:
        out.append(f"Balans przód/tył: {bal['a']:.0f}% → {bal['b']:.0f}% z przodu.")
    geo = result["geometria"][:3]
    if geo:
        out.append("Zmiana obrysu: " + "; ".join(f"{g['nazwa']}, {g['wymiar']} {g['delta']:+.2f} m" for g in geo) + ".")
    fl = result["przeplyw"]
    if fl.get("strata"):
        s = fl["strata"]["za_autem"]
        out.append(f"Za autem strata energii powietrza to {s['b']:.2f} m² (było {s['a']:.2f}).")
    w = fl.get("wiry") or {}
    if w.get("nowe"):
        out.append("Nowe silne wiry: " + "; ".join(f"{v.get('region')} ({abs(v['peakCirculationM2s']):.1f} m²/s)" for v in w["nowe"][:2]) + ".")
    if w.get("znikniete"):
        out.append("Zniknęły wiry: " + "; ".join(f"{v.get('region')} ({abs(v['peakCirculationM2s']):.1f} m²/s)" for v in w["znikniete"][:2]) + ".")
    for r in fl.get("oderwania") or []:
        if abs(r["delta_pp"]) >= 1.0:
            out.append(f"Oderwanie na części „{r['nazwa']}”: {r['a_pct']:.1f}% → {r['b_pct']:.1f}% powierzchni.")
    tr = result["pewnosc"]
    out.append({"niska": "Ufaj temu ostrożnie: różnica jest częściowo różnicą metody, a nie bolidu.", "srednia": "Ufaj z zastrzeżeniami (patrz powody).", "wysoka": "Porównanie jest uczciwe: ta sama metoda."}[tr["poziom"]])
    return out


def explain(a: dict, b: dict) -> dict:
    """Why `b` differs from `a`. Both are loaded `meta.json` files."""
    rows = parts(a, b)
    top = [r["czesc"] for r in rows[:3]]
    result = {
        "a": name_of(a),
        "b": name_of(b),
        "calkowite": totals(a, b),
        "czesci": rows,
        "gdzie_wzdluz": along_x(a, b, top),
        "srodek_parcia": centre_of_pressure(a, b),
        "geometria": geometry(a, b),
        "przeplyw": flow(a, b),
        "pewnosc": trust(a, b),
    }
    result["wnioski"] = sentences(result)
    return result


def render(result: dict) -> str:
    """Markdown for people."""
    lines = [f"# Dlaczego {result['b']} różni się od {result['a']}", "", f"Punkt odniesienia: **{result['a']}**. Pewność wyjaśnienia: **{result['pewnosc']['poziom']}**.", ""]
    lines += ["## W skrócie", ""] + [f"- {s}" for s in result["wnioski"]] + [""]
    t = result["calkowite"]
    lines += ["## Całość", "", "| | " + result["a"] + " | " + result["b"] + " | Zmiana |", "| --- | --- | --- | --- |"]
    for key, label, digits in (("Cd", "Opór Cd", 3), ("downforce", "Docisk", 3), ("LOverD", "Docisk / opór", 2), ("frontPct", "Balans: przód [%]", 1), ("copXM", "Środek parcia [m]", 3)):
        d = t.get(key)
        if d:
            pct = "" if d["pct"] is None else f" ({d['pct']:+.0f}%)"
            lines.append(f"| {label} | {d['a']:.{digits}f} | {d['b']:.{digits}f} | {d['delta']:+.{digits}f}{pct} |")
    lines += ["", "## Które części", "", "Udział to część całej zmiany. Udziały sumują się do 100%.", "", "| Część | Docisk A | Docisk B | Zmiana | Udział | Zmiana oporu |", "| --- | --- | --- | --- | --- | --- |"]
    for r in result["czesci"]:
        share = "brak" if r["udzial_df_pct"] is None else f"{r['udzial_df_pct']:.0f}%"
        lines.append(f"| {r['nazwa']} | {r['df_a']:.3f} | {r['df_b']:.3f} | {r['d_df']:+.3f} | {share} | {r['d_cd']:+.3f} |")
    lines.append("")
    if result["gdzie_wzdluz"]:
        lines += ["## Gdzie wzdłuż auta", ""]
        for g, rows in result["gdzie_wzdluz"].items():
            lines.append(f"- **{part_name(g)}**: " + ", ".join(f"x = {r['x_m']:.2f} m ({r['delta']:+.3f})" for r in rows))
        lines.append("")
    cop = result.get("srodek_parcia")
    if cop:
        lines += ["## Środek docisku", "", f"Z {cop['a']:.3f} m na {cop['b']:.3f} m ({cop['delta']:+.3f} m). Wkłady części: " + ", ".join(f"{w['nazwa']} {w['wklad_m']:+.3f}" for w in cop["wklady"][:4]) + f". {cop['uwaga'].capitalize()}.", ""]
    if result["geometria"]:
        lines += ["## Co zmieniło się w geometrii", "", "Z obrysu stref ścian (przesunięcia o 1 cm i więcej):", ""] + [f"- {g['nazwa']}, {g['wymiar']}: {g['a']:.3f} → {g['b']:.3f} m ({g['delta']:+.3f})" for g in result["geometria"][:8]] + [""]
    fl = result["przeplyw"]
    lines += ["## Co zmieniło się w przepływie", "", "To jest zapis tego, co widać obok zmiany sił. Nie jest dowodem przyczyny.", ""]
    if fl.get("strata"):
        for s in fl["strata"]["najwieksze_roznice_przyrostu"]:
            lines.append(f"- Przyrost straty między x = {s['fromX_m']:.1f} a {s['toX_m']:.1f} m: {s['a']:.3f} → {s['b']:.3f} m² ({s['delta']:+.3f})")
    w = fl.get("wiry") or {}
    for v in w.get("wspolne", []):
        lines.append(f"- Wir „{v['region']}”: {v['a']:.1f} → {v['b']:.1f} m²/s")
    lines += [f"- Nowy wir: {v.get('region')} ({abs(v['peakCirculationM2s']):.1f} m²/s)" for v in w.get("nowe", [])]
    lines += [f"- Zniknął wir: {v.get('region')} ({abs(v['peakCirculationM2s']):.1f} m²/s)" for v in w.get("znikniete", [])]
    lines += [f"- Oderwanie, {r['nazwa']}: {r['a_pct']:.1f}% → {r['b_pct']:.1f}%" for r in fl.get("oderwania") or []]
    lines += ["", "## Ile temu ufać", ""] + [f"- {p}" for p in result["pewnosc"]["powody"]] if result["pewnosc"]["powody"] else ["", "## Ile temu ufać", "", "Poza geometrią nic się nie różni."]
    return "\n".join(lines).rstrip() + "\n"
