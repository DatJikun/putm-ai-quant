"""The explanation engine on two made-up cases whose differences are known by construction."""

import pytest

from ingest.why import (
    along_x,
    centre_of_pressure,
    explain,
    flow,
    geometry,
    parts,
    render,
    sentences,
    totals,
    trust,
)


def meta(name, floor_df, fw_df, *, model="k-omega SST", floor_x=0.6, settled=True, floor_box=None, tracks=None, rev=0.02):
    groups = {
        "floor": {"downforceCoeff": floor_df, "Cd": 0.1 + 0.05 * floor_df},
        "fw": {"downforceCoeff": fw_df, "Cd": 0.2},
        "wheels": {"downforceCoeff": -0.1, "Cd": 0.15},
    }
    strips = {
        "floor": [{"x_m": floor_x, "downforceCoeff": floor_df}],
        "fw": [{"x_m": -0.7, "downforceCoeff": fw_df}],
        "wheels": [{"x_m": 0.0, "downforceCoeff": -0.1}],
    }
    zones = {
        "surface_ut": {"group": "floor", "bboxM": floor_box or [[0.2, -0.6, 0.0], [1.2, 0.0, 0.1]], "reverseFlow": {"areaShare": rev, "horizontalAreaM2": 1.0}},
        "surface_fw": {"group": "fw", "bboxM": [[-0.9, -0.7, 0.0], [-0.3, 0.0, 0.3]], "reverseFlow": {"areaShare": 0.01, "horizontalAreaM2": 1.0}},
    }
    cd = sum(g["Cd"] for g in groups.values())
    df = sum(g["downforceCoeff"] for g in groups.values())
    return {
        "caseId": name,
        "paczka": {
            "identity": {"caseId": name, "halfModel": True, "speedMs": 15.0},
            "methods": {"turbulence": model, "wallTreatment": "w"},
            "kpis": {"Cd": cd, "downforceCoeff": df, "LOverD": df / cd, "aeroBalance": {"frontPct": 50.0, "copXM": 0.5}, "convergence": {"settled": settled}, "references": {"frontalAreaM2": {"value": 0.5}}},
            "flowSummary": {"vortexTracks": tracks if tracks is not None else [{"region": "pod podłogą", "peakCirculationM2s": -2.0, "fromX_m": 0.0, "toX_m": 1.0}]},
        },
        "raport": {
            "walls": {"groups": groups, "strips": strips, "zones": zones},
            "flow": {"stations": [{"x_m": 0.0, "lossIntegralM2": 0.0}, {"x_m": 0.1, "lossIntegralM2": 0.1}, {"x_m": 0.2, "lossIntegralM2": 0.1 + 0.2 * floor_df}]},
        },
    }


A = meta("A", 0.5, 1.5)
B = meta("B", 1.25, 1.1)


def test_totals_carry_old_new_change_and_percent():
    t = totals(A, B)
    assert t["downforce"]["a"] == pytest.approx(1.9) and t["downforce"]["b"] == pytest.approx(2.25)
    assert t["downforce"]["delta"] == pytest.approx(0.35)
    assert t["downforce"]["pct"] == pytest.approx(100 * 0.35 / 1.9)


def test_the_parts_add_up_to_the_whole_change():
    rows = parts(A, B)
    assert sum(r["d_df"] for r in rows) == pytest.approx(totals(A, B)["downforce"]["delta"])
    assert sum(r["udzial_df_pct"] for r in rows) == pytest.approx(100.0)
    assert rows[0]["czesc"] == "floor" and rows[0]["d_df"] == pytest.approx(0.75)
    assert rows[1]["czesc"] == "fw" and rows[1]["udzial_df_pct"] < 0  # it worked against the change


def test_the_strips_show_where_along_the_car_a_part_changed():
    rows = along_x(A, B, ["floor"])["floor"]
    assert rows[0]["x_m"] == 0.6 and rows[0]["delta"] == pytest.approx(0.75)
    shifted = meta("S", 1.25, 1.1, floor_x=1.0)
    moved = along_x(A, shifted, ["floor"])["floor"]
    assert {r["x_m"] for r in moved} == {0.6, 1.0}


