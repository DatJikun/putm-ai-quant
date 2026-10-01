"""Orthogonal quality of tiny meshes whose answer is known."""

import numpy as np
import pytest

from ingest.h5_mesh import fan_area, has_symmetry
from ingest.mesh_quality import face_quality


def _quad(points):
    pts = np.asarray(points, dtype=np.float64)
    return fan_area(pts, np.array([0]), np.array([4]))[0], pts.mean(axis=0)


def test_a_face_between_two_aligned_cubes_has_quality_one():
    # two unit cubes side by side along x; the shared face at x = 1, normal pointing into cell 0 (-x)
    face = [[1, 0, 0], [1, 0, 1], [1, 1, 1], [1, 1, 0]]  # right-hand normal along -x
    area, centre = _quad(face)
    assert area[0] < 0
    c0, c1 = np.array([0.5, 0.5, 0.5]), np.array([1.5, 0.5, 0.5])
    q = face_quality(area[None], centre[None], c0[None], c1[None], np.array([0]))
    assert q[0] == pytest.approx(1.0)


def test_shifting_the_neighbour_sideways_lowers_the_quality():
    face = [[1, 0, 0], [1, 0, 1], [1, 1, 1], [1, 1, 0]]
    area, centre = _quad(face)
    c0 = np.array([0.5, 0.5, 0.5])
    straight = face_quality(area[None], centre[None], c0[None], np.array([[1.5, 0.5, 0.5]]), np.array([0]))[0]
    skewed = face_quality(area[None], centre[None], c0[None], np.array([[1.5, 1.5, 0.5]]), np.array([0]))[0]
    # the neighbour's own face-centre term is the smaller one: 0.5 / sqrt(0.5^2 + 1^2)
    assert skewed == pytest.approx(0.5 / np.sqrt(1.25), abs=1e-6)
    assert skewed < straight


def test_a_cell_whose_centre_sits_near_a_face_edge_is_poor():
    face = [[1, 0, 0], [1, 0, 1], [1, 1, 1], [1, 1, 0]]
    area, centre = _quad(face)
    off_centre = np.array([0.9, 0.95, 0.5])  # the face centre is far to the side of the cell centre
    q = face_quality(area[None], centre[None], off_centre[None])
    assert q[0] < 0.4


def test_a_boundary_face_only_looks_at_its_own_cell():
    face = [[1, 0, 0], [1, 0, 1], [1, 1, 1], [1, 1, 0]]
    area, centre = _quad(face)
    q = face_quality(area[None], centre[None], np.array([[0.5, 0.5, 0.5]]))
    assert q[0] == pytest.approx(1.0)


def test_symmetry_zone_means_half_a_car():
    class Mesh(dict):
        pass

    def mesh(types):
        top = {
            "name": np.array([b";".join(f"z{i}".encode() for i in range(len(types)))]),
            "zoneType": np.array(types),
            "minId": np.array([1 + 10 * i for i in range(len(types))]),
            "maxId": np.array([10 + 10 * i for i in range(len(types))]),
        }

        class Top(dict):
            def __getitem__(self, key):
                value = super().__getitem__(key)

                class V:
                    def __init__(self, v):
                        self.v = v

                    def __getitem__(self, _):
                        return self.v

                return V(value)

        m = Mesh()
        m["meshes/1/faces/zoneTopology"] = Top(top)
        return m

    assert has_symmetry(mesh([2, 3, 7])) is True
    assert has_symmetry(mesh([2, 3, 5])) is False
