"""Mesh quality measured from the mesh itself, for cases without the meshing log.

Orthogonal quality as Fluent defines it: for every face of a cell, the cosine of the angle
between the face normal and (a) the vector from the cell centre to the face centre,
(b) the vector from the cell centre to the neighbouring cell centre. The quality of a
cell is the smallest of those, and 0 is bad, 1 is perfect.

Cell centres are rebuilt as the mean of the face centres, not the true volume centroid,
so the result is an approximation and can differ a little from the meshing log.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ingest.flow_field import cell_centers
from ingest.h5_mesh import iter_face_chunks

THRESHOLDS = (0.01, 0.1, 0.2)


def _cos(vec_a: np.ndarray, vec_b: np.ndarray) -> np.ndarray:
    num = (vec_a * vec_b).sum(axis=1)
    den = np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1)
    return num / np.maximum(den, 1e-30)


def face_quality(area, centre, first_centre, second_centre=None, second_face=None) -> np.ndarray:
    """Quality of each face of the slice. `area` points into the first cell (outward for the second).

    first_centre: centre of the first cell of each face. second_centre / second_face: centres of the
    second cell and the indices of the faces that have one. Boundary faces only see the first cell.
    """
    out = _cos(-area, centre - first_centre)
    if second_face is not None and second_face.size:
        a, f = area[second_face], centre[second_face]
        to_face = _cos(a, f - second_centre)
        between = _cos(-a, second_centre - first_centre[second_face])
        out[second_face] = np.minimum(out[second_face], np.minimum(to_face, between))
    return out


def measure(cas_path: Path, cache: Path | None = None, chunk_faces: int = 1_000_000) -> dict:
    import h5py

    centers = cell_centers(cas_path, cache)
    worst, worst_at = np.inf, None
    below = {t: 0 for t in THRESHOLDS}
    faces = 0
    with h5py.File(cas_path, "r") as mesh:
        for _, _, area, centre, first, face_idx, second in iter_face_chunks(mesh, chunk_faces):
            ok = (first > 0) & (np.linalg.norm(area, axis=1) > 0)
            first_centre = centers[np.maximum(first, 1) - 1].astype(np.float64)
            second_centre = centers[second - 1].astype(np.float64) if second.size else None
            q = face_quality(area, centre, first_centre, second_centre, face_idx)
            q = np.where(ok, q, 1.0)
            faces += int(q.size)
            for t in THRESHOLDS:
                below[t] += int((q < t).sum())
            i = int(np.argmin(q))
            if q[i] < worst:
                worst, worst_at = float(q[i]), [round(float(v), 3) for v in centre[i]]
    return {
        "minOrthogonalQuality": round(worst, 4),
        "worstAtM": worst_at,
        "facesBelow": {f"{t:g}": below[t] for t in THRESHOLDS},
        "faces": faces,
        "approximate": True,
        "note": "Obliczone z geometrii (środki komórek to średnia środków ścianek), więc może różnić się od logu siatkowania.",
    }
