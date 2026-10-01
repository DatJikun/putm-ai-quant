"""The viewer package: numerical pieces on synthetic data, then a whole package written to disk."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

from ingest import viewer_export as ve

zarr = pytest.importorskip("zarr")
S = 0.1  # a coarse grid keeps the tests fast


def test_cells_are_averaged_into_voxels_and_empty_voxels_stay_nan():
    centers = np.array([[0.5, -0.5, 0.5], [0.5, -0.5, 0.5], [2.0, -0.2, 1.0]], dtype=np.float32)
    grids, counts = ve.bin_cells(centers, {"u": np.array([10.0, 20.0, 5.0], dtype=np.float32)}, S)
    assert counts.sum() == 3 and counts.max() == 2
    assert np.nanmax(grids["u"]) == 15.0
    assert np.isnan(grids["u"]).sum() == grids["u"].size - 2


def test_cells_outside_the_box_are_ignored():
    centers = np.array([[9.0, 0.0, 0.0], [0.0, 0.0, 0.5]], dtype=np.float32)
    _, counts = ve.bin_cells(centers, {"u": np.ones(2, dtype=np.float32)}, S)
    assert counts.sum() == 1


def _slab():
    shape = ve.grid_shape(S)
    counts = np.zeros(shape)
    counts[20:24, 6:9, 4:7] = 1
    grid = np.full(shape, np.nan)
    grid[20:24, 6:9, 4:7] = 7.0
    return grid, counts


def test_filling_reaches_a_little_beyond_data_but_not_across_the_domain():
    grid, counts = _slab()
    fields, mask = ve.fill_volume({"u": grid}, counts)
    assert mask[21, 7, 5] == 1 and mask[24, 7, 5] == 1  # next to the data
    assert mask[0, 0, 0] == 0  # far away, nothing to take from
    assert fields["u"].dtype == np.dtype("<f4") and fields["u"][0, 0, 0] == 0.0
    assert fields["u"][24, 7, 5] == 7.0


def test_the_volume_has_cp_and_total_pressure_coefficients():
    centers = np.array([[0.5, -0.5, 0.5]], dtype=np.float32)
    one = lambda x: np.array([x], dtype=np.float32)  # noqa: E731
    fields, mask = ve.volume_fields(centers, one(-100.0), one(15.0), one(0.0), one(0.0), 1.225, 15.0, S)
    q = 0.5 * 1.225 * 225
    i = tuple(np.argwhere(mask)[0])
    assert fields["cp"][i] == pytest.approx(-100.0 / q, rel=1e-5)
    assert fields["cpt"][i] == pytest.approx((-100.0 + q) / q, rel=1e-5)
    assert set(fields) == {"u", "v", "w", "pressure", "cp", "cpt"}


def _cube_faces():
    corners = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], dtype=float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    xyz = np.concatenate([corners[list(q)] for q in quads])
    return xyz, np.full(6, 4)


def test_clustering_keeps_a_cube_as_six_polygons_and_averages_values_at_points():
    xyz, counts = _cube_faces()
    out = ve.cluster_faces(xyz, counts, {"cp": np.arange(6.0)}, voxel=0.5)
    assert out["points"].shape == (8, 3) and out["offsets"].size == 6
    assert out["offsets"][-1] == out["connectivity"].size == 24
    assert np.all(out["offsets"][1:] - out["offsets"][:-1] == 4)
    # every corner touches three faces, so its value is the mean of three face values
    assert out["point_values"]["cp"].min() >= 0.0 and out["point_values"]["cp"].max() <= 5.0


def test_a_face_that_collapses_into_a_line_is_dropped():
    tiny = np.array([[0, 0, 0], [0.0005, 0, 0], [0.001, 0.0004, 0], [0.0004, 0.0004, 0]], dtype=float)
    big = np.array([[1, 0, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]], dtype=float)
    out = ve.cluster_faces(np.concatenate([tiny, big]), np.array([4, 4]), {"cp": np.array([1.0, 2.0])}, voxel=0.01)
    assert out["offsets"].size == 1 and out["face_index"].tolist() == [1]


def test_merging_nodes_reduces_the_point_count():
    rng = np.random.default_rng(3)
    xyz = rng.uniform(0, 0.02, size=(400, 3))
    out = ve.cluster_faces(xyz, np.full(100, 4), {"cp": np.zeros(100)}, voxel=0.01)
    assert out["points"].shape[0] <= 8


def test_a_streamline_follows_a_uniform_flow_straight():
    shape = ve.grid_shape(S)
    u = np.full(shape, 10.0, dtype="f4")
    zero = np.zeros(shape, dtype="f4")
    mask = np.ones(shape, dtype="u1")
    paths = ve.integrate_streamlines(u, zero, zero, mask, np.array([[-1.0, -0.5, 0.4]]), spacing=S, step=0.05, max_length=2.0)
    assert len(paths) == 1
    path = paths[0]
    assert path[-1][0] == pytest.approx(path[0][0] + 2.0, abs=0.05)
    assert np.allclose(path[:, 1], -0.5) and np.allclose(path[:, 2], 0.4)


def test_a_streamline_bends_with_the_flow_and_stops_at_a_solid():
    shape = ve.grid_shape(S)
    u = np.full(shape, 10.0, dtype="f4")
    w = np.full(shape, 5.0, dtype="f4")
    mask = np.ones(shape, dtype="u1")
    mask[30:, :, :] = 0
    path = ve.integrate_streamlines(u, np.zeros(shape, dtype="f4"), w, mask, np.array([[-1.0, -0.5, 0.1]]), spacing=S, step=0.05, max_length=6.0)[0]
    slope = (path[-1][2] - path[0][2]) / (path[-1][0] - path[0][0])
    assert slope == pytest.approx(0.5, abs=0.05)
    assert path[-1][0] < ve.grid_origin()[0] + 30 * S + 0.1


def test_plane_seeds_cover_the_requested_grid():
    seeds = ve.plane_seeds(-1.0, (-0.9, -0.1), (0.1, 0.5), (3, 2))
    assert seeds.shape == (6, 3) and np.all(seeds[:, 0] == -1.0)
    assert seeds[:, 1].min() == -0.9 and seeds[:, 2].max() == 0.5


def test_the_digest_changes_when_a_file_changes_and_ignores_absent_files(tmp_path):
    (tmp_path / "a.json").write_text("1", encoding="utf-8")
    first = ve.digest_paths(tmp_path, [tmp_path / "a.json", tmp_path / "missing"])
    (tmp_path / "a.json").write_text("2", encoding="utf-8")
    assert ve.digest_paths(tmp_path, [tmp_path / "a.json"]) != first


def _build(tmp_path):
    xyz, counts = _cube_faces()
    clustered = ve.cluster_faces(xyz, counts, {"cp": np.arange(6.0), "wss": np.ones(6), "yplus": np.ones(6)}, voxel=0.5)
    surface = {**clustered, "zone_id": np.zeros(clustered["offsets"].size, dtype=np.int32)}
    shape = ve.grid_shape(S)
    fields = {f["id"]: np.full(shape, 1.0, dtype="<f4") for f in ve.VOLUME_FIELDS}
    mask = np.ones(shape, dtype="u1")
    paths = {s["id"]: ([np.array([[0, -0.5, 0.4], [0.1, -0.5, 0.4], [0.2, -0.5, 0.4]])] if s["id"] == "przod" else []) for s in ve.STREAMLINE_PRESETS}
    return ve.assemble_package(tmp_path / "demo.viewer", case_id="demo", display_name="Demo", reference={"rho": 1.225, "speed_ms": 15.0, "length_m": 1.53}, fields=fields, mask=mask, surface=surface, zone_names=["surface_fw"], streams=ve.STREAMLINE_PRESETS, paths_by_stream=paths, spacing=S)


def test_the_package_has_every_part_the_viewer_expects(tmp_path):
    root = _build(tmp_path)
    for name in ("metadata.json", "surface.vtp", "presets.json", "COMPLETE", "volume.zarr", "streamlines/przod.vtp"):
        assert (root / name).exists(), name
    meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert set(meta["checksums"]) == {"surface", "presets", "streamlines", "volume"}
    assert meta["grid"]["shape"] == list(ve.grid_shape(S)) and meta["steady"] is True
    assert {f["id"] for f in meta["volume_fields"]} >= {"u", "v", "w"}
    assert meta["checksums"]["surface"] == ve.digest_group(root, "surface")
    group = zarr.open_group(root / "volume.zarr", mode="r")
    for field in ("u", "v", "w", "valid_mask"):
        for axis in "xyz":
            assert tuple(group[field][axis].shape) == tuple(meta["grid"]["shape"])
    assert group["u"]["x"].dtype == np.dtype("<f4") and group["valid_mask"]["y"].dtype == np.dtype("u1")


def test_the_surface_file_declares_its_counts_and_the_zone_of_each_polygon(tmp_path):
    root = _build(tmp_path)
    text = (root / "surface.vtp").read_text(encoding="utf-8")
    assert 'NumberOfPoints="8"' in text and 'NumberOfPolys="6"' in text
    assert 'Name="zone_id"' in text and 'Name="cp"' in text and 'Name="yplus"' in text
    assert 'NumberOfComponents="3"' in text


def test_an_existing_package_is_replaced_not_mixed(tmp_path):
    first = _build(tmp_path)
    (first / "stale.txt").write_text("x", encoding="utf-8")
    second = _build(tmp_path)
    assert not (second / "stale.txt").exists()
    assert not (tmp_path / "demo.viewer.building").exists()


def test_a_cell_count_mismatch_in_the_vtp_writer_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ve.write_vtp(tmp_path / "x.vtp", np.zeros((3, 3)), polys=(np.array([0, 1, 2]), np.array([3])), cell_data={"zone_id": np.array([0, 1])})


@pytest.mark.skipif(not os.environ.get("CFD3D_SRC"), reason="set CFD3D_SRC to the viewer's src folder to check against its own validator")
def test_the_package_passes_the_viewers_own_validation(tmp_path):
    sys.path.insert(0, os.environ["CFD3D_SRC"])
    from cfd3d.package import CasePackage

    root = _build(tmp_path)
    package = CasePackage.open(Path(root))
    assert package.metadata.case_id == "demo"
    assert package.read_slice("u", "x", 10).values.shape == ve.grid_shape(S)[1:]