def test_the_centre_of_pressure_shift_is_split_exactly_by_part():
    cop = centre_of_pressure(A, B)
    assert sum(w["wklad_m"] for w in cop["wklady"]) == pytest.approx(cop["delta"])
    assert cop["delta"] == pytest.approx(cop["b"] - cop["a"])
    assert cop["wklady"][0]["czesc"] in ("floor", "fw")


def test_no_downforce_means_no_centre_of_pressure():
    empty = meta("E", 0.0, 0.0)
    empty["raport"]["walls"]["strips"] = {"floor": [{"x_m": 0.6, "downforceCoeff": 0.0}]}
    assert centre_of_pressure(A, empty) is None


def test_geometry_lists_only_moves_of_a_centimetre_or_more():
    longer = meta("L", 1.25, 1.1, floor_box=[[0.2, -0.6, 0.0], [1.4, 0.0, 0.1]])
    rows = geometry(A, longer)
    assert len(rows) == 1 and rows[0]["czesc"] == "floor" and rows[0]["wymiar"] == "x do"
    assert rows[0]["delta"] == pytest.approx(0.2)
    assert geometry(A, A) == []


def test_flow_changes_vortices_losses_and_separation():
    newer = meta("N", 1.25, 1.1, rev=0.10, tracks=[{"region": "ślad za kołem", "peakCirculationM2s": 3.0, "fromX_m": 1.0, "toX_m": 2.0}])
    f = flow(A, newer)
    assert [v["region"] for v in f["wiry"]["nowe"]] == ["ślad za kołem"]
    assert [v["region"] for v in f["wiry"]["znikniete"]] == ["pod podłogą"]
    floor = next(r for r in f["oderwania"] if r["czesc"] == "floor")
    assert floor["delta_pp"] == pytest.approx(8.0)
    assert f["strata"]["za_autem"]["x_m"] == 0.2


def test_a_vortex_in_the_same_region_is_matched_not_reported_as_new():
    f = flow(A, meta("N", 1.25, 1.1, tracks=[{"region": "pod podłogą", "peakCirculationM2s": 4.0, "fromX_m": 0.1, "toX_m": 1.0}]))
    assert f["wiry"]["nowe"] == [] and f["wiry"]["znikniete"] == []
    assert f["wiry"]["wspolne"] == [{"region": "pod podłogą", "a": 2.0, "b": 4.0}]


def test_trust_is_low_when_the_method_differs_and_high_when_only_the_car_does():
    assert trust(A, B)["poziom"] == "wysoka"
    other = meta("K", 1.25, 1.1, model="Realizable k-epsilon")
    low = trust(A, other)
    assert low["poziom"] == "niska" and low["metoda_rozni_sie"] is True
    unsettled = trust(A, meta("U", 1.25, 1.1, settled=False))
    assert unsettled["poziom"] == "srednia" and any("nie ustabilizowały" in p for p in unsettled["powody"])


def test_the_sentences_name_the_main_part_and_say_how_far_to_trust_it():
    text = " ".join(explain(A, B)["wnioski"])
    assert "podłoga i dyfuzor" in text and "+0.75" in text and "przednie skrzydło" in text
    assert text.index("podłoga i dyfuzor") < text.index("przednie skrzydło")  # the main contributor is named first
    assert "Porównanie jest uczciwe" in text
    low = " ".join(explain(A, meta("K", 1.25, 1.1, model="Realizable k-epsilon"))["wnioski"])
    assert "częściowo różnicą metody" in low


def test_the_rendered_page_has_every_section_and_the_numbers_of_the_parts():
    page = render(explain(A, B))
    for header in ("## W skrócie", "## Całość", "## Które części", "## Gdzie wzdłuż auta", "## Środek docisku", "## Co zmieniło się w przepływie", "## Ile temu ufać"):
        assert header in page
    assert "| podłoga i dyfuzor | 0.500 | 1.250 | +0.750 | 214% |" in page
    assert "Poza geometrią nic się nie różni." in page


def test_explain_survives_a_meta_without_flow_or_zones():
    bare = {"caseId": "Z", "paczka": {"kpis": {"Cd": 1.0, "downforceCoeff": 3.0}}, "raport": {}}
    result = explain(bare, bare)
    assert result["czesci"] == [] and result["srodek_parcia"] is None and result["geometria"] == []
    assert isinstance(sentences(result), list)
