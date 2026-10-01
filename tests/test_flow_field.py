"""Vortex finding and tracking on synthetic planes."""

import numpy as np

from ingest.flow_field import (
    BOX_Y,
    BOX_Z,
    PITCH_M,
    bin_plane,
    find_vortices,
    grid_shape,
    link_tracks,
    station_list,
    swirl_fields,
    tag_region,
)

SPEED = 15.0


def _grid():
    ny, nz = grid_shape()
    y = BOX_Y[0] + (np.arange(ny) + 0.5) * PITCH_M
    z = BOX_Z[0] + (np.arange(nz) + 0.5) * PITCH_M
    return np.meshgrid(y, z, indexing="ij")


def lamb_oseen(y0, z0, gamma, core):
    yy, zz = _grid()
    dy, dz = yy - y0, zz - z0
    r2 = np.maximum(dy**2 + dz**2, 1e-12)
    swirl = gamma / (2 * np.pi * r2) * (1 - np.exp(-r2 / core**2))
    return -swirl * dz, swirl * dy  # v, w


def test_a_vortex_is_found_with_its_circulation_and_position():
    v, w = lamb_oseen(-0.5, 0.4, gamma=2.0, core=0.05)
    swirl, omega = swirl_fields(v, w)
    found = find_vortices(swirl, omega, np.ones_like(v), PITCH_M, SPEED)
    assert len(found) == 1
    top = found[0]
    assert abs(top["y_m"] + 0.5) < 0.03 and abs(top["z_m"] - 0.4) < 0.03
    assert top["circulationM2s"] > 0
    assert 0.3 < top["circulationM2s"] < 2.5  # the core holds part of the total circulation


def test_the_turning_direction_follows_the_sign_of_the_circulation():
    v, w = lamb_oseen(-0.5, 0.4, gamma=-2.0, core=0.05)
    swirl, omega = swirl_fields(v, w)
    found = find_vortices(swirl, omega, np.ones_like(v), PITCH_M, SPEED)
    assert found and found[0]["circulationM2s"] < 0
    assert "zgodnie" in found[0]["turn"]


def test_plain_shear_near_a_wall_is_not_a_vortex():
    yy, zz = _grid()
    v = np.zeros_like(yy)
    w = np.zeros_like(yy)
    u_profile = 0.0 * zz
    w[:] = 0.0
    v[:] = 8.0 * np.clip(0.1 - zz, 0, None) / 0.1  # sideways velocity that falls to zero away from the wall
    swirl, omega = swirl_fields(v, w)
    assert find_vortices(swirl, omega, np.ones_like(v), PITCH_M, SPEED) == []
    assert np.nanmax(np.abs(omega)) > 10  # there is vorticity, but no swirl
    assert u_profile.shape == v.shape


def test_two_vortices_are_ranked_by_circulation():
    v1, w1 = lamb_oseen(-0.4, 0.3, gamma=4.0, core=0.05)
    v2, w2 = lamb_oseen(-0.9, 0.7, gamma=-2.5, core=0.05)
    swirl, omega = swirl_fields(v1 + v2, w1 + w2)
    found = find_vortices(swirl, omega, np.ones_like(v1), PITCH_M, SPEED)
    assert len(found) == 2
    assert abs(found[0]["circulationM2s"]) > abs(found[1]["circulationM2s"])
    assert found[0]["circulationM2s"] > 0 > found[1]["circulationM2s"]


def test_binning_averages_cells_and_leaves_empty_bins_empty():
    y = np.array([-0.5, -0.5, -0.5])
    z = np.array([0.4, 0.4, 0.4])
    grid = bin_plane(y, z, {"u": np.array([1.0, 2.0, 6.0])})
    assert np.nanmax(grid["u"]) == 3.0
    assert int(np.isfinite(grid["u"]).sum()) == 1
    assert grid["count"].sum() == 3


def _station(x, vortices):
    return {"x_m": x, "vortices": vortices}


def _vortex(y, z, gamma):
    return {"y_m": y, "z_m": z, "circulationM2s": gamma, "minCpt": 0.8}


def test_a_vortex_is_tracked_across_stations():
    stations = [
        _station(0.0, [_vortex(-0.5, 0.3, 1.0)]),
        _station(0.1, [_vortex(-0.52, 0.31, 1.4)]),
        _station(0.2, [_vortex(-0.55, 0.33, 1.1)]),
    ]
    tracks = link_tracks(stations)
    assert len(tracks) == 1
    assert tracks[0]["fromX_m"] == 0.0 and tracks[0]["toX_m"] == 0.2
    assert tracks[0]["strongestAtX_m"] == 0.1


def test_opposite_vortices_are_not_joined_even_when_close():
    stations = [_station(0.0, [_vortex(-0.5, 0.3, 1.0)]), _station(0.1, [_vortex(-0.5, 0.3, -1.0)])]
    assert link_tracks(stations) == []


def test_a_single_sighting_is_not_a_track():
    assert link_tracks([_station(0.0, [_vortex(-0.5, 0.3, 1.0)])]) == []


def test_regions_use_the_wheel_positions():
    wheels = {"front": {"originM": [0.0, -0.7, 0.2]}, "rear": {"originM": [1.5, -0.7, 0.2]}}
    assert "przednim" in tag_region(0.4, -0.7, 0.25, wheels)
    assert "tylnym" in tag_region(1.9, -0.7, 0.25, wheels)
    assert "przednie skrzydło" in tag_region(-0.6, -0.4, 0.4, wheels)
    assert "podłog" in tag_region(0.8, -0.2, 0.05, wheels)
    assert "tylne skrzydło" in tag_region(1.9, -0.2, 0.9, wheels)


def test_station_list_covers_the_range():
    stations = station_list(-1.0, 1.0, 0.5)
    assert stations == [-1.0, -0.5, 0.0, 0.5, 1.0]
