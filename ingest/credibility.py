"""How far a simulation can be trusted, graded against practice and literature.

Every check has a weight, a verdict, a plain explanation and the source it comes from. The score
is the share of the weight that is passed, counted only over the checks that could be made. The
coverage says how much of the total weight that was. A high score with low coverage means "nothing
wrong was found, but little could be checked".

Be clear about what this is. It grades how the simulation was done (convergence, mesh, wall model,
set-up, domain) and whether the results sit where the literature puts similar cars. Agreement with
reality can only be stated against a measurement. Put one in `pomiary.json` next to the case and
it is compared; without it the report says so.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

OK, WARN, BAD, NONE = "ok", "uwaga", "zle", "brak"
CREDIT = {OK: 1.0, WARN: 0.5, BAD: 0.0}

SOURCES = {
    "ansys-guide": ("ANSYS Fluent, Guide to a Successful Simulation: residuals, a mass imbalance below 1% of the smallest boundary flux and stable monitors together decide convergence", "https://www.afs.enea.it/project/neptunius/docs/fluent/html/gs/node17.htm"),
    "ansys-mesh": ("ANSYS Meshing, Check Mesh Quality: keep the minimum orthogonal quality above about 0.1", "https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/wb_msh/msh_check_mesh_quality.html"),
    "menter": ("Menter F.R. (1994), Two-equation eddy-viscosity turbulence models for engineering applications, AIAA Journal 32(8): the SST model resolves the viscous sublayer down to y+ of about 1", "https://en.wikipedia.org/wiki/Menter's_Shear_Stress_Transport"),
    "wall-functions": ("Standard wall functions need the first cell in the log layer, y+ 30 to 300, and not in the buffer layer 5 to 30. Enhanced wall treatment tolerates any y+", "https://innovationspace.ansys.com/forum/forums/topic/near-wall-treatment/"),
    "celik": ("Celik I.B., Ghia U., Roache P.J., Freitas C.J., Coleman H., Raad P.E. (2008), Procedure for estimation and reporting of uncertainty due to discretization in CFD applications, J. Fluids Eng. 130(7): 078001 (the GCI method)", "https://dl.acm.org/doi/10.5555/2799685.2799698"),
    "katz": ("Katz J. (2006), Aerodynamics of race cars, Annu. Rev. Fluid Mech. 38: wheels contribute about 40% of the drag of an open-wheel car", "https://sites.fem.unicamp.br/~phoenics/EM974/PROJETOS/Temas%20Projetos/Cars%20aerodynamics/annurev.fluid.38.050304.092016.pdf"),
    "waschle": ("Wäschle A. (2007), The influence of rotating wheels on vehicle aerodynamics, SAE 2007-01-0107: rotating wheels and a moving ground change the forces and have to be modelled", "https://saemobilus.sae.org/papers/influence-rotating-wheels-vehicle-aerodynamics-numerical-experimental-investigations-2007-01-0107"),
    "domain": ("Domain size practice for car aerodynamics: inlet 2 to 4 vehicle lengths ahead, outlet 6 to 7 behind, negligible blockage on open road (e.g. CFD simulation of aerodynamic forces on the DrivAer car model: impact of computational parameters, J. Wind Eng. Ind. Aerodyn. 2024)", "https://www.sciencedirect.com/science/article/pii/S0167610524000746"),
    "gupta": ("Gupta S., Saxena K. (2017), Aerodynamics analysis of a Formula SAE car, Univ. of Pretoria: lap-time optimum Cd 1.53 and downforce coefficient 3.6 for a Formula Student car; balance set by a moment balance about the centre of gravity", "https://repository.up.ac.za/bitstream/handle/2263/62356/Gupta_Aerodynamics_2017.pdf?sequence=1"),
    "wordley": ("Wordley S., Saunders J. (2006), Aerodynamics for Formula SAE: a numerical, wind tunnel and on-track study, SAE 2006-01-0808: CFD, wind tunnel and track agree only when validated against measurement", "https://www.sae.org/publications/technical-papers/content/2006-01-0808/"),
    "ercoftac": ("Casey M., Wintergerste T. (2000), ERCOFTAC Best Practice Guidelines for Industrial CFD: monitor integral quantities, not only residuals", "https://www.ercoftac.org/publications/ercoftac_best_practice_guidelines/"),
}

# Weights add up to 100. The measurement check is extra and only counts when a measurement is given.
WEIGHTS = {
    "residua": 8, "zbieznosc-sil": 10, "bilans-masy": 6, "suma-sil": 6, "przebieg": 4, "siatka-gci": 6,
    "yplus": 10, "jakosc-siatki": 7, "pierwsza-komorka": 4, "oderwania": 4,
    "podloze": 6, "kola-obroty": 6, "domena": 5, "model": 3,
    "zakres-wspolczynnikow": 4, "udzial-kol": 4, "balans": 3, "znak": 2,
    "pomiar": 12,
}
CATEGORIES = {
    "Zbieżność i rachunek": ("residua", "zbieznosc-sil", "bilans-masy", "suma-sil", "przebieg", "siatka-gci"),
    "Siatka i ściana": ("yplus", "jakosc-siatki", "pierwsza-komorka", "oderwania"),
    "Ustawienia fizyczne": ("podloze", "kola-obroty", "domena", "model"),
    "Wyniki względem literatury": ("zakres-wspolczynnikow", "udzial-kol", "balans", "znak"),
    "Zgodność z pomiarem": ("pomiar",),
}


def _get(data, *path):
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _check(cid: str, title: str, status: str, value: str, detail: str, sources: tuple[str, ...] = ()) -> dict:
    return {"id": cid, "title": title, "weight": WEIGHTS[cid], "status": status, "value": value, "detail": detail, "sources": list(sources)}


# ------------------------------------------------------------------ geometry facts

def domain_extent(cas_path: Path) -> dict:
    """Bounding box of all mesh nodes: the size of the computational domain."""
    import h5py

    from ingest.h5_mesh import node_coords

    with h5py.File(cas_path, "r") as mesh:
        coords = node_coords(mesh)
        lo = np.full(3, np.inf)
        hi = np.full(3, -np.inf)
        step = 4_000_000
        for start in range(0, int(coords.shape[0]), step):
            block = np.asarray(coords[start : start + step])
            lo = np.minimum(lo, block.min(axis=0))
            hi = np.maximum(hi, block.max(axis=0))
    return {"minM": [round(float(v), 3) for v in lo], "maxM": [round(float(v), 3) for v in hi]}


def car_extent(walls: dict | None) -> dict | None:
    """Bounding box of the car from the vehicle wall zones."""
    boxes = [z["bboxM"] for z in ((walls or {}).get("zones") or {}).values() if z.get("group") and z.get("bboxM")]
    if not boxes:
        return None
    lo = np.min([b[0] for b in boxes], axis=0)
    hi = np.max([b[1] for b in boxes], axis=0)
    return {"minM": [round(float(v), 3) for v in lo], "maxM": [round(float(v), 3) for v in hi]}


# ----------------------------------------------------------------------- checks

def _from_report(checks: list[dict], cid: str) -> dict | None:
    return next((c for c in checks if c["id"] == cid), None)


def _reuse(report_checks: list[dict], source_id: str, cid: str, title: str, sources: tuple[str, ...], hint: str = "") -> dict:
    found = _from_report(report_checks, source_id)
    if not found or found["status"] == NONE:
        return _check(cid, title, NONE, "brak", (found or {}).get("detail", "Brak danych do tego sprawdzenia."), sources)
    return _check(cid, title, found["status"], found["value"], found["detail"] + (" " + hint if hint else ""), sources)


def check_mesh_independence(study: dict | None) -> dict:
    title = "Wynik nie zależy od gęstości siatki"
    src = ("celik",)
    if not study:
        return _check("siatka-gci", title, NONE, "nie wykonano", "Nie ma testu niezależności od siatki (trzy siatki tego samego bolidu). To największa niewiadoma tej oceny: nie wiadomo, o ile wynik zmieniłby się na gęstszej siatce.", src)
    rows = {q["id"]: q for q in study.get("quantities", [])}
    gci = [rows[k].get("gciFinePct") for k in ("Cd", "downforce") if k in rows and rows[k].get("gciFinePct") is not None]
    if not gci:
        diffs = [abs(d) for k in ("Cd", "downforce") if k in rows for d in rows[k].get("relativeDifferencePct", []) if d is not None]
        if not diffs:
            return _check("siatka-gci", title, NONE, "brak", "Test siatki nie dał liczb.", src)
        worst = max(diffs)
        status = OK if worst <= 1 else WARN if worst <= 3 else BAD
        return _check("siatka-gci", title, status, f"różnica {worst:.1f}%", "Są tylko dwie siatki, więc widać różnicę, ale nie niepewność (GCI).", src)
    worst = max(gci)
    status = OK if worst <= 3 else WARN if worst <= 5 else BAD
    return _check("siatka-gci", title, status, f"GCI {worst:.1f}%", "Niepewność wyniku z gęstości siatki (GCI), dla oporu i docisku.", src)


def check_oderwania(walls: dict | None, model: str) -> dict:
    title = "Oderwania, które RANS liczy niepewnie"
    src = ("wordley",)
    total_rev, total_area = 0.0, 0.0
    for z in ((walls or {}).get("zones") or {}).values():
        if z.get("group") in ("fw", "rw", "floor"):
            rf = z.get("reverseFlow") or {}
            if rf.get("areaShare") is not None:
                total_rev += rf["areaShare"] * (rf.get("horizontalAreaM2") or 0.0)
                total_area += rf.get("horizontalAreaM2") or 0.0
    if total_area <= 0:
        return _check("oderwania", title, NONE, "brak", "Brak pól przy ścianie do oceny oderwań.", src)
    share = total_rev / total_area
    status = OK if share < 0.03 else WARN if share < 0.10 else BAD
    return _check(
        "oderwania",
        title,
        status,
        f"{100 * share:.1f}% powierzchni",
        "Stacjonarny RANS dobrze liczy przepływ przyklejony, a gorzej oderwany i niestacjonarny. Im więcej oderwania na skrzydłach i podłodze, tym mniej pewne siły, i tym bardziej liczy się pomiar.",
        src,
    )


def check_ground(walls: dict | None, speed: float | None) -> dict:
    title = "Ruchoma podłoga"
    src = ("waschle",)
    zone = ((walls or {}).get("zones") or {}).get("domain_ground")
    if not zone or not zone.get("wallSpeedMs") or not speed:
        return _check("podloze", title, NONE, "brak", "Nie odczytano prędkości ściany podłoża.", src)
    v = zone["wallSpeedMs"]["median"]
    ratio = v / speed
    if abs(ratio - 1) <= 0.02:
        return _check("podloze", title, OK, f"{v:.2f} m/s", "Podłoże porusza się z prędkością strumienia, jak ruchoma taśma w tunelu. Przepływ pod autem nie rośnie na nieruchomej ziemi.", src)
    if v < 0.05 * speed:
        return _check("podloze", title, BAD, f"{v:.2f} m/s", "Podłoże stoi. Pod autem narasta warstwa przyścienna, której nie ma na torze, i to zmienia podłogę i dyfuzor.", src)
    return _check("podloze", title, WARN, f"{v:.2f} m/s", f"Prędkość podłoża to {100 * ratio:.0f}% prędkości strumienia, a powinna być równa.", src)


def check_wheels(walls: dict | None, speed: float | None) -> dict:
    title = "Koła obracają się z prędkością jazdy"
    src = ("waschle",)
    speeds = [z["wallSpeedMs"]["max"] for n, z in ((walls or {}).get("zones") or {}).items() if "wheel" in n and "rotary" in n and z.get("wallSpeedMs")]
    if not speeds or not speed:
        return _check("kola-obroty", title, NONE, "brak", "Nie znaleziono wirujących stref kół albo prędkości.", src)
    top = max(speeds)
    ratio = top / speed
    if 0.93 <= ratio <= 1.12:
        return _check("kola-obroty", title, OK, f"{top:.1f} m/s na bieżniku", "Prędkość obwodowa bieżnika zgadza się z prędkością jazdy, czyli opony toczą się bez poślizgu.", src)
    return _check("kola-obroty", title, BAD if ratio < 0.8 or ratio > 1.3 else WARN, f"{top:.1f} m/s na bieżniku", f"Prędkość obwodowa to {100 * ratio:.0f}% prędkości jazdy. Koła kręcą się za wolno lub za szybko, a opór kół (często ponad 30% całego) jest wtedy niewiarygodny.", src)


def check_domain(domain: dict | None, car: dict | None, aref_half: float | None, half: bool) -> dict:
    title = "Rozmiar domeny obliczeniowej"
    src = ("domain",)
    if not domain or not car:
        return _check("domena", title, NONE, "brak", "Nie ustalono wymiarów domeny albo samochodu.", src)
    length = car["maxM"][0] - car["minM"][0]
    ahead = car["minM"][0] - domain["minM"][0]
    behind = domain["maxM"][0] - car["maxM"][0]
    width = domain["maxM"][1] - domain["minM"][1]
    height = domain["maxM"][2] - domain["minM"][2]
    cross = width * height
    blockage = (aref_half or 0.0) / cross if cross > 0 and aref_half else None
    problems = []
    if ahead < 2 * length:
        problems.append(f"przed autem jest {ahead / length:.1f} długości (zalecane co najmniej 2)")
    if behind < 5 * length:
        problems.append(f"za autem jest {behind / length:.1f} długości (zalecane 6 do 7)")
    if blockage is not None and blockage > 0.05:
        problems.append(f"blokada {100 * blockage:.1f}% (zalecane poniżej 5%)")
    value = f"{ahead / length:.1f} L przed, {behind / length:.1f} L za" + ("" if blockage is None else f", blokada {100 * blockage:.2f}%")
    if not problems:
        return _check("domena", title, OK, value, f"Długość auta {length:.2f} m. Domena jest dość duża, żeby ściany nie zaburzały przepływu wokół auta.", src)
    status = BAD if blockage is not None and blockage > 0.10 else WARN
    return _check("domena", title, status, value, "Domena może być za mała: " + "; ".join(problems) + ".", src)


def check_model(model: str | None, wall: str | None) -> dict:
    title = "Model turbulencji pasuje do zadania"
    src = ("menter",)
    if not model:
        return _check("model", title, NONE, "brak", "Nie odczytano modelu turbulencji.", src)
    m = model.lower()
    if "sst" in m:
        return _check("model", title, OK, model, "k-omega SST to zwykły wybór dla zewnętrznej aerodynamiki z oderwaniem i dużymi gradientami ciśnienia przy skrzydłach.", src)
    if "realizable" in m or "k-epsilon" in m or "k-ε" in m:
        return _check("model", title, WARN, model, "k-epsilon jest szybszy, ale ogólnie przyjęta praktyka to SST dla zewnętrznej aerodynamiki z oderwaniem i dużymi gradientami ciśnienia (skrzydła wieloelementowe). Wyniki skrzydeł traktuj ostrożniej.", src)
    return _check("model", title, WARN, model, "Nietypowy model dla aerodynamiki bolidu. Brak odniesienia z literatury do oceny.", src)


# Literature anchors are points of reference, not limits (see the `gupta` source).
CD_RANGE = (0.8, 2.2)
DOWNFORCE_RANGE = (2.0, 6.0)
WHEEL_SHARE_LOW = 20.0


def check_coefficient_range(kpis: dict) -> dict:
    title = "Opór i docisk w typowym zakresie"
    src = ("gupta",)
    cd, df = _num(kpis.get("Cd")), _num(kpis.get("downforceCoeff"))
    if cd is None or df is None:
        return _check("zakres-wspolczynnikow", title, NONE, "brak", "Brak Cd lub docisku.", src)
    out = []
    if not CD_RANGE[0] <= cd <= CD_RANGE[1]:
        out.append(f"Cd {cd:.2f} poza przedziałem {CD_RANGE[0]} do {CD_RANGE[1]}")
    if not DOWNFORCE_RANGE[0] <= df <= DOWNFORCE_RANGE[1]:
        out.append(f"docisk {df:.2f} poza przedziałem {DOWNFORCE_RANGE[0]} do {DOWNFORCE_RANGE[1]}")
    detail = f"Punkt odniesienia z literatury: Cd ok. 1,53 i docisk ok. 3,6 dla bolidu Formula Student (Gupta i Saxena). Tu Cd {cd:.2f}, docisk {df:.2f}, docisk/opór {df / cd:.2f}."
    if out:
        return _check("zakres-wspolczynnikow", title, WARN, f"Cd {cd:.2f}, docisk {df:.2f}", detail + " " + "; ".join(out) + ". To nie musi być błąd, ale sprawdź powierzchnię odniesienia.", src)
    return _check("zakres-wspolczynnikow", title, OK, f"Cd {cd:.2f}, docisk {df:.2f}", detail, src)


def check_wheel_share(walls: dict | None) -> dict:
    title = "Udział kół w oporze"
    src = ("katz",)
    group = ((walls or {}).get("groups") or {}).get("wheels")
    if not group or group.get("shareDragPct") is None:
        return _check("udzial-kol", title, NONE, "brak", "Brak podziału oporu na części.", src)
    share = group["shareDragPct"]
    detail = "Dla bolidu z odsłoniętymi kołami literatura podaje ok. 40% oporu na kołach (Katz 2006). "
    if share >= WHEEL_SHARE_LOW:
        return _check("udzial-kol", title, OK, f"{share:.0f}%", detail + "Wynik mieści się w sensownym zakresie.", src)
    return _check("udzial-kol", title, WARN, f"{share:.0f}%", detail + f"Tu {share:.0f}%, czyli wyraźnie mniej. Może to oznaczać zbyt małe opory kół (np. zasłonięte przez nadwozie, uproszczona geometria opony, zła rotacja) albo po prostu inny bolid. Warto sprawdzić geometrię kół.", src)


def check_balance(kpis: dict, expected_front_pct: float | None) -> dict:
    title = "Balans aero zgodny z masą"
    src = ("gupta",)
    front = _num(_get(kpis, "aeroBalance", "frontPct"))
    if front is None:
        return _check("balans", title, NONE, "brak", "Balans aero nie został policzony.", src)
    if expected_front_pct is None:
        return _check("balans", title, NONE, f"{front:.0f}% z przodu", "Nie znam rozkładu masy. Balans aero powinien być zbliżony do niego (Gupta i Saxena dobierają go z bilansu momentów względem środka ciężkości). Podaj `przod_masa_pct` w `pomiary.json`.", src)
    diff = abs(front - expected_front_pct)
    status = OK if diff <= 5 else WARN if diff <= 12 else BAD
    return _check("balans", title, status, f"{front:.0f}% z przodu, masa {expected_front_pct:.0f}%", f"Różnica {diff:.0f} punktów. Duża różnica oznacza, że aero przesuwa obciążenie osi względem tego, na co jest ustawiony bolid.", src)


def check_sign(kpis: dict) -> dict:
    title = "Znak i spójność sił"
    df, cd = _num(kpis.get("downforceCoeff")), _num(kpis.get("Cd"))
    verified = kpis.get("forceVectorVerified")
    if df is None or cd is None:
        return _check("znak", title, NONE, "brak", "Brak sił.")
    problems = []
    if df <= 0:
        problems.append("docisk nie jest dodatni, a to bolid z aerodynamiką dociskową")
    if cd <= 0:
        problems.append("opór nie jest dodatni")
    if verified is False:
        problems.append("znak sił nie został potwierdzony w ustawieniach")
    if problems:
        return _check("znak", title, BAD if (df <= 0 or cd <= 0) else WARN, "niespójne", "; ".join(problems).capitalize() + ".")
    return _check("znak", title, OK, "spójne", "Opór i docisk mają sensowny znak, a wektory sił są potwierdzone w ustawieniach.")


def check_measurement(kpis: dict, measured: dict | None, refs: dict | None) -> dict:
    title = "Zgodność z pomiarem"
    src = ("wordley",)
    if not measured:
        return _check("pomiar", title, NONE, "brak pomiaru", "Bez pomiaru z tunelu lub toru nie da się powiedzieć nic o zgodności z rzeczywistością. Podaj go w `pomiary.json` (CdA_m2, ClA_m2), a porównam.", src)
    parts = []
    errors = []
    area = None if not refs else refs["aref_m2"] * (2.0 if refs.get("half") else 1.0)
    for key, mine in (("CdA_m2", _num(kpis.get("Cd"))), ("ClA_m2", _num(kpis.get("downforceCoeff")))):
        ref = _num(measured.get(key))
        if ref is None or mine is None or not area:
            continue
        sim = mine * area
        err = (sim - ref) / ref
        errors.append(abs(err))
        parts.append(f"{key}: symulacja {sim:.2f}, pomiar {ref:.2f} ({100 * err:+.0f}%)")
    if not errors:
        return _check("pomiar", title, NONE, "brak", "W `pomiary.json` nie ma CdA_m2 ani ClA_m2.", src)
    worst = max(errors)
    status = OK if worst <= 0.10 else WARN if worst <= 0.20 else BAD
    origin = measured.get("zrodlo")
    return _check("pomiar", title, status, f"błąd do {100 * worst:.0f}%", "; ".join(parts) + (f". Źródło pomiaru: {origin}." if origin else "."), src)


# ------------------------------------------------------------------------ the whole

def assess(
    report: dict,
    *,
    domain: dict | None = None,
    mesh_study: dict | None = None,
    measured: dict | None = None,
) -> dict:
    """Grade one case. `report` is the dict `build_report` returns."""
    pack = report["pack"]
    walls = report.get("walls")
    kpis = pack.get("kpis") or {}
    checks = report.get("checks") or []
    refs_raw = _get(kpis, "references") or {}
    speed = _num(_get(refs_raw, "speedMs", "value"))
    aref = _num(_get(refs_raw, "frontalAreaM2", "value"))
    half = bool((pack.get("identity") or {}).get("halfModel"))
    model = _get(pack, "methods", "turbulence")
    refs = {"aref_m2": aref, "half": half} if aref else None
    items = [
        _reuse(checks, "residua", "residua", "Residua poniżej 1e-3", ("ansys-guide", "ercoftac"), "Residua same nie wystarczą, ważne są też siły i bilans masy."),
        _reuse(checks, "zbieznosc-sil", "zbieznosc-sil", "Siły się ustabilizowały", ("ansys-guide", "ercoftac")),
        _reuse(checks, "bilans-masy", "bilans-masy", "Bilans masy się domyka", ("ansys-guide",)),
        _reuse(checks, "suma-sil", "suma-sil", "Siły na części sumują się do monitorów", ("ercoftac",)),
        _reuse(checks, "przebieg", "przebieg", "Liczenie przeszło bez awarii", ("ansys-guide",)),
        check_mesh_independence(mesh_study),
        _reuse(checks, "yplus", "yplus", "y+ pasuje do modelu turbulencji", ("menter", "wall-functions")),
        _reuse(checks, "siatka", "jakosc-siatki", "Jakość siatki", ("ansys-mesh",)),
        _reuse(checks, "warstwy", "pierwsza-komorka", "Warstwy przyścienne", ("menter",)),
        check_oderwania(walls, model or ""),
        check_ground(walls, speed),
        check_wheels(walls, speed),
        check_domain(domain, car_extent(walls), aref, half),
        check_model(model, _get(pack, "methods", "wallTreatment")),
        check_coefficient_range(kpis),
        check_wheel_share(walls),
        check_balance(kpis, _num((measured or {}).get("przod_masa_pct"))),
        check_sign(kpis),
        check_measurement(kpis, measured, refs),
    ]
    return summarize(items)


def summarize(items: list[dict]) -> dict:
    """Score over the checks that could be made, the coverage, and the unknowns.

    The measurement check is a bonus: its weight only counts when there is a measurement.
    """
    counted = [c for c in items if c["id"] != "pomiar" or c["status"] != NONE]
    known = [c for c in counted if c["status"] != NONE]
    total_weight = sum(c["weight"] for c in counted)
    known_weight = sum(c["weight"] for c in known)
    earned = sum(c["weight"] * CREDIT[c["status"]] for c in known)
    score = None if known_weight == 0 else round(100.0 * earned / known_weight)
    coverage = 0 if total_weight == 0 else round(100.0 * known_weight / total_weight)
    bad = [c["title"] for c in items if c["status"] == BAD]
    unknown = [c["title"] for c in items if c["status"] == NONE]
    if score is None:
        label = "Nie da się ocenić"
    elif score >= 85 and coverage >= 70 and not bad:
        label = "Wysoka wiarygodność"
    elif score >= 65 and not (bad and score < 75):
        label = "Umiarkowana wiarygodność"
    else:
        label = "Niska wiarygodność"
    by_cat = {}
    for name, ids in CATEGORIES.items():
        got = [c for c in items if c["id"] in ids and c["status"] != NONE]
        by_cat[name] = round(100.0 * sum(c["weight"] * CREDIT[c["status"]] for c in got) / sum(c["weight"] for c in got)) if got else None
    return {"score": score, "coverage": coverage, "label": label, "byCategory": by_cat, "checks": items, "bad": bad, "unknown": unknown}


def load_measurements(folder: Path) -> dict | None:
    """`pomiary.json` next to the case: CdA_m2, ClA_m2, przod_masa_pct, zrodlo."""
    path = Path(folder) / "pomiary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------ writing

LIGHT = {OK: "🟢 OK", WARN: "🟡 UWAGA", BAD: "🔴 ŹLE", NONE: "⚪ BRAK DANYCH"}


def render(result: dict, case: str) -> str:
    score = result["score"]
    lines = [
        f"# Wiarygodność symulacji: {case}",
        "",
        f"**{result['label']}: {'brak oceny' if score is None else f'{score} na 100'}** (pokrycie danymi {result['coverage']}%).",
        "",
        "Ocena mówi o tym, jak symulację wykonano (zbieżność, siatka, ściana, ustawienia, domena) i czy wyniki leżą tam, gdzie literatura stawia podobne bolidy. "
        "To nie jest dowód zgodności z rzeczywistością. Ta wymaga pomiaru z tunelu lub toru.",
        "",
        "Wynik liczy się tylko z tych sprawdzeń, które dało się wykonać. Pokrycie mówi, jaką część wagi to było: wysoka ocena przy niskim pokryciu znaczy „nic złego nie znaleziono, ale mało sprawdzono”.",
        "",
        "## Oceny według grup",
        "",
        "| Grupa | Ocena |",
        "| --- | --- |",
    ]
    for name, value in result["byCategory"].items():
        lines.append(f"| {name} | {'brak danych' if value is None else f'{value} / 100'} |")
    lines += ["", "## Wszystkie sprawdzenia", "", "| Sprawdzenie | Waga | Ocena | Wartość | Co to znaczy | Źródło |", "| --- | --- | --- | --- | --- | --- |"]
    for c in result["checks"]:
        refs = ", ".join(c["sources"])
        lines.append(f"| {c['title']} | {c['weight']} | {LIGHT[c['status']]} | {c['value']} | {c['detail']} | {refs} |")
    if result["unknown"]:
        lines += ["", "## Czego nie dało się sprawdzić", ""] + [f"- {u}" for u in result["unknown"]]
    used = []
    for c in result["checks"]:
        for s in c["sources"]:
            if s not in used:
                used.append(s)
    lines += ["", "## Źródła", ""]
    for key in used:
        text, url = SOURCES[key]
        lines.append(f"- **{key}**: {text}. {url}")
    lines += [
        "",
        "Progi w tym pliku (`ingest/credibility.py`) są praktyką z literatury i dokumentacji ANSYS, a nie twardymi normami. "
        "Zakres Cd i docisku to szerokie widełki wokół jedynego sprawdzonego punktu odniesienia (Cd ok. 1,5 i docisk ok. 3,6), nie granice poprawności.",
        "",
    ]
    return "\n".join(lines)
