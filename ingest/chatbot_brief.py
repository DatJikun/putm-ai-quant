"""Skrót paczki aeropack do wklejenia w czat bez narzędzi i bez liczenia."""

from __future__ import annotations

from pathlib import Path

BRAK = "brak"

PART_NAMES = {
    "fw": "przednie skrzydło (FW)",
    "rw": "tylne skrzydło (RW)",
    "floor": "podłoga",
    "body": "nadwozie",
    "wheels": "koła",
    "cooling": "chłodzenie",
    "other": "reszta",
}

REF_ROWS = (
    ("speedMs", "Prędkość", "m/s"),
    ("rho", "Gęstość ρ", "kg/m³"),
    ("mu", "Lepkość μ", "Pa·s"),
    ("frontalAreaM2", "Aref", "m²"),
    ("referenceLengthM", "Długość odniesienia", "m"),
)


def render_brief(pack: dict) -> str:
    parts = [
        _title(pack),
        _trust(pack),
        _headline_numbers(pack),
        _balance(pack),
        _convergence(pack),
        _setup(pack),
        _parts(pack),
        _warnings(pack),
        _rules(pack),
        _glossary(),
    ]
    return "\n".join(parts).rstrip() + "\n"


def write_brief(pack: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "dla-chatbota.md"
    dest.write_text(render_brief(pack), encoding="utf-8")
    return dest


def _kpis(pack: dict) -> dict:
    return pack.get("kpis") or {}


def _refs(pack: dict) -> dict:
    return (_kpis(pack).get("references")) or {}


def _balance_block(pack: dict) -> dict:
    return (_kpis(pack).get("aeroBalance")) or {}


def _conv(pack: dict) -> dict:
    return (_kpis(pack).get("convergence")) or {}


def _methods(pack: dict) -> dict:
    return pack.get("methods") or {}


def _sessions(pack: dict) -> list:
    raw = _methods(pack).get("solverSessions") or []
    return raw if isinstance(raw, list) else []


def _ref_value(pack: dict, key: str):
    item = _refs(pack).get(key) or {}
    if not isinstance(item, dict):
        return None
    return _as_float(item.get("value"))


def _ref_source(pack: dict, key: str) -> str:
    item = _refs(pack).get(key) or {}
    if not isinstance(item, dict):
        return BRAK
    return _text(item.get("source"))


def _as_float(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _text(value) -> str:
    if value is None or value is True or value is False:
        return BRAK
    text = str(value).strip()
    return text or BRAK


def _coeff(value) -> str:
    number = _as_float(value)
    return BRAK if number is None else f"{number:.3f}"


def _pct(value) -> str:
    number = _as_float(value)
    return BRAK if number is None else f"{number:.1f}"


def _newton(value) -> str:
    number = _as_float(value)
    return BRAK if number is None else str(int(round(number)))


def _plain(value) -> str:
    number = _as_float(value)
    if number is None:
        return BRAK
    magnitude = abs(number)
    if magnitude != 0 and (magnitude < 1e-3 or magnitude >= 1e6):
        return f"{number:.4g}"
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _metres(value) -> str:
    number = _as_float(value)
    return BRAK if number is None else f"{_plain(number)} m"


def _count(value) -> str:
    number = _as_float(value)
    if number is None:
        return BRAK
    return f"{int(round(number)):,}".replace(",", " ")


def _vec(value) -> str:
    if not isinstance(value, (list, tuple)) or not value:
        return BRAK
    return ", ".join(_plain(item) for item in value)


def _cell(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ")


def _bool_pl(value, yes: str = "tak", no: str = "nie") -> str:
    if value is True:
        return yes
    if value is False:
        return no
    return BRAK


def _title(pack: dict) -> str:
    ident = pack.get("identity") or {}
    vehicle = _text(ident.get("vehicle"))
    case_id = _text(ident.get("caseId"))
    yaw = ident.get("yawDeg")
    yaw_txt = BRAK if _as_float(yaw) is None else f"{_plain(yaw)}°"
    speed = _plain(_ref_value(pack, "speedMs"))
    speed_src = _ref_source(pack, "speedMs")
    if ident.get("halfModel") is True:
        model = "Połowa auta na płaszczyźnie symetrii."
    elif ident.get("halfModel") is False:
        model = "Identity nie oznacza half-modelu (brak potwierdzenia z transcriptu)."
    else:
        model = "Brak informacji, czy to połowa auta."
    return "\n".join([
        f"# {vehicle} — {case_id}",
        "",
        (
            "To jest skrót jednej symulacji CFD dla recenzenta AI. "
            "Czat nie ma plików solvera ani narzędzi. Każda liczba poniżej jest już policzona, "
            "z jednostką i źródłem. Nic tu nie licz od nowa i nic nie zgaduj."
        ),
        "",
        f"{model} Jazda na wprost, yaw {yaw_txt}. Prędkość {speed} m/s (źródło: {speed_src}).",
        "",
    ])


def _deciding_session(sessions: list) -> dict | None:
    """Session that actually solved. Falls back to the last file if none iterated."""
    if not sessions:
        return None
    for session in reversed(sessions):
        if session.get("lastIteration"):
            return session
    return sessions[-1]


def _verdict(pack: dict) -> str:
    settled = _conv(pack).get("settled")
    deciding = _deciding_session(_sessions(pack)) or {}
    if settled is False or deciding.get("crashed") is True:
        return "NIE PORÓWNUJ"
    if settled is None:
        return "OSTROŻNIE"
    return "OK"


def _trust_reasons(pack: dict) -> list[str]:
    conv = _conv(pack)
    sessions = _sessions(pack)
    deciding = _deciding_session(sessions)
    reasons = [item for item in (conv.get("reasons") or []) if isinstance(item, str) and item.strip()]
    if conv.get("stoppedEarly") is True:
        left = _plain(conv.get("iterationsLeft"))
        planned = _plain(conv.get("plannedIterations"))
        reasons.append(
            f"Liczenie zatrzymane przed planem: zostało {left} iteracji z planowanych {planned}."
        )
    for session in sessions:
        if session.get("crashed") is not True:
            continue
        why = ", ".join(session.get("crashReasons") or []) or "BAD TERMINATION"
        line = f"Sesja {_text(session.get('file'))} padła: {why}."
        if session is not deciding:
            line = f"Informacyjnie: {line}"
        reasons.append(line)
    residual = ((pack.get("monitors") or {}).get("residuals")) or {}
    continuity = _as_float(residual.get("continuity"))
    if continuity is not None and continuity > 1e-4:
        reasons.append(f"Residual continuity = {continuity:.3e} (powyżej 1e-4).")
    return reasons


def _trust(pack: dict) -> str:
    verdict = _verdict(pack)
    lead = {
        "NIE PORÓWNUJ": "Nie zestawiaj tej symulacji z innymi.",
        "OSTROŻNIE": "Liczby można czytać, ale wynik nie jest czysty.",
        "OK": "Siły są ustabilizowane, a sesja, która je doliczyła, nie padła.",
    }[verdict]
    lines = ["## Czy można ufać liczbom", "", f"Werdykt: {verdict}. {lead}", ""]
    reasons = _trust_reasons(pack)
    if reasons:
        lines.extend(f"- {item}" for item in reasons)
    else:
        lines.append("- Brak powodów do nieufności w tej paczce.")
    lines.append("")
    return "\n".join(lines)


def _dynamic_pressure(pack: dict) -> float | None:
    rho = _ref_value(pack, "rho")
    speed = _ref_value(pack, "speedMs")
    if rho is None or speed is None:
        return None
    return 0.5 * rho * speed * speed


def _headline_numbers(pack: dict) -> str:
    kpis = _kpis(pack)
    balance = _balance_block(pack)
    rows = [
        ("Cd (opór)", _coeff(kpis.get("Cd"))),
        ("Cl (ujemny Cl = docisk)", _coeff(kpis.get("Cl"))),
        ("Współczynnik docisku", _coeff(kpis.get("downforceCoeff"))),
        ("L/D", _coeff(kpis.get("LOverD"))),
        ("Balans aero, przód", _pct(balance.get("frontPct")) + ("%" if _as_float(balance.get("frontPct")) is not None else "")),
        ("Środek parcia X", _metres(balance.get("copXM"))),
    ]
    table = ["| Wielkość | Wartość |", "| --- | --- |"]
    table.extend(f"| {_cell(name)} | {_cell(value)} |" for name, value in rows)
    q = _dynamic_pressure(pack)
    area = _ref_value(pack, "frontalAreaM2")
    rho = _plain(_ref_value(pack, "rho"))
    speed = _plain(_ref_value(pack, "speedMs"))
    q_txt = BRAK if q is None else f"{q:.2f} Pa"
    area_txt = _plain(area)
    lines = [
        "## Najważniejsze liczby",
        "",
        "Ujemny Cl to docisk (siła w dół). Dodatni współczynnik docisku to ta sama siła zapisana w dół.",
        "",
        *table,
        "",
        (
            f"Siły w niutonach przy prędkości z tego case'a. "
            f"q = 0.5 × ρ × V² = {q_txt} "
            f"(ρ = {rho} kg/m³, V = {speed} m/s). "
            f"F = współczynnik × q × Aref. "
            f"Aref = {area_txt} m² (źródło: {_ref_source(pack, 'frontalAreaM2')}). "
            "Aref jest dla połowy modelu."
        ),
        "",
        "| Siła | pół auta (tak liczy solver) | całe auto (x2) |",
        "| --- | --- | --- |",
    ]
    for label, coeff in (
        ("Opór z Cd", kpis.get("Cd")),
        ("Docisk", kpis.get("downforceCoeff")),
    ):
        half = None if q is None or area is None or _as_float(coeff) is None else _as_float(coeff) * q * area
        full = None if half is None else half * 2.0
        lines.append(f"| {label} | {_newton(half)} N | {_newton(full)} N |")
    lines.append("")
    return "\n".join(lines)


def _balance(pack: dict) -> str:
    balance = _balance_block(pack)
    inputs = balance.get("inputs") or {}
    sources = balance.get("sources") or {}
    centre = inputs.get("momentCenterM")
    centre_txt = _vec(centre) + " m" if isinstance(centre, (list, tuple)) else BRAK
    if _as_float(balance.get("frontPct")) is None:
        missing = ", ".join(balance.get("missing") or []) or BRAK
        body = (
            f"Balans aero niepoliczony. Brakuje: {missing}. "
            "Nie zgaduj go i nie licz go jako 0.5 + Cm/Cz ani z udziałów FW/RW."
        )
    else:
        body = " ".join([
            f"Przód {_pct(balance.get('frontPct'))}%, tył {_pct(balance.get('rearPct'))}%.",
            (
                f"Współczynnik docisku osi przedniej {_coeff(balance.get('frontDownforceCoeff'))}, "
                f"tylnej {_coeff(balance.get('rearDownforceCoeff'))}."
            ),
            (
                "Jak policzone: moment cm z solvera przeniesiony na osie kół. "
                f"Punkt momentu {centre_txt}, oś momentu {_vec(inputs.get('momentAxis'))}, "
                f"długość odniesienia {_metres(_as_float(inputs.get('referenceLengthM')))}, "
                f"oś przednia X = {_metres(_as_float(inputs.get('frontAxleXM')))}, "
                f"oś tylna X = {_metres(_as_float(inputs.get('rearAxleXM')))}."
            ),
            (
                "Źródła: "
                f"moment {_text(sources.get('moment'))}, "
                f"długość odniesienia {_text(sources.get('referenceLength'))}, "
                f"osie kół {_text(sources.get('axles'))}."
            ),
            (
                "Nie przeliczaj balansu jako 0.5 + Cm/Cz ani z udziałów FW/RW. "
                f"Środek momentu w tym case to {centre_txt}."
            ),
        ])
    return "\n".join(["## Balans aero", "", body, ""])


def _monitor_row(name: str, stab, *, drift: bool = True) -> str:
    drift_missing = "nie dotyczy" if not drift else BRAK
    if not isinstance(stab, dict):
        return f"| {name} | {BRAK} | {BRAK} | {drift_missing} |"
    window = _plain(stab.get("window"))
    delta = _as_float(stab.get("delta"))
    delta_txt = BRAK if delta is None else f"{delta:.4f}"
    if not drift:
        drift_txt = "nie dotyczy"
    else:
        drift_pct = _pct(stab.get("driftPct"))
        drift_txt = BRAK if drift_pct == BRAK else f"{drift_pct}%"
    return f"| {name} | {window} | {delta_txt} | {drift_txt} |"


def _convergence(pack: dict) -> str:
    conv = _conv(pack)
    limits = conv.get("limits") or {}
    drift_lim = _pct(limits.get("driftPct"))
    bal_lim = _pct(limits.get("balancePp"))
    shift = _as_float(conv.get("balanceShiftPp"))
    shift_txt = BRAK if shift is None else f"{shift:.2f} pp"
    done = _plain(_kpis(pack).get("iterations"))
    planned = _plain(conv.get("plannedIterations"))
    left = _plain(conv.get("iterationsLeft")) if conv.get("stoppedEarly") is True else BRAK
    lines = [
        "## Zbieżność",
        "",
        "| Monitor | Ostatnie N iteracji | Delta | Dryf |",
        "| --- | --- | --- | --- |",
        _monitor_row("cx", conv.get("cx")),
        _monitor_row("cz", conv.get("cz")),
        _monitor_row("cm", conv.get("cm"), drift=False),
        "",
        "cm ocenia się przez przesunięcie balansu, nie przez procent.",
        f"Przesunięcie balansu: {shift_txt}. Limity: {drift_lim}% dla cx i cz, {bal_lim} pp dla balansu.",
        f"Iteracje: {done} zrobione / {planned} planowane. Niepoliczonych na końcu: {left}.",
        "",
    ]
    return "\n".join(lines)


def _layers(mesh: dict) -> list[str]:
    parsed = mesh.get("boundaryLayers")
    if not isinstance(parsed, dict):
        return [f"Warstwy przyścienne: {BRAK}."]
    layers = parsed.get("boundaryLayers") or []
    if not layers:
        return [f"Warstwy przyścienne: {BRAK}."]
    lines = ["Warstwy przyścienne (przepis z .wft, nie pomiar gotowej siatki):"]
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        zones = layer.get("zones") or []
        zone_txt = ", ".join(str(z) for z in zones) if zones else BRAK
        height = layer.get("firstHeightM")
        lines.append(
            f"- {_text(layer.get('name'))}: {_plain(layer.get('layers'))} warstw, "
            f"pierwsza wysokość {_metres(_as_float(height))}, strefy: {zone_txt}."
        )
    return lines


def _wheels(pack: dict) -> str:
    wheels = _methods(pack).get("wheelRotation")
    if not isinstance(wheels, dict) or not wheels:
        return "Obrót kół: brak potwierdzenia."
    bits = []
    for axle, label in (("front", "Przód"), ("rear", "Tył")):
        item = wheels.get(axle) or {}
        origin = item.get("originM") or [None, None, None]
        x = origin[0] if isinstance(origin, (list, tuple)) and origin else None
        bits.append(
            f"{label}: ściana {_text(item.get('zone'))}, "
            f"omega {_plain(item.get('omegaRadS'))} rad/s, oś X = {_metres(_as_float(x))}."
        )
    return "Koła to obracające się ściany. " + " ".join(bits)


def _setup(pack: dict) -> str:
    methods = _methods(pack)
    mesh = pack.get("mesh") or {}
    turb = _text(methods.get("turbulence"))
    wall = _text(methods.get("wallTreatment"))
    src = _text(methods.get("turbulenceSource"))
    ref_table = ["| Wielkość | Wartość | Źródło |", "| --- | --- | --- |"]
    for key, label, unit in REF_ROWS:
        ref_table.append(
            f"| {label} | {_plain(_ref_value(pack, key))} {unit} | {_cell(_ref_source(pack, key))} |"
        )
    lines = [
        "## Setup symulacji",
        "",
        f"Fluent: {_text(methods.get('fluentVersion'))}.",
        f"Turbulencja: {turb}. Ściana: {wall}. Źródło: {src}.",
        (
            f"Siatka: {_count(mesh.get('cells'))} komórek, "
            f"min. jakość ortogonalna {_plain(mesh.get('minOrthogonalQuality'))}, "
            f"max. aspect ratio {_plain(mesh.get('maxAspectRatio'))}."
        ),
        *_layers(mesh),
        _wheels(pack),
        f"Wentylator MRF: {_bool_pl(methods.get('mrfFan'), 'jest', 'nie ma')}.",
        "",
        *ref_table,
        "",
    ]
    return "\n".join(lines)


def _parts(pack: dict) -> str:
    groups = ((_kpis(pack).get("components")) or {}).get("groups")
    lines = ["## Siły na części", ""]
    if not isinstance(groups, dict) or not groups:
        lines.append("Sił na częściach nie ma w tej paczce.")
        lines.append("")
        return "\n".join(lines)
    lines.extend([
        "Współczynniki są dla połowy auta, tak jak liczy solver. Udział to procent sumy auta.",
        "",
        "| Część | Cd | Cl | Docisk | Udział oporu | Udział docisku |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for name, rec in groups.items():
        rec = rec or {}
        drag = _pct(rec.get("shareDragPct"))
        down = _pct(rec.get("shareDownforcePct"))
        lines.append(
            "| "
            + " | ".join([
                _cell(PART_NAMES.get(name, _text(name))),
                _coeff(rec.get("Cd")),
                _coeff(rec.get("Cl")),
                _coeff(rec.get("downforceCoeff")),
                BRAK if drag == BRAK else f"{drag}%",
                BRAK if down == BRAK else f"{down}%",
            ])
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _warnings(pack: dict) -> str:
    lines = ["## Ostrzeżenia", ""]
    items = [item.strip() for item in (pack.get("warnings") or []) if isinstance(item, str) and item.strip()]
    if not items:
        lines.append(f"- {BRAK}")
    else:
        lines.extend(f"- {item}" for item in items)
    lines.append("")
    return "\n".join(lines)


def _rules(pack: dict) -> str:
    lines = ["## Zasady dla recenzenta", ""]
    for note in pack.get("notesForAgent") or []:
        if isinstance(note, str) and note.strip():
            lines.append(f"- {note.strip()}")
    lines.extend([
        "- Liczby pochodzą z solvera, nie ze zdjęć.",
        "- To połowa modelu i yaw 0, więc nie wyciągaj wniosków o zakręcie ani o yaw.",
        "- Nie mnoż współczynników przez 2. Razy dwa wolno tylko niutony (kolumna całe auto).",
        "- Porównuj symulacje tylko gdy obie mają werdykt OK.",
        "",
    ])
    return "\n".join(lines)


def _glossary() -> str:
    rows = [
        ("Cd", "współczynnik oporu. Cd = cx z solvera. Większy Cd bardziej hamuje auto."),
        ("Cl", "współczynnik siły pionowej w górę. Ujemny Cl to docisk."),
        ("docisk", "siła aerodynamiczna w dół. Dodatni współczynnik docisku = −Cl."),
        ("L/D", "docisk podzielony przez opór. Większe znaczy więcej docisku na jednostkę oporu."),
        ("balans aero", "procent całego docisku, który stoi na przedniej osi."),
        ("środek parcia", "punkt X, w którym wypadkowa siła aero nie daje momentu."),
        ("y+", "bezwymiarowa wysokość pierwszej komórki przy ścianie. Mówi, czy model ściany pasuje do siatki."),
        ("residual continuity", "błąd równania ciągłości. Mniejszy znaczy, że masa w komórkach lepiej się domyka."),
        ("zbieżność", "czy cx, cz i balans przestały wyraźnie wędrować w ostatnich iteracjach."),
        ("half model", "liczona jest połowa auta, a płaszczyzna symetrii zastępuje drugą połowę."),
    ]
    lines = ["## Słowniczek", ""]
    lines.extend(f"- **{name}** — {text}" for name, text in rows)
    lines.append("")
    return "\n".join(lines)
