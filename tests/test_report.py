"""The traffic lights of the report: each rule on tiny synthetic inputs."""

from ingest.report import (
    BAD,
    NONE,
    OK,
    WARN,
    check_checksum,
    check_force_convergence,
    check_mass_balance,
    check_mesh_quality,
    check_residuals,
    check_run_health,
    check_yplus,
    group_yplus,
    missing_data,
    overall,
)


def _pack(**parts):
    return {
        "kpis": parts.get("kpis", {}),
        "mesh": parts.get("mesh", {}),
        "methods": parts.get("methods", {}),
        "files": parts.get("files", {}),
        "monitors": {},
        "images": {},
    }


def test_force_convergence_is_red_above_two_percent_drift():
    conv = {"settled": False, "windowIterations": 200, "cx": {"driftPct": 1.0}, "cz": {"driftPct": -6.5}, "cm": {"driftPct": 17.0}}
    assert check_force_convergence(_pack(kpis={"convergence": conv}))["status"] == BAD
    conv["cz"]["driftPct"] = -1.0
    assert check_force_convergence(_pack(kpis={"convergence": conv}))["status"] == WARN
    settled = {"settled": True, "cx": {"driftPct": 0.1}}
    assert check_force_convergence(_pack(kpis={"convergence": settled}))["status"] == OK
    assert check_force_convergence(_pack())["status"] == NONE


def test_residual_check_grades_by_distance_from_the_limit():
    ok = {"residuals": {"equations": {"continuity": {"final": 5e-4, "trend": {"verdict": "spada"}}}, "aboveLimit": [], "allBelowLimit": True}}
    assert check_residuals(ok)["status"] == OK
    warn = {"residuals": {"equations": {"continuity": {"final": 3e-3, "trend": {"verdict": "płaskie"}}}, "aboveLimit": ["continuity"], "allBelowLimit": False}}
    result = check_residuals(warn)
    assert result["status"] == WARN and "płaskie" in result["detail"]
    bad = {"residuals": {"equations": {"continuity": {"final": 5e-2, "trend": {"verdict": "spada"}}}, "aboveLimit": ["continuity"], "allBelowLimit": False}}
    assert check_residuals(bad)["status"] == BAD
    assert check_residuals({"residuals": None})["status"] == NONE


def test_mass_balance_check():
    good = {"massBalance": {"relativeImbalance": 1e-7, "inflowKgS": 10.0, "outflowKgS": 10.0}}
    assert check_mass_balance(good)["status"] == OK
    leak = {"massBalance": {"relativeImbalance": 0.05, "inflowKgS": 10.0, "outflowKgS": 9.5}}
    assert check_mass_balance(leak)["status"] == BAD
    assert check_mass_balance({"massBalance": None})["status"] == NONE


def test_checksum_check_has_a_yellow_band():
    def walls(cd, df):
        return {"checksum": {"cdRelErr": cd, "downforceRelErr": df}}

    assert check_checksum(walls(0.001, 0.002))["status"] == OK
    assert check_checksum(walls(0.002, 0.02))["status"] == WARN
    assert check_checksum(walls(0.002, 0.08))["status"] == BAD
    assert check_checksum(None)["status"] == NONE


def test_mesh_quality_check_uses_fluents_ortho_guidance():
    assert check_mesh_quality(_pack(mesh={"minOrthogonalQuality": 0.2, "cells": 1000}))["status"] == OK
    assert check_mesh_quality(_pack(mesh={"minOrthogonalQuality": 0.04}))["status"] == WARN
    assert check_mesh_quality(_pack(mesh={"minOrthogonalQuality": 0.005}))["status"] == BAD
    assert check_mesh_quality(_pack(mesh={}))["status"] == NONE


def _zone(group, area, shares, median=1.0, peak=2.0):
    return {"group": group, "areaM2": area, "yplus": {"areaShare": shares, "median": median, "max": peak, "maxAtM": [0, 0, 0]}}


def test_yplus_check_depends_on_the_wall_treatment():
    resolved = {"le1": 0.97, "1to5": 0.03, "5to30": 0.0, "30to300": 0.0, "gt300": 0.0}
    walls = {"zones": {"surface_fw": _zone("fw", 1.0, resolved)}}
    walls["groupYplus"] = group_yplus(walls["zones"])
    sst = _pack(methods={"turbulence": "k-omega SST", "wallTreatment": "k-omega (bez funkcji ściany)"})
    assert check_yplus(sst, walls)["status"] == OK
    wall_fn = _pack(methods={"turbulence": "k-epsilon", "wallTreatment": "Standard Wall Functions"})
    assert check_yplus(wall_fn, walls)["status"] == BAD
    assert check_yplus(_pack(), walls)["status"] == NONE


def test_yplus_check_accepts_the_whole_range_with_enhanced_wall_treatment():
    shares = {"le1": 0.0, "1to5": 0.0, "5to30": 0.5, "30to300": 0.5, "gt300": 0.0}
    walls = {"zones": {"surface_fw": _zone("fw", 1.0, shares)}}
    walls["groupYplus"] = group_yplus(walls["zones"])
    pack = _pack(methods={"turbulence": "k-epsilon", "wallTreatment": "Enhanced Wall Treatment"})
    assert check_yplus(pack, walls)["status"] == OK


def test_group_yplus_ignores_wheels_and_weights_by_area():
    zones = {
        "surface_fw": _zone("fw", 1.0, {"le1": 1.0}),
        "surface_rw": _zone("rw", 3.0, {"le1": 0.0, "5to30": 1.0}),
        "surface_front_wheel": _zone("wheels", 5.0, {"gt300": 1.0}),
    }
    stats = group_yplus(zones)["all"]
    assert stats["areaM2"] == 4.0
    assert stats["shares"]["le1"] == 0.25
    assert stats["shares"]["5to30"] == 0.75


def test_run_health_is_red_when_the_last_session_crashed():
    crashed = [{"file": "a.trn", "lastIteration": 100, "crashed": True}]
    assert check_run_health(_pack(methods={"solverSessions": crashed}))["status"] == BAD
    done = [{"file": "a.trn", "lastIteration": 100, "crashed": False}]
    assert check_run_health(_pack(methods={"solverSessions": done}))["status"] == OK
    early = {"convergence": {"stoppedEarly": True, "iterationsLeft": 5, "plannedIterations": 10}}
    assert check_run_health(_pack(methods={"solverSessions": done}, kpis=early))["status"] == WARN


def test_overall_is_the_worst_traffic_light():
    checks = [{"title": "a", "status": OK}, {"title": "b", "status": WARN}, {"title": "c", "status": NONE}]
    verdict = overall(checks)
    assert verdict["status"] == WARN and verdict["missing"] == ["c"]
    assert overall(checks + [{"title": "d", "status": BAD}])["status"] == BAD
    assert overall(checks[:1])["status"] == OK


def test_missing_data_names_each_absent_input():
    gaps = missing_data(_pack(files={"cas": ["x.cas.h5"]}), {"missing": []}, None)
    text = " ".join(gaps)
    assert "dat" in text and "STEP" in text and "wft" in text and ".jou" in text
    assert "Nie policzono sił na części" in text
