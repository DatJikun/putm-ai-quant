"""Questions to a meta pack: each tool, the router, and the safety of the second pack's name."""

import json

import numpy as np
import pytest

from ingest import metapack as mp
from ingest.ask import answer
from ingest.meta_ask import credibility, explain_change, findings, other_pack, question, station, wall_value
from tests.test_why import meta as case_meta


def make_pack(root, name, meta_doc, with_maps=False):
    folder = root / name
    (folder / "meta").mkdir(parents=True)
    meta_doc = dict(meta_doc)
    meta_doc["wnioski"] = [
        {"id": "a", "waga": "wysoka", "tekst": "pierwszy", "dowod": "x"},
        {"id": "b", "waga": "srednia", "tekst": "drugi", "dowod": "y"},
        {"id": "c", "waga": "info", "tekst": "trzeci", "dowod": "z"},
    ]
    meta_doc["werdykt"] = {"label": "Wyniki orientacyjne"}
    meta_doc["wiarygodnosc"] = {"score": 70, "coverage": 80, "label": "Umiarkowana wiarygodność", "byCategory": {"Siatka": 60}, "unknown": ["pomiar"], "checks": [{"title": "y+", "weight": 10, "status": "ok", "value": "0.5", "detail": "ok", "sources": ["menter"]}]}
    meta_doc["raport"]["flow"]["stations"] = [{"x_m": 0.0, "lossIntegralM2": 0.0, "vortices": []}, {"x_m": 1.0, "lossIntegralM2": 0.4, "lossAreaM2": 0.6, "minCpt": 0.2, "reverseFlowAreaM2": 0.01, "wheels": {}, "vortices": [{"y_m": -0.5}]}]
    (folder / "meta" / "meta.json").write_text(json.dumps(meta_doc), encoding="utf-8")
    if with_maps:
        xyz = np.array([[0.0, -0.5, 0.1], [1.0, -0.3, 0.2], [2.0, -0.1, 0.3]])
        faces = {"names": ["surface_fw"], "xyz": xyz, "zone": np.zeros(3, dtype=np.uint8), "cp": np.array([-1.0, -0.5, 0.2]), "wss": np.array([1.0, 2.0, 3.0]), "yplus": np.array([0.4, 0.5, 0.6]), "rev": np.array([0.0, 1.0, 0.0])}
        mp.write_surface_files(folder / "meta", faces)
    return folder


@pytest.fixture
def packs(tmp_path):
    a = make_pack(tmp_path, "A", case_meta("A", 0.5, 1.5), with_maps=True)
    b = make_pack(tmp_path, "B", case_meta("B", 1.25, 1.1))
    return tmp_path, a, b


def test_findings_are_limited_and_can_be_filtered_by_weight(packs):
    _, a, _ = packs
    assert [f["id"] for f in findings(a, limit=2)["wnioski"]] == ["a", "b"]
    assert findings(a, limit=5)["razem"] == 3
    assert [f["id"] for f in findings(a, weight="info")["wnioski"]] == ["c"]
    with pytest.raises(ValueError):
        findings(a, weight="pilne")


def test_credibility_returns_the_grade_the_checks_and_the_unknowns(packs):
    out = credibility(packs[1])
    assert out["ocena"] == 70 and out["pokrycie_pct"] == 80
    assert out["sprawdzenia"][0]["zrodla"] == ["menter"] and out["nie_sprawdzono"] == ["pomiar"]


def test_the_nearest_station_is_returned(packs):
    s = station(packs[1], 0.8)
    assert s["x_m"] == 1.0 and s["strata_m2"] == 0.4 and len(s["wiry"]) == 1
    assert station(packs[1], -3.0)["x_m"] == 0.0


def test_a_wall_point_returns_the_nearest_voxel_values(packs):
    v = wall_value(packs[1], 1.0, -0.3, 0.2, "1cm")
    assert v["strefa"] == "surface_fw" and v["cp"] == pytest.approx(-0.5, abs=1e-2)
    assert v["tarcie_Pa"] == pytest.approx(2.0, abs=1e-2) and v["cofniety_przeplyw_pct"] == 100
    assert v["odleglosc_m"] < 0.01


def test_the_second_pack_is_found_by_name_or_as_the_only_other_one(packs):
    root, a, b = packs
    assert other_pack(a, "B") == b
    assert other_pack(a, None) == b


def test_a_second_pack_name_cannot_leave_the_packs_folder(packs):
    root, a, _ = packs
    for bad in ("../x", "..", "a/b", "A\\B", ".", "x y"):
        with pytest.raises(ValueError):
            other_pack(a, bad)
    with pytest.raises(FileNotFoundError):
        other_pack(a, "nie-ma")


def test_without_a_name_and_with_several_candidates_the_choice_is_left_to_the_asker(packs):
    root, a, _ = packs
    make_pack(root, "C", case_meta("C", 1.0, 1.0))
    with pytest.raises(ValueError, match="podaj `other`"):
        other_pack(a, None)


def test_explain_change_takes_the_named_pack_as_the_reference(packs):
    _, a, b = packs
    result = explain_change(b, "A")
    assert result["a"] == "A" and result["b"] == "B"
    assert result["czesci"][0]["czesc"] == "floor"


@pytest.mark.parametrize(
    "text, tool",
    [
        ("Dlaczego docisk jest inny niż w poprzedniej wersji?", "explain_change"),
        ("czemu spadł opór", "explain_change"),
        ("Czy mogę ufać tej symulacji?", "get_credibility"),
        ("jaka jest wiarygodność", "get_credibility"),
        ("co dzieje się na stacji x = 1,0", "get_station"),
        ("jakie wiry są w przekroju 0.5 m", "get_station"),
        ("co jest najważniejsze", "get_findings"),
    ],
)
def test_the_question_router_picks_the_tool_and_names_it(packs, text, tool):
    out = question(packs[1], text, other="B")
    assert out["narzedzie"] == tool and out["odpowiedz"]


def test_a_decimal_comma_in_the_question_is_read_as_a_number(packs):
    out = question(packs[1], "stacja x = 1,0", None)
    assert out["odpowiedz"]["zadane_x_m"] == 1.0


def test_the_shared_answer_function_routes_the_new_tools(packs):
    _, a, _ = packs
    assert answer(a, "get_findings", {"limit": 1})["wnioski"][0]["id"] == "a"
    assert answer(a, "get_station", {"x": 0.9})["x_m"] == 1.0
    assert answer(a, "question", {"text": "ufać?"})["narzedzie"] == "get_credibility"
    assert answer(a, "explain_change", {"other": "B"})["b"] == "A"
    with pytest.raises(ValueError, match="x musi być liczbą"):
        answer(a, "get_station", {"x": "abc"})
    with pytest.raises(ValueError, match="x musi być liczbą"):
        answer(a, "get_station", {"x": float("nan")})


def test_a_pack_without_a_meta_pack_says_how_to_make_one(tmp_path):
    (tmp_path / "P").mkdir()
    with pytest.raises(FileNotFoundError, match="python -m ingest meta"):
        findings(tmp_path / "P")
