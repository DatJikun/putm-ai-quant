"""The two documents and the HTML conversion, on a small made-up report."""

from ingest.documents import _findings, markdown_to_html, render_full, render_short


def _report():
    zone = {
        "group": "fw",
        "faces": 10,
        "areaM2": 1.0,
        "Cd": 0.2,
        "downforceCoeff": 1.0,
        "Cd_pressure": 0.19,
        "Cd_viscous": 0.01,
        "yplus": {"median": 0.5, "p95": 0.9, "max": 2.0, "areaShare": {"le1": 1.0}, "maxAtM": [0, 0, 0]},
        "firstCellHeightM": {"median": 2e-5},
        "reverseFlow": {"areaShare": 0.02, "strips": [{"x_m": -0.75, "areaM2": 0.05, "reversedShare": 0.4}]},
        "F": [1, 0, -1],
        "strips": [{"x_m": -0.75, "Cd": 0.1, "downforceCoeff": 0.5}],
    }
    walls = {
        "zones": {"surface_fw": zone, "domain_ground": {**zone, "group": None}},
        "groups": {
            "fw": {"zones": ["surface_fw"], "Cd": 0.2, "downforceCoeff": 1.0, "Cd_pressure": 0.19, "Cd_viscous": 0.01, "shareDragPct": 40.0, "shareDownforcePct": 60.0},
            "rw": {"zones": [], "Cd": 0.3, "downforceCoeff": -0.1, "Cd_pressure": 0.3, "Cd_viscous": 0.0, "shareDragPct": 60.0, "shareDownforcePct": 40.0},
        },
        "vehicle": {"Cd": 0.5, "downforceCoeff": 0.9},
        "checksum": {"vehicleCd": 0.5, "vehicleDownforce": 0.9, "monitorCd": 0.5, "monitorDownforce": 0.9, "cdRelErr": 0.0, "downforceRelErr": 0.0, "ok": True},
        "strips": {"fw": [{"x_m": -0.75, "Cd": 0.1, "downforceCoeff": 0.5}]},
        "groupYplus": {"all": {"areaM2": 1.0, "shares": {"le1": 1.0}, "max": 2.0, "median": 0.5}, "fw": {"areaM2": 1.0, "shares": {"le1": 1.0}, "max": 2.0, "median": 0.5}},
    }
    flow = {
        "stations": [
            {"x_m": 0.0, "cells": 100, "lossIntegralM2": 0.1, "lossAreaM2": 0.2, "minCpt": 0.5, "reverseFlowAreaM2": 0.0, "minU_ms": 5.0, "wheels": {}, "vortices": [{"y_m": -0.5, "z_m": 0.3, "circulationM2s": 1.5, "turn": "przeciwnie do ruchu wskazówek (patrząc z przodu)", "coreRadiusM": 0.04, "swirlSpeedMs": 6.0, "minCpt": 0.2, "region": "pod podłogą"}]}
        ],
        "vortexTracks": [{"turn": "przeciwnie do ruchu wskazówek", "fromX_m": 0.0, "toX_m": 0.2, "strongestAtX_m": 0.1, "peakCirculationM2s": 1.5, "region": "pod podłogą", "start": {"y_m": -0.5, "z_m": 0.3}, "end": {"y_m": -0.5, "z_m": 0.3}, "points": [{"x_m": 0.0, "y_m": -0.5, "z_m": 0.3, "circulationM2s": 1.5}]}],
    }
    pack = {
        "identity": {"caseId": "TEST", "halfModel": True, "yawDeg": 0},
        "kpis": {"Cd": 0.5, "downforceCoeff": 0.9, "LOverD": 1.8, "aeroBalance": {"frontPct": 55.0, "rearPct": 45.0, "copXM": 0.7}, "iterations": 100, "references": {"speedMs": {"value": 15.0, "source": "case"}, "rho": {"value": 1.225, "source": "case"}, "mu": {"value": 1.8e-5, "source": "case"}, "frontalAreaM2": {"value": 0.5, "source": "case"}}},
        "mesh": {"cells": 1000000},
        "methods": {"turbulence": "k-omega SST", "wallTreatment": "k-omega (bez funkcji ściany)"},
        "images": {"total": 0, "byAxis": {}},
        "flowSummary": {"lossGrowth": [{"fromX_m": 0.0, "toX_m": 0.1, "growthM2": 0.1, "dragMostlyFrom": "tylne skrzydło"}], "vortexTracks": flow["vortexTracks"], "reverseFlow": None},
        "warnings": ["coś"],
    }
    return {
        "generatedAt": "2026-10-01T10:00:00+00:00",
        "caseId": "TEST",
        "verdict": {"status": "uwaga", "label": "Wyniki orientacyjne, są zastrzeżenia", "bad": [], "warn": ["Residua"], "missing": []},
        "checks": [{"id": "residua", "title": "Residua poniżej 1e-3", "status": "uwaga", "value": "5e-3", "detail": "Powyżej limitu: continuity 5.3e-03. Nie spadają."}],
        "missing": ["Brak journala .jou: nic."],
        "conservation": {"residuals": None, "massBalance": None, "missing": []},
        "walls": walls,
        "flow": flow,
        "pack": pack,
    }


def test_the_summary_is_short_and_has_the_headline_parts():
    text = render_short(_report())
    assert text.startswith("# TEST: skrót")
    for needle in ("## Na co uważać", "## Najważniejsze liczby", "## Skąd się biorą siły", "## Co robi bolid", "## Czego brakuje", "PELNY.md"):
        assert needle in text
    assert len(text.splitlines()) < 70
    assert "Docisk całego auta przy 15 m/s" in text


def test_the_full_report_contains_every_appendix():
    text = render_full(_report())
    for letter in "ABCDEFGH":
        assert f"## Dodatek {letter}." in text
    assert "surface_fw" in text and "domain_ground" in text
    assert "Każdy znaleziony wir" in text and "pod podłogą" in text
    assert len(text) > len(render_short(_report())) * 3


def test_findings_name_the_biggest_contributors_and_parts_that_work_backwards():
    found = " ".join(_findings(_report()))
    assert "przednie skrzydło" in found and "60%" in found
    assert "Zmniejszają docisk" in found and "tylne skrzydło" in found
    assert "Oderwanie na powierzchni" in found
    assert "Najsilniejszy wir" in found


def test_markdown_tables_headings_lists_and_bold_become_html():
    page = markdown_to_html("# Tytuł\n\n| a | b |\n| --- | --- |\n| 1 | **x** |\n\n- punkt `kod`\n\nzwykły <tekst>", "T")
    assert "<h1>Tytuł</h1>" in page
    assert "<th>a</th>" in page and "<td><b>x</b></td>" in page
    assert "<li>punkt <code>kod</code></li>" in page
    assert "&lt;tekst&gt;" in page
    assert page.startswith("<!doctype html>") and "<title>T</title>" in page
