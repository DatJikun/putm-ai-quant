"""Credibility checks: each rule on small inputs, and the score arithmetic."""

import json

import pytest

from ingest.credibility import (
    BAD,
    NONE,
    OK,
    SOURCES,
    WARN,
    assess,
    car_extent,
    check_balance,
    check_coefficient_range,
    check_domain,
    check_ground,
    check_measurement,
    check_mesh_independence,
    check_model,
    check_oderwania,
    check_sign,
    check_wheel_share,
    check_wheels,
    load_measurements,
    render,
    summarize,
)


def _zone(group=None, wall=None, bbox=None, rev=None, area=1.0):
    z = {"group": group, "areaM2": area}
    if wall:
        z["wallSpeedMs"] = wall
    if bbox:
        z["bboxM"] = bbox
    if rev is not None:
        z["reverseFlow"] = {"areaShare": rev, "horizontalAreaM2": area}
    return z


def test_a_moving_ground_equal_to_the_stream_is_ok_and_a_still_one_is_bad():
    ok = {"zones": {"domain_ground": _zone(wall={"median": 15.0, "max": 15.0})}}
    assert check_ground(ok, 15.0)["status"] == OK
    still = {"zones": {"domain_ground": _zone(wall={"median": 0.0, "max": 0.0})}}
    assert check_ground(still, 15.0)["status"] == BAD
    slow = {"zones": {"domain_ground": _zone(wall={"median": 12.0, "max": 12.0})}}
    assert check_ground(slow, 15.0)["status"] == WARN
    assert check_ground(None, 15.0)["status"] == NONE


def test_wheels_must_turn_at_the_driving_speed():
    def walls(top):
        return {"zones": {"surface_front_wheel-rotary": _zone(wall={"median": top / 2, "max": top})}}

    assert check_wheels(walls(15.0), 15.0)["status"] == OK
    assert check_wheels(walls(9.0), 15.0)["status"] == BAD
    assert check_wheels(walls(13.0), 15.0)["status"] == WARN
    assert check_wheels({"zones": {"surface_mono": _zone()}}, 15.0)["status"] == NONE


def test_the_domain_is_checked_in_car_lengths_and_blockage():
    car = {"zones": {"surface_mono": _zone(group="body", bbox=[[-1.0, -0.7, 0.0], [2.0, 0.0, 1.2]])}}
    big = {"minM": [-9.0, -8.0, 0.0], "maxM": [20.0, 0.0, 6.0]}
    result = check_domain(big, car_extent(car), 0.49, True)
    assert result["status"] == OK and "L przed" in result["value"]
    small = {"minM": [-3.0, -1.5, 0.0], "maxM": [5.0, 0.0, 2.0]}
    bad = check_domain(small, car_extent(car), 0.49, True)
    assert bad["status"] in (WARN, BAD) and "za mała" in bad["detail"]
    assert check_domain(None, None, None, True)["status"] == NONE


def test_the_car_extent_is_the_box_of_the_vehicle_zones_only():
    walls = {"zones": {"a": _zone(group="fw", bbox=[[0, 0, 0], [1, 1, 1]]), "b": _zone(group="rw", bbox=[[2, -1, 0], [3, 0, 2]]), "domain_ground": _zone(bbox=[[-9, -9, 0], [9, 9, 0]])}}
    assert car_extent(walls) == {"minM": [0.0, -1.0, 0.0], "maxM": [3.0, 1.0, 2.0]}
    assert car_extent({"zones": {}}) is None


def test_the_turbulence_model_is_judged_for_wing_separation():
    assert check_model("k-omega SST", None)["status"] == OK
    assert check_model("Realizable k-epsilon", "Enhanced Wall Treatment")["status"] == WARN
    assert check_model(None, None)["status"] == NONE


def test_separation_share_grades_the_confidence_in_rans():
    low = {"zones": {"surface_fw": _zone(group="fw", rev=0.01)}}
    mid = {"zones": {"surface_fw": _zone(group="fw", rev=0.06)}}
    high = {"zones": {"surface_fw": _zone(group="fw", rev=0.2)}}
    assert [check_oderwania(w, "k-omega SST")["status"] for w in (low, mid, high)] == [OK, WARN, BAD]
    assert check_oderwania({"zones": {}}, "")["status"] == NONE


def test_coefficients_near_the_literature_anchor_are_ok():
    assert check_coefficient_range({"Cd": 1.5, "downforceCoeff": 3.6})["status"] == OK
    assert check_coefficient_range({"Cd": 0.4, "downforceCoeff": 3.6})["status"] == WARN
    assert check_coefficient_range({"Cd": 1.5, "downforceCoeff": 9.0})["status"] == WARN
    assert check_coefficient_range({})["status"] == NONE


def test_a_low_wheel_share_is_flagged_against_katz():
    assert check_wheel_share({"groups": {"wheels": {"shareDragPct": 38.0}}})["status"] == OK
    low = check_wheel_share({"groups": {"wheels": {"shareDragPct": 10.0}}})
    assert low["status"] == WARN and "40%" in low["detail"]
    assert check_wheel_share({"groups": {}})["status"] == NONE


