"""Forces per zone and conservation checks, on tiny synthetic meshes."""

import numpy as np

from ingest.conservation import (
    mass_balance_from_zones,
    scaled_residuals,
    summarize_residuals,
    _porous_flows,
)
from ingest.zone_forces import _coefficients, area_vectors, group_table, with_checksum


class FakeMesh(dict):
    """Looks like the .cas.h5 for the three paths area_vectors reads."""


def square_mesh():
    # one unit square on z = 0, nodes counter-clockwise seen from +z, and a triangle
    coords = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [3, 0, 0], [2, 1, 0]],
        dtype=float,
    )
    mesh = FakeMesh()
    mesh["meshes/1/nodes/coords"] = {"77": coords}
    mesh["meshes/1/faces/nodes/1/nnodes"] = np.array([4, 3])
    mesh["meshes/1/faces/nodes/1/nodes"] = np.array([1, 2, 3, 4, 5, 6, 7])
    return mesh


def test_area_vector_points_along_right_hand_normal():
    area = area_vectors(square_mesh(), 1, 2)
    assert np.allclose(area[0], [0, 0, 1.0])
    assert np.allclose(area[1], [0, 0, 0.5])


def test_area_vector_of_a_single_face_zone():
    area = area_vectors(square_mesh(), 2, 2)
    assert area.shape == (1, 3)
    assert np.isclose(np.linalg.norm(area[0]), 0.5)


def test_coefficients_follow_the_force_directions():
    zones = {
        "surface_fw": {
            "faces": 1,
            "areaM2": 1.0,
            "F": [10.0, 0.0, -20.0],
            "Fpressure": [9.0, 0.0, -20.0],
            "Fviscous": [1.0, 0.0, 0.0],
            "group": "fw",
        }
    }
    out = _coefficients(zones, scale=5.0, cx_dir=np.array([1.0, 0, 0]), cz_dir=np.array([0, 0, -1.0]))
    rec = out["surface_fw"]
    assert np.isclose(rec["Cd"], 2.0)
    assert np.isclose(rec["Cd_viscous"], 0.2)
    assert np.isclose(rec["downforceCoeff"], 4.0)


def test_groups_skip_the_tunnel_and_sum_the_rest():
    zones = {
        "surface_fw": {"group": "fw", "Cd": 0.2, "downforceCoeff": 1.0, "Cd_pressure": 0.19, "Cd_viscous": 0.01, "areaM2": 1.0},
        "surface_rw": {"group": "rw", "Cd": 0.4, "downforceCoeff": 1.5, "Cd_pressure": 0.38, "Cd_viscous": 0.02, "areaM2": 2.0},
        "domain_ground": {"group": None, "Cd": 0.0, "downforceCoeff": 9.0, "Cd_pressure": 0.0, "Cd_viscous": 0.0, "areaM2": 300.0},
    }
    result = with_checksum(zones, cd_total=0.6, downforce_total=2.5)
    assert set(result["groups"]) == {"fw", "rw"}
    assert np.isclose(result["vehicle"]["downforceCoeff"], 2.5)
    assert result["checksum"]["ok"] is True
    assert np.isclose(result["groups"]["fw"]["shareDownforcePct"], 40.0)


def test_checksum_fails_when_sums_disagree_with_the_monitor():
    zones = {"surface_fw": {"group": "fw", "Cd": 0.2, "downforceCoeff": 1.0, "Cd_pressure": 0.2, "Cd_viscous": 0.0, "areaM2": 1.0}}
    assert with_checksum(zones, cd_total=0.4, downforce_total=1.0)["checksum"]["ok"] is False


def test_checksum_without_monitor_values_is_not_ok():
    zones = {"surface_fw": {"group": "fw", "Cd": 0.2, "downforceCoeff": 1.0, "Cd_pressure": 0.2, "Cd_viscous": 0.0, "areaM2": 1.0}}
    assert with_checksum(zones, cd_total=None, downforce_total=None)["checksum"]["ok"] is False


