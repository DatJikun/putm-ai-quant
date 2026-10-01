"""Comparing cases: numbers, wording, charts and the written files."""

import json

import pytest

from ingest.compare import (
    bar_chart,
    build_document,
    check_matrix,
    compare,
    headline,
    line_chart,
    load_case,
    reading,
    series_loss,
    series_strips,
)


def case(name, cd, df, front, model="k-omega SST", fw=1.0, floor=0.5):
    pack = {
        "_name": name,
        "identity": {"caseId": name, "halfModel": True, "yawDeg": 0, "speedMs": 15.0},
        "methods": {"turbulence": model, "wallTreatment": "w"},
        "mesh": {"cells": 1000000},
        "kpis": {
            "Cd": cd,
            "downforceCoeff": df,
            "LOverD": df / cd,
            "iterations": 100,
            "aeroBalance": {"frontPct": front, "copXM": 0.7},
            "references": {"speedMs": {"value": 15.0}, "rho": {"value": 1.225}, "frontalAreaM2": {"value": 0.5}},
            "components": {"groups": {"fw": {"Cd": 0.2, "downforceCoeff": fw}, "floor": {"Cd": 0.1, "downforceCoeff": floor}}},
        },
        "flowSummary": {"vortexTracks": [{"region": "pod podłogą", "peakCirculationM2s": -2.0, "fromX_m": 0.0, "toX_m": 1.0}]},
    }
    report = {
        "verdict": {"status": "ok", "label": "ok"},
        "checks": [{"title": "Residua", "status": "ok"}],
        "walls": {"strips": {"fw": [{"x_m": -0.75, "downforceCoeff": fw / 2}, {"x_m": -0.65, "downforceCoeff": fw / 2}], "floor": [{"x_m": 0.55, "downforceCoeff": floor}]}},
        "flow": {"stations": [{"x_m": 0.0, "lossIntegralM2": 0.0}, {"x_m": 0.1, "lossIntegralM2": 0.2}]},
    }
    return {"name": name, "pack": pack, "report": report}


def test_headline_converts_to_newtons_for_a_half_model():
    h = headline(case("a", 1.0, 4.0, 50.0))
    q = 0.5 * 1.225 * 225
    assert h["downforceN"] == pytest.approx(2 * 4.0 * q * 0.5)
    assert h["dragN"] == pytest.approx(2 * 1.0 * q * 0.5)


def test_strips_are_summed_over_groups_or_taken_for_one():
    cases = [case("a", 1, 4, 50)]
    total = series_strips(cases)["a"]
    assert total == [(-0.75, 0.5), (-0.65, 0.5), (0.55, 0.5)]
    assert series_strips(cases, "floor")["a"] == [(0.55, 0.5)]
    assert series_strips(cases, "rw") == {}


def test_loss_series_and_check_matrix():
    cases = [case("a", 1, 4, 50), case("b", 1, 4, 50)]
    assert series_loss(cases)["a"] == [(0.0, 0.0), (0.1, 0.2)]
    titles, rows = check_matrix(cases)
    assert titles == ["Residua"] and rows == [["🟢 OK", "🟢 OK"]]


def test_the_reading_names_the_biggest_changes_and_warns_about_different_methods():
    base = case("002", 1.19, 3.68, 68.0, model="k-epsilon", fw=1.6, floor=0.7)
    new = case("003", 1.65, 4.56, 51.0, fw=1.2, floor=1.45)
    sentences = reading([base, new], ["Różni się model turbulencji"])
    text = " ".join(sentences)
    assert "003" in text and "względem 002" in text
    assert "podłoga i dyfuzor" in text  # the largest downforce change
    assert "w stronę tyłu" in text
    assert "Uwaga" in text and "metody" in text


def test_the_document_has_every_section_and_charts_for_every_series():
    cases = [case("a", 1.19, 3.68, 68.0, model="k-epsilon"), case("b", 1.65, 4.56, 51.0)]
    text, charts, raw = build_document(cases)
    for needle in ("## Co to za symulacje", "## Czy to uczciwe porównanie?", "## Najważniejsze liczby", "## Siły na części", "## Wiarygodność każdej symulacji"):
        assert needle in text
    assert "Nie do końca" in text
    assert len(charts) == 6  # downforce bars, drag bars, along x (all, fw, floor), loss
    assert raw["names"] == ["a", "b"] and "Cd" in raw["headline"]["a"]


def test_a_fair_comparison_says_so():
    text, _, raw = build_document([case("a", 1.6, 4.5, 50.0), case("b", 1.7, 4.6, 51.0)])
    assert "Tak: ten sam model" in text and raw["issues"] == []


def test_charts_are_valid_svg_with_every_series_named():
    svg = line_chart({"a": [(0, 0), (1, 2)], "b": [(0, 1), (1, 0.5)]}, "T & <x>", "x", "y")
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "T &amp; &lt;x&gt;" in svg and svg.count("<polyline") == 2
    bars = bar_chart(["fw", "rw"], {"a": [1.0, -0.5], "b": [None, 0.2]}, "B", "y")
    assert bars.count("<rect") == 3 + 2  # three bars plus two legend swatches


def test_compare_writes_markdown_html_and_json(tmp_path):
    for name, cd in (("a", 1.2), ("b", 1.6)):
        folder = tmp_path / name
        folder.mkdir()
        c = case(name, cd, 4.0, 50.0)
        (folder / "aeropack.json").write_text(json.dumps(c["pack"]), encoding="utf-8")
        (folder / "raport.json").write_text(json.dumps(c["report"]), encoding="utf-8")
    result = compare([tmp_path / "a", tmp_path / "b"], tmp_path / "out")
    assert result["names"] == ["a", "b"] and result["charts"] >= 4
    html_text = (tmp_path / "out" / "POROWNANIE.html").read_text(encoding="utf-8")
    assert "<svg" in html_text and "Wykresy" in html_text
    assert (tmp_path / "out" / "POROWNANIE.md").exists() and (tmp_path / "out" / "porownanie.json").exists()


def test_a_folder_without_a_report_is_still_loaded(tmp_path):
    folder = tmp_path / "x"
    folder.mkdir()
    (folder / "aeropack.json").write_text(json.dumps(case("x", 1, 4, 50)["pack"]), encoding="utf-8")
    loaded = load_case(folder, "Etykieta")
    assert loaded["name"] == "Etykieta" and loaded["report"] == {}


def test_one_case_is_not_a_comparison(tmp_path):
    with pytest.raises(ValueError):
        compare([tmp_path], tmp_path / "out")
