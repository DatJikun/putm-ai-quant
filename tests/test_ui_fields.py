"""Residuals and y+ in the places the workbench reads them from."""

from ingest.report import attach_solver_fields


def _cons():
    return {"residuals": {"iterations": 860, "equations": {"continuity": {"final": 5e-3}, "x-velocity": {"final": 1e-7}, "omega": {"final": 1e-3}, "epsilon": {"final": 2e-5}}}}


def _walls():
    def zone(group, area, mn, mean, mx):
        return {"group": group, "areaM2": area, "yplus": {"min": mn, "mean": mean, "median": mean, "max": mx}}

    return {"zones": {"surface_fw": zone("fw", 1.0, 0.1, 0.5, 2.0), "surface_rw": zone("rw", 3.0, 0.2, 1.0, 1.5), "surface_ut": zone("floor", 2.0, 0.3, 0.6, 3.0), "surface_x": zone(None, 9.0, 0, 99, 999)}}


def test_residuals_use_the_names_the_workbench_knows():
    pack = {}
    attach_solver_fields(pack, _cons(), None)
    res = pack["monitors"]["residuals"]
    assert res["continuity"] == 5e-3 and res["xMomentum"] == 1e-7
    assert res["omega"] == 1e-3 and res["epsilon"] == 2e-5 and res["iteration"] == 860


def test_a_residual_table_from_a_log_is_not_overwritten():
    pack = {"monitors": {"residuals": {"continuity": 0.5}}}
    attach_solver_fields(pack, _cons(), None)
    assert pack["monitors"]["residuals"] == {"continuity": 0.5}


def test_yplus_is_merged_for_wings_and_floor_weighted_by_area():
    pack = {}
    attach_solver_fields(pack, {}, _walls())
    block = pack["monitors"]["yPlus"]
    assert block["wings"] == {"min": 0.1, "avg": round((0.5 * 1 + 1.0 * 3) / 4, 3), "max": 2.0}
    assert block["floor"] == {"min": 0.3, "avg": 0.6, "max": 3.0}


def test_nothing_is_added_without_data():
    pack = {}
    attach_solver_fields(pack, {"residuals": None}, None)
    assert "residuals" not in pack["monitors"] and "yPlus" not in pack["monitors"]
