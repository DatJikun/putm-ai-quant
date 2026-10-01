"""Plane positions, slicing, gap filling and the gallery page."""

import json

import numpy as np

from ingest.plane_images import (
    BOX,
    Slicer,
    draw_plane,
    draw_surface,
    fill_gaps,
    plane_positions,
    write_gallery,
)


def test_default_planes_follow_the_cfd_post_animation():
    pos = plane_positions({"frames": 150, "x": {"startM": -1.1, "endM": 2.5}, "y": {"startM": -0.01, "endM": -0.9}, "z": {"startM": 0.0, "endM": 1.5}})
    assert {len(v) for v in pos.values()} == {150}
    assert pos["x"][0] == -1.1 and pos["x"][-1] == 2.5
    assert abs((pos["x"][1] - pos["x"][0]) - 0.0242) < 1e-4
    assert pos["y"][0] == -0.01 and pos["y"][-1] == -0.9


def test_planes_come_from_the_picture_index_when_it_has_them():
    index = {"index": [{"axis": "x", "stationM": round(-1.0 + 0.05 * i, 4)} for i in range(20)] + [{"axis": "full", "stationM": None}]}
    pos = plane_positions(None, index)
    assert len(pos["x"]) == 20 and pos["x"][1] == -0.95
    assert len(pos["y"]) == 150  # no picture stations for y, so the template default


def _cloud():
    rng = np.random.default_rng(1)
    centers = rng.uniform([-1.0, -1.0, 0.0], [2.0, 0.1, 1.5], size=(20000, 3)).astype(np.float32)
    return centers, {"f": centers[:, 0].copy()}


def test_a_slab_holds_only_cells_near_the_plane():
    centers, fields = _cloud()
    idx = Slicer(centers, fields).slab("x", 0.5, 0.05)
    assert idx.size > 0
    assert np.all(np.abs(centers[idx, 0] - 0.5) <= 0.05)


def test_grid_averages_the_field_in_each_bin_and_uses_the_right_axes():
    centers, fields = _cloud()
    grid = Slicer(centers, fields).grid("y", -0.5, 0.05, pitch=0.05)
    nh = int(np.ceil((BOX["x"][1] - BOX["x"][0]) / 0.05))
    nv = int(np.ceil((BOX["z"][1] - BOX["z"][0]) / 0.05))
    assert grid["f"].shape == (nh, nv)
    filled = np.isfinite(grid["f"])
    assert filled.any()
    # the field was the x coordinate, so each bin mean must sit inside the bin's x range
    ix = np.flatnonzero(filled.any(axis=1))
    lo = BOX["x"][0] + ix * 0.05
    assert np.all(np.nanmean(grid["f"][ix], axis=1) >= lo - 1e-3)


def test_gaps_close_only_near_data():
    grid = np.full((20, 20), np.nan)
    grid[5, 5] = 1.0
    filled = fill_gaps(grid, bins=2)
    assert np.isfinite(filled[5, 7]) and np.isfinite(filled[4, 4])
    assert not np.isfinite(filled[15, 15])


def test_a_plane_and_a_surface_view_are_written_as_png(tmp_path):
    grid = np.random.default_rng(0).uniform(-1, 1, (40, 30))
    draw_plane(grid, "x", 0.5, "cp", tmp_path / "plane.png", markers=[{"y_m": -0.5, "z_m": 0.3}])
    xyz = np.random.default_rng(0).uniform([-1, -1, 0], [2, 0, 1], size=(5000, 3))
    draw_surface(xyz, xyz[:, 0], "z-boku", "cp", tmp_path / "side.png")
    for name in ("plane.png", "side.png"):
        data = (tmp_path / name).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 1000


def test_the_gallery_page_lists_every_axis_field_and_surface_image(tmp_path):
    page = write_gallery(tmp_path, {"x": [0.0, 0.1], "y": [-0.1]}, {"cp": "Cp"}, ["cp_z-gory.png"], "Test <b>")
    text = page.read_text(encoding="utf-8")
    assert "&lt;b&gt;" in text and "Test <b>" not in text
    data = json.loads(text.split("const DATA = ")[1].split(";\n")[0])
    assert data["planes"] == {"x": [0.0, 0.1], "y": [-0.1]}
    assert data["surface"] == ["cp_z-gory.png"]
    assert "przekroje/" in text and "powierzchnia/" in text
