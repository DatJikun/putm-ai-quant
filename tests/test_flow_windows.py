"""Loss windows behind the wheels."""

import numpy as np

from ingest.flow_field import BOX_Y, BOX_Z, PITCH_M, grid_shape, wheel_windows, window_loss


def _cpt(lossy_y=(-0.8, -0.6), lossy_z_max=0.3, value=0.5):
    ny, nz = grid_shape()
    y = BOX_Y[0] + (np.arange(ny) + 0.5) * PITCH_M
    z = BOX_Z[0] + (np.arange(nz) + 0.5) * PITCH_M
    cpt = np.ones((ny, nz))
    cpt[np.ix_((y >= lossy_y[0]) & (y <= lossy_y[1]), z <= lossy_z_max)] = value
    return cpt


def test_window_loss_measures_the_lossy_patch():
    result = window_loss(_cpt(), (-1.05, -0.35), 0.6)
    assert result["minCpt"] == 0.5
    assert 0.18 < result["widthM"] < 0.24
    area = 0.2 * 0.32
    assert abs(result["lossAreaM2"] - area) < 0.02
    assert abs(result["lossIntegralM2"] - 0.5 * area) < 0.02


def test_window_loss_of_clean_air_is_zero():
    ny, nz = grid_shape()
    result = window_loss(np.ones((ny, nz)), (-1.05, -0.35), 0.6)
    assert result["lossAreaM2"] == 0.0 and result["widthM"] == 0.0


def test_window_loss_ignores_loss_outside_the_window():
    result = window_loss(_cpt(lossy_y=(0.0, 0.1)), (-1.05, -0.35), 0.6)
    assert result["lossAreaM2"] == 0.0


def test_only_stations_behind_a_wheel_get_its_window():
    wheels = {"front": {"originM": [0.0, -0.7, 0.2]}, "rear": {"originM": [1.5, -0.7, 0.2]}}
    cpt = _cpt()
    assert wheel_windows(cpt, -0.5, wheels) == {}
    assert set(wheel_windows(cpt, 0.8, wheels)) == {"front"}
    assert set(wheel_windows(cpt, 1.0, wheels)) == {"front"}
    assert set(wheel_windows(cpt, 2.0, wheels)) == {"rear"}
    assert wheel_windows(cpt, 2.0, None) == {}