def test_balance_needs_the_weight_distribution_to_be_judged():
    kpis = {"aeroBalance": {"frontPct": 50.0}}
    assert check_balance(kpis, None)["status"] == NONE
    assert check_balance(kpis, 48.0)["status"] == OK
    assert check_balance(kpis, 40.0)["status"] == WARN
    assert check_balance(kpis, 20.0)["status"] == BAD


def test_the_sign_check_catches_lift_and_unverified_vectors():
    assert check_sign({"Cd": 1.5, "downforceCoeff": 3.0, "forceVectorVerified": True})["status"] == OK
    assert check_sign({"Cd": 1.5, "downforceCoeff": -1.0, "forceVectorVerified": True})["status"] == BAD
    assert check_sign({"Cd": 1.5, "downforceCoeff": 3.0, "forceVectorVerified": False})["status"] == WARN


def test_mesh_independence_uses_gci_when_there_are_three_meshes():
    study = {"quantities": [{"id": "Cd", "gciFinePct": 1.2}, {"id": "downforce", "gciFinePct": 2.5}]}
    assert check_mesh_independence(study)["status"] == OK
    assert check_mesh_independence({"quantities": [{"id": "Cd", "gciFinePct": 7.0}]})["status"] == BAD
    two = {"quantities": [{"id": "Cd", "relativeDifferencePct": [2.0]}]}
    assert check_mesh_independence(two)["status"] == WARN
    none = check_mesh_independence(None)
    assert none["status"] == NONE and "największa niewiadoma" in none["detail"]


def test_a_measurement_is_compared_with_the_full_car_area():
    kpis = {"Cd": 1.0, "downforceCoeff": 4.0}
    refs = {"aref_m2": 0.5, "half": True}
    ok = check_measurement(kpis, {"CdA_m2": 1.0, "ClA_m2": 4.1, "zrodlo": "tunel"}, refs)
    assert ok["status"] == OK and "tunel" in ok["detail"]
    off = check_measurement(kpis, {"CdA_m2": 1.5}, refs)
    assert off["status"] == BAD and "+" not in off["detail"].split("symulacja")[0]
    none = check_measurement(kpis, None, refs)
    assert none["status"] == NONE and "pomiary.json" in none["detail"]


def _item(cid, status, weight):
    return {"id": cid, "title": cid, "status": status, "weight": weight, "value": "", "detail": "", "sources": []}


def test_score_counts_only_checks_that_could_be_made():
    items = [_item("residua", OK, 8), _item("yplus", WARN, 10), _item("domena", NONE, 5), _item("pomiar", NONE, 12)]
    result = summarize(items)
    assert result["score"] == round(100 * (8 + 5) / 18)
    assert result["coverage"] == round(100 * 18 / 23)
    assert result["unknown"] == ["domena", "pomiar"]


def test_a_measurement_adds_its_weight_only_when_given():
    base = [_item("residua", OK, 8)]
    assert summarize(base + [_item("pomiar", NONE, 12)])["coverage"] == 100
    with_measure = summarize(base + [_item("pomiar", BAD, 12)])
    assert with_measure["score"] == round(100 * 8 / 20)


def test_bad_checks_cap_the_label():
    items = [_item("residua", OK, 80), _item("yplus", BAD, 20)]
    assert summarize(items)["label"] == "Umiarkowana wiarygodność"
    assert summarize([_item("residua", BAD, 10), _item("yplus", WARN, 10)])["label"] == "Niska wiarygodność"
    assert summarize([_item("residua", NONE, 10)])["label"] == "Nie da się ocenić"
    assert summarize([_item("residua", OK, 80), _item("yplus", OK, 20)])["label"] == "Wysoka wiarygodność"


def test_the_rendered_page_lists_scores_checks_and_only_the_sources_used():
    items = [
        {**_item("yplus", OK, 10), "title": "y+", "sources": ["menter"], "value": "0.5", "detail": "ok"},
        {**_item("domena", NONE, 5), "title": "Domena", "sources": ["domain"], "detail": "brak"},
    ]
    text = render(summarize(items), "X")
    assert "# Wiarygodność symulacji: X" in text and "100 na 100" in text
    assert "## Czego nie dało się sprawdzić" in text and "Domena" in text
    assert "**menter**" in text and "**katz**" not in text
    assert "nie jest dowód zgodności z rzeczywistością" in text


def test_every_source_has_a_citation_and_a_link():
    for key, (text, url) in SOURCES.items():
        assert len(text) > 40 and url.startswith("https://"), key


def test_assess_runs_on_a_minimal_report():
    report = {
        "pack": {"identity": {"halfModel": True}, "kpis": {"Cd": 1.5, "downforceCoeff": 3.6, "forceVectorVerified": True, "references": {"speedMs": {"value": 15.0}, "frontalAreaM2": {"value": 0.5}}}, "methods": {"turbulence": "k-omega SST"}},
        "walls": None,
        "checks": [],
    }
    result = assess(report)
    ids = {c["id"] for c in result["checks"]}
    assert {"residua", "yplus", "podloze", "domena", "pomiar", "model"} <= ids
    assert result["score"] is not None and result["coverage"] < 100


def test_measurements_are_read_from_the_case_folder(tmp_path):
    assert load_measurements(tmp_path) is None
    (tmp_path / "pomiary.json").write_text(json.dumps({"CdA_m2": 1.4, "przod_masa_pct": 47}), encoding="utf-8")
    assert load_measurements(tmp_path)["przod_masa_pct"] == 47
