"""Grid convergence on made-up packs. The numbers follow f = f_exact + C h^p."""

import pytest

from ingest.mesh_study import cells_of, differences, richardson, study


def pack(name, cells, cd, downforce=4.0, **over):
    data = {
        "_name": name,
        "identity": {"halfModel": True, "yawDeg": 0, "speedMs": 15.0},
        "methods": {"turbulence": "k-omega SST", "wallTreatment": "k-omega (bez funkcji ściany)"},
        "mesh": {"cells": cells},
        "kpis": {
            "Cd": cd,
            "downforceCoeff": downforce,
            "aeroBalance": {"frontPct": 50.0, "copXM": 0.75},
            "references": {"frontalAreaM2": {"value": 0.49}},
            "convergence": {"settled": True},
        },
    }
    for key, value in over.items():
        section, field = key.split("__")
        data[section][field] = value
    return data


def series(p=2.0, exact=1.5, c=0.4, h=(1.0, 1.5, 2.25)):
    return [exact + c * x**p for x in h]


def test_the_order_of_convergence_is_recovered():
    fine, medium, coarse = series(p=2.0)
    result = richardson(fine, medium, coarse, 1.5, 1.5)
    assert result["kind"] == "zbieżna"
    assert result["order"] == pytest.approx(2.0, abs=0.01)
    assert result["extrapolated"] == pytest.approx(1.5, abs=1e-6)
    assert result["inAsymptoticRange"] is True


def test_gci_matches_the_roache_formula():
    fine, medium, coarse = series(p=2.0)
    result = richardson(fine, medium, coarse, 1.5, 1.5)
    expected = 1.25 * abs((medium - fine) / fine) / (1.5**2 - 1) * 100
    assert result["gciFinePct"] == pytest.approx(expected, abs=0.001)


def test_a_non_monotone_series_has_no_order():
    result = richardson(1.0, 1.2, 1.1, 1.5, 1.5)
    assert result["kind"] == "oscylacyjna lub rozbieżna"
    assert result["order"] is None and result["gciFinePct"] is None


def test_identical_solutions_are_mesh_independent():
    result = richardson(1.0, 1.0, 1.0, 1.5, 1.5)
    assert result["kind"] == "niezależne od siatki"
    assert result["gciFinePct"] == 0.0


def test_uneven_refinement_still_gives_the_right_order():
    sizes = (1.0, 1.4, 2.4)
    fine, medium, coarse = [1.5 + 0.4 * h**2.0 for h in sizes]
    result = richardson(fine, medium, coarse, sizes[1] / sizes[0], sizes[2] / sizes[1])
    assert result["order"] == pytest.approx(2.0, abs=0.01)


def test_study_sorts_from_the_finest_mesh_and_uses_three_levels():
    sizes = [(28e6, 1.0), (12e6, None), (5e6, None)]
    h = [(c / 28e6) ** (-1 / 3) for c, _ in sizes]
    cds = [1.5 + 0.4 * x**2 for x in h]
    packs = [pack("gruba", 5_000_000, cds[2]), pack("gesta", 28_000_000, cds[0]), pack("srednia", 12_000_000, cds[1])]
    result = study(packs)
    assert [m["name"] for m in result["meshes"]] == ["gesta", "srednia", "gruba"]
    cd = next(q for q in result["quantities"] if q["id"] == "Cd")
    assert cd["kind"] == "zbieżna"
    assert cd["order"] == pytest.approx(2.0, abs=0.05)
    assert result["comparable"] is True and result["issues"] == []


def test_two_meshes_give_a_difference_but_no_order():
    result = study([pack("a", 28_000_000, 1.60), pack("b", 12_000_000, 1.64)])
    cd = next(q for q in result["quantities"] if q["id"] == "Cd")
    assert cd["kind"] == "tylko dwie siatki"
    assert cd["relativeDifferencePct"] == [pytest.approx(2.5, abs=0.01)]
    assert "order" not in cd


def test_a_different_turbulence_model_makes_the_study_not_comparable():
    a = pack("a", 28_000_000, 1.6)
    b = pack("b", 12_000_000, 1.7, methods__turbulence="Realizable k-epsilon")
    issues = differences([a, b])
    assert any("model turbulencji" in i for i in issues)
    assert study([a, b])["comparable"] is False


def test_an_unsettled_run_is_flagged_but_still_compared():
    a = pack("a", 28_000_000, 1.6)
    a["kpis"]["convergence"]["settled"] = False
    result = study([a, pack("b", 12_000_000, 1.7)])
    assert any("a:" in i and "nie ustabilizowały" in i for i in result["issues"])
    assert result["comparable"] is True


def test_a_different_reference_area_hints_at_a_different_car():
    a = pack("a", 28_000_000, 1.6)
    b = pack("b", 12_000_000, 1.7)
    b["kpis"]["references"]["frontalAreaM2"]["value"] = 0.55
    assert any("powierzchnia odniesienia" in i for i in differences([a, b]))


def test_missing_cell_counts_are_refused():
    with pytest.raises(ValueError):
        study([pack("a", 28_000_000, 1.6), pack("b", None, 1.7)])
    assert cells_of(pack("c", 0, 1.0)) is None


def test_a_single_pack_is_refused():
    with pytest.raises(ValueError):
        study([pack("a", 28_000_000, 1.6)])

