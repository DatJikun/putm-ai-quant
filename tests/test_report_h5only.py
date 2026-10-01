"""The report without logs: what is measured from the files stands in for what the logs would say."""

from ingest.dat_monitors import monitor_samples, parse_scheme, to_monitors
from ingest.pack import _proxy_convergence
from ingest.report import (
    NONE,
    OK,
    WARN,
    check_boundary_layers,
    check_mesh_quality,
    missing_data,
)


def test_scheme_reader_handles_nested_lists_strings_and_numbers():
    tree = parse_scheme('(a (1. 2.5) ("name" (3.) x) ())')
    assert tree == ["a", [1.0, 2.5], ["name", [3.0], "x"], []]


def _table(first, last, n=100):
    middle = " ".join(str(first + (last - first) * i / (n - 1)) for i in range(1, n - 1))
    return f"{first} {middle} {last}"


def _data_variables():
    return (
        "(37 (stuff (monitor/average-over-state ((\"cz\" (1. 2.) (0. 860. ("
        + _table(4.5, 4.6)
        + "))) (\"cz_all\" (1. 2.) (0. 860. (4.0) (5.0))))) other))"
    )


def test_monitor_tables_are_found_inside_the_data_variables_text():
    samples = monitor_samples(_data_variables())
    assert set(samples) == {"cz", "cz_all"}
    assert len(samples["cz"]["series"][0]) == 100
    assert samples["cz"]["to"] == 860.0


def test_only_the_two_ends_of_a_table_are_used_and_one_number_tables_are_skipped():
    monitors = to_monitors(monitor_samples(_data_variables()))["monitors"]
    assert set(monitors) == {"cz"}
    cz = monitors["cz"]
    assert cz["instantaneous"] == 4.5 and cz["averaged"] == 4.6
    assert cz["stability"]["proxy"] is True
    assert round(cz["stability"]["driftPct"], 2) == round(100 * (4.5 - 4.6) / 4.6, 2)


def test_no_monitor_table_gives_no_monitors():
    assert monitor_samples("(37 (nothing here))") == {}


def _stab(gap):
    return {"proxy": True, "driftPct": gap}


def test_proxy_convergence_is_settled_when_instantaneous_and_average_agree():
    out = _proxy_convergence({"reasons": []}, {"cx": _stab(0.01), "cz": _stab(-0.2)})
    assert out["settled"] is True and out["windowIterations"] is None


def test_proxy_convergence_flags_a_gap_above_the_limit():
    out = _proxy_convergence({"reasons": []}, {"cx": _stab(0.01), "cz": _stab(-1.2)})
    assert out["settled"] is False
    assert "cz" in out["reasons"][0] and "-1.20%" in out["reasons"][0]


def _approx(bad, poor):
    return {"mesh": {"cells": 1000, "orthogonalQualityApprox": {"facesBelow": {"0.01": bad, "0.1": poor}, "faces": 5000, "worstAtM": [1.0, 2.0, 3.0]}}}


def test_mesh_quality_from_geometry_is_marked_as_an_approximation():
    clean = check_mesh_quality(_approx(0, 3))
    assert clean["status"] == OK and "Przybliżenie z geometrii" in clean["detail"]
    poor = check_mesh_quality(_approx(9, 1000))
    assert poor["status"] == WARN and "x=1.0" in poor["detail"]


def test_mesh_quality_without_log_or_measurement_is_missing():
    assert check_mesh_quality({"mesh": {}})["status"] == NONE


def _walls(height):
    zone = {"group": "fw", "areaM2": 1.0, "firstCellHeightM": {"median": height}}
    return {"zones": {"surface_fw": zone}}


def test_first_cell_is_taken_from_the_mesh_when_there_is_no_recipe():
    result = check_boundary_layers({"mesh": {}}, _walls(2e-5))
    assert result["status"] == OK and "20 µm" in result["value"]
    assert check_boundary_layers({"mesh": {}}, None)["status"] == NONE


def test_recipe_and_measurement_are_both_shown_when_both_exist():
    pack = {"mesh": {"boundaryLayers": {"staleControls": ["uniform_1"], "boundaryLayers": []}}}
    result = check_boundary_layers(pack, _walls(2e-5))
    assert result["status"] == WARN and "20 µm" in result["detail"]


def test_missing_list_does_not_ask_for_logs_that_files_replace():
    pack = {"kpis": {}, "mesh": {"orthogonalQualityApprox": {"facesBelow": {}}}, "methods": {"turbulence": "k-omega SST"}, "files": {"cas": ["a"], "dat": ["b"], "transcripts": ["t"]}, "monitors": {"monitors": {"cx": {}}}, "images": {"total": 1}}
    text = " ".join(missing_data(pack, {"missing": []}, _walls(2e-5)))
    assert "warstw" not in text and "jakości siatki" not in text