def test_group_table_orders_known_groups_first():
    zones = {
        "surface_x": {"group": "other", "Cd": 0, "downforceCoeff": 0, "Cd_pressure": 0, "Cd_viscous": 0, "areaM2": 0},
        "surface_rw": {"group": "rw", "Cd": 0, "downforceCoeff": 0, "Cd_pressure": 0, "Cd_viscous": 0, "areaM2": 0},
        "surface_fw": {"group": "fw", "Cd": 0, "downforceCoeff": 0, "Cd_pressure": 0, "Cd_viscous": 0, "areaM2": 0},
    }
    assert list(group_table(zones)) == ["fw", "rw", "other"]


def test_scaled_residual_is_value_over_normalisation():
    rows = np.array([[10.0, 100.0, 0, 0], [1.0, 100.0, 0, 0]])
    assert np.allclose(scaled_residuals(rows), [0.1, 0.01])


def test_residual_summary_flags_the_equation_that_misses_the_limit():
    iterations = np.arange(1, 401, dtype=float)
    falling = np.stack([np.logspace(0, -5, 400) * 100, np.full(400, 100.0), np.zeros(400), np.zeros(400)], axis=1)
    stuck = np.stack([np.full(400, 5e-3) * 100, np.full(400, 100.0), np.zeros(400), np.zeros(400)], axis=1)
    summary = summarize_residuals({"continuity": (iterations, stuck), "k": (iterations, falling)})
    assert summary["aboveLimit"] == ["continuity"]
    assert summary["allBelowLimit"] is False
    assert summary["equations"]["continuity"]["trend"]["verdict"] == "płaskie"
    assert summary["equations"]["k"]["trend"]["verdict"] == "spada"
    assert summary["equations"]["k"]["belowLimit"] is True
    assert summary["iterations"] == 400


def test_residual_summary_keeps_fluents_equation_order():
    iterations = np.arange(1, 30, dtype=float)
    rows = np.stack([np.full(29, 1e-5), np.ones(29), np.zeros(29), np.zeros(29)], axis=1)
    history = {name: (iterations, rows) for name in ("omega", "z-velocity", "continuity", "k")}
    assert list(summarize_residuals(history)["equations"]) == ["continuity", "z-velocity", "k", "omega"]


def test_mass_balance_closes_when_inlet_equals_outlet():
    zones = [
        {"name": "domain_inlet", "type": 10, "flux": -100.0},
        {"name": "domain_outlet", "type": 5, "flux": 100.0},
        {"name": "domain_symmetry", "type": 7, "flux": 0.0},
        {"name": "surface_fw", "type": 3, "flux": 0.0},
        {"name": "interior--obudowa", "type": 2, "flux": 8000.0},
    ]
    balance = mass_balance_from_zones(zones)
    assert balance["inflowKgS"] == 100.0
    assert balance["closes"] is True
    assert balance["relativeImbalance"] == 0.0


def test_mass_balance_reports_a_leak():
    zones = [
        {"name": "domain_inlet", "type": 10, "flux": -100.0},
        {"name": "domain_outlet", "type": 5, "flux": 95.0},
    ]
    balance = mass_balance_from_zones(zones)
    assert balance["closes"] is False
    assert np.isclose(balance["relativeImbalance"], 0.05)


def test_mass_balance_without_inflow_has_no_verdict():
    balance = mass_balance_from_zones([{"name": "x", "type": 5, "flux": 0.0}])
    assert balance["closes"] is None


def test_radiator_flow_is_the_mean_of_its_two_sides():
    zones = [
        {"name": "radiator_core-body:1", "type": 2, "flux": 0.10},
        {"name": "radiator_core-body:1:55740", "type": 2, "flux": -0.12},
        {"name": "interior--radiator_core-body", "type": 2, "flux": 3.0},
        {"name": "mrf_fan-body:1", "type": 2, "flux": 0.2},
    ]
    flows = _porous_flows(zones)
    assert np.isclose(flows["radiatorKgS"], 0.11)
    assert np.isclose(flows["fanKgS"], 0.2)
