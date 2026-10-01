"""The meta pack: binning, quantizing, findings, files with checksums, and drawing from the maps alone."""

import json

import numpy as np
import pytest

from ingest import metapack as mp


def _faces(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    xyz = rng.uniform([0.0, -0.7, 0.0], [2.0, 0.0, 1.0], size=(n, 3))
    return {
        "names": ["surface_fw", "surface_rw"],
        "xyz": xyz,
        "zone": (xyz[:, 0] > 1.0).astype(np.uint8),
        "cp": -xyz[:, 0],
        "wss": np.abs(xyz[:, 1]) * 3,
        "yplus": np.full(n, 0.5),
        "rev": (xyz[:, 2] > 0.8).astype(np.float64),
    }


def test_binning_keeps_every_face_and_averages_inside_a_voxel():
    xyz = np.array([[0.1005, -0.5, 0.2], [0.1008, -0.5, 0.2], [1.0, -0.2, 0.5]])
    out = mp.bin_surface(xyz, np.array([0, 0, 1], dtype=np.uint8), {"cp": np.array([1.0, 3.0, 5.0])}, 0.01)
    assert out["ijk"].shape == (2, 3) and out["faces"].sum() == 3
    assert sorted(out["cp"].tolist()) == [2.0, 5.0]
    assert sorted(out["zone"].tolist()) == [0, 1]


def test_positions_decoded_from_voxels_sit_within_half_a_voxel_of_the_faces():
    f = _faces(500)
    voxel = 0.01
    out = mp.bin_surface(f["xyz"], f["zone"], {"cp": f["cp"]}, voxel)
    pos = mp.surface_positions(out["ijk"], voxel)
    # every original face lies in a voxel whose centre is at most half a voxel away along each axis
    code_back = np.floor((pos - mp.SURFACE_ORIGIN) / voxel).astype(int)
    assert np.array_equal(code_back, out["ijk"].astype(int))
    nearest = np.abs(f["xyz"][:, None, :] - pos[None, :, :]).max(axis=2).min(axis=1)
    assert nearest.max() <= voxel / 2 + 1e-9


def test_a_finer_voxel_gives_more_points_and_the_same_faces():
    f = _faces(3000)
    values = {"cp": f["cp"]}
    coarse = mp.bin_surface(f["xyz"], f["zone"], values, 0.1)
    fine = mp.bin_surface(f["xyz"], f["zone"], values, 0.003)
    assert fine["ijk"].shape[0] > coarse["ijk"].shape[0]
    assert coarse["faces"].astype(int).sum() == fine["faces"].astype(int).sum() == 3000


def test_a_point_outside_the_map_is_refused():
    with pytest.raises(ValueError):
        mp.bin_surface(np.array([[-9.0, 0.0, 0.0]]), np.zeros(1, dtype=np.uint8), {"cp": np.zeros(1)}, 0.01)


def test_values_are_half_precision_and_reversed_flow_is_a_percent():
    binned = mp.bin_surface(_faces(200)["xyz"], np.zeros(200, dtype=np.uint8), {"cp": np.full(200, -1.2345), "wss": np.ones(200), "yplus": np.ones(200), "rev": np.full(200, 0.426)}, 0.1)
    q = mp.quantize_surface(binned)
    assert q["cp"].dtype == np.float16 and q["rev"].dtype == np.uint8
    assert set(q["rev"].tolist()) == {43}
    assert q["ijk"].dtype == np.uint16


def test_written_files_have_checksums_and_verify_passes_then_catches_damage(tmp_path):
    f = _faces(1500)
    surface = mp.write_surface_files(tmp_path, f)
    planes = {"x": {"pos": np.array([0.0, 0.1], dtype=np.float32), **{k: np.random.default_rng(1).uniform(-1, 1, (2, 5, 6)).astype(np.float16) for k in ("cp", "cpt", "vel")}}}
    plane_info = mp.write_plane_file(tmp_path, planes)
    meta = {"schemat": mp.SCHEMA, "mapy": {"powierzchnia": surface, "przekroje": plane_info}}
    mp.write_meta(tmp_path, meta)
    assert set(surface) == {"1cm", "3mm"} and surface["3mm"]["punktow"] >= surface["1cm"]["punktow"]
    assert mp.verify_meta(tmp_path) == []
    path = tmp_path / surface["1cm"]["plik"]
    path.write_bytes(path.read_bytes()[:-5] + b"xxxxx")
    assert any("suma kontrolna" in p for p in mp.verify_meta(tmp_path))
    path.unlink()
    assert any("brak pliku" in p for p in mp.verify_meta(tmp_path))


def test_verify_reports_a_missing_or_foreign_meta(tmp_path):
    assert mp.verify_meta(tmp_path) == ["brak meta.json"]
    (tmp_path / "meta.json").write_text(json.dumps({"schemat": "inny"}), encoding="utf-8")
    assert any("nieznany schemat" in p for p in mp.verify_meta(tmp_path))


def test_surface_round_trips_through_the_file(tmp_path):
    f = _faces(800)
    mp.write_surface_files(tmp_path, f)
    s = mp.load_surface(tmp_path, "1cm")
    assert s["xyz"].shape[0] == s["cp"].shape[0] and s["zone_names"] == ["surface_fw", "surface_rw"]
    assert s["voxel"] == 0.01
    assert s["cp"].min() >= -2.0 and s["cp"].max() <= 0.0
    assert 0.0 <= s["rev"].min() and s["rev"].max() <= 1.0


def test_plane_maps_cut_each_plane_and_store_half_precision():
    centers = np.random.default_rng(2).uniform([-1.0, -1.0, 0.0], [2.0, 0.1, 1.5], size=(30000, 3)).astype(np.float32)
    one = lambda v: np.full(30000, v, dtype=np.float32)  # noqa: E731
    out = mp.plane_maps(centers, one(-50.0), one(15.0), one(0.0), one(0.0), 1.225, 15.0, {"x": [0.0, 0.5]}, pitch=0.1)
    q = 0.5 * 1.225 * 225
    assert out["x"]["cp"].dtype == np.float16 and out["x"]["cp"].shape[0] == 2
    assert np.nanmax(out["x"]["cp"]) == pytest.approx(-50.0 / q, abs=1e-2)
    assert np.nanmax(out["x"]["vel"]) == pytest.approx(1.0, abs=1e-3)


def _report():
    return {
        "caseId": "T",
        "verdict": {"status": "uwaga"},
        "checks": [
            {"id": "residua", "title": "Residua", "status": "uwaga", "detail": "za wysokie"},
            {"id": "zbieznosc-sil", "title": "Siły", "status": "zle", "detail": "dryf 6%"},
            {"id": "bilans-masy", "title": "Bilans", "status": "ok", "detail": "ok"},
        ],
        "credibility": {"score": 55, "coverage": 90, "label": "Niska wiarygodność", "unknown": ["Test siatki"]},
        "walls": {"groups": {"fw": {"shareDownforcePct": 60.0, "shareDragPct": 30.0, "downforceCoeff": 1.0}, "wheels": {"shareDownforcePct": -5.0, "shareDragPct": 10.0, "downforceCoeff": -0.2}}},
        "pack": {"flowSummary": {"lossGrowth": [{"fromX_m": 1.6, "toX_m": 1.7, "growthM2": 0.1, "dragMostlyFrom": "tylne skrzydło"}], "vortexTracks": [{"peakCirculationM2s": -3.0, "region": "pod podłogą", "fromX_m": 0.0, "toX_m": 1.0}], "reverseFlow": {"fromX_m": 1.8, "toX_m": 2.1, "maxAreaM2": 0.09}}},
    }


def test_findings_are_ranked_with_evidence_and_leave_out_passed_checks():
    found = mp.build_findings(_report())
    ids = [f["id"] for f in found]
    assert ids[0] in ("sprawdzenie:zbieznosc-sil", "wiarygodnosc") and found[0]["waga"] == "wysoka"
    assert "sprawdzenie:bilans-masy" not in ids
    assert "unosi:wheels" in ids and "oderwanie-w-sladzie" in ids
    assert all(f["dowod"] for f in found)
    severities = [mp.SEVERITY_ORDER[f["waga"]] for f in found]
    assert severities == sorted(severities)


def test_provenance_says_when_a_number_is_an_approximation():
    exact = mp.build_provenance({"kpis": {"convergence": {}}, "monitors": {"monitors": {"cx": {}}}, "mesh": {"minOrthogonalQuality": 0.04}})
    assert exact["stabilnosc_sil"]["dokladnosc"] == "dokładne" and exact["jakosc_siatki"]["zrodlo"] == "log siatkowania"
    proxy = mp.build_provenance({"kpis": {"convergence": {"source": "dat.h5: różnica"}}, "mesh": {}})
    assert proxy["stabilnosc_sil"]["dokladnosc"] == "przybliżenie" and proxy["jakosc_siatki"]["dokladnosc"].startswith("przybliżenie")


def test_meta_holds_the_report_the_pack_the_findings_and_the_maps():
    report = _report()
    report["pack"]["identity"] = {"caseId": "T"}
    meta = mp.build_meta(report, {"powierzchnia": {}, "przekroje": {}})
    assert meta["schemat"] == mp.SCHEMA and meta["caseId"] == "T"
    for key in ("jak_czytac", "wnioski", "werdykt", "wiarygodnosc", "zrodla", "oryginaly", "mapy", "raport", "paczka"):
        assert key in meta
    assert "pack" not in meta["raport"] and "credibility" not in meta["raport"]
    json.dumps(meta, default=mp._json_default)


def test_pictures_can_be_drawn_again_from_the_maps_alone(tmp_path):
    f = _faces(1200)
    surface = mp.write_surface_files(tmp_path, f)
    rng = np.random.default_rng(3)
    planes = {a: {"pos": np.array([0.0, 0.5], dtype=np.float32), **{k: rng.uniform(-1, 1, (2, 30, 40)).astype(np.float16) for k in ("cp", "cpt", "vel")}} for a in "xyz"}
    info = mp.write_plane_file(tmp_path, planes)
    mp.write_meta(tmp_path, {"schemat": mp.SCHEMA, "mapy": {"powierzchnia": surface, "przekroje": info}})
    out = mp.render_from_meta(tmp_path, tmp_path / "obrazy", surface_label="1cm", every=1)
    assert out["obrazow"] == 9 + 3 * 2 * 3  # nine wall views, then two planes per axis in three fields
    pngs = list((tmp_path / "obrazy").rglob("*.png"))
    assert len(pngs) == out["obrazow"] and all(p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for p in pngs)
