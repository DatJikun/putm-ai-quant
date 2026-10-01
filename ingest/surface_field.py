"""3D bins of pressure, y+ and wall shear on named wall zones."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ingest.h5_mesh import face_ranges as _face_ranges
from ingest.h5_mesh import node_coords, node_cursor as _node_cursor, text_of as _text  # noqa: F401
from ingest.wall_state import checked_layout, wall_state

Q = 0.5 * 1.225 * 15.0 ** 2
TARGETS = {
    "surface_fw": ("fw", "przednie skrzydło"),
    "surface_rw": ("rw", "tylne skrzydło"),
    "surface_ut": ("ut", "podłoga"),
}


def _bins(centers: np.ndarray, values: dict[str, np.ndarray], pitch: float) -> list[dict]:
    keys = np.floor(centers / pitch).astype(np.int32)
    order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
    keys = keys[order]
    centers = centers[order]
    values = {name: arr[order] for name, arr in values.items()}
    change = np.any(np.diff(keys, axis=0) != 0, axis=1)
    first = np.r_[0, np.flatnonzero(change) + 1]
    ends = np.r_[first[1:], keys.shape[0]]
    width = ends - first
    out = []
    for name in values:
        values[name] = np.add.reduceat(values[name], first) / width
    mean_xyz = np.add.reduceat(centers, first) / width[:, None]
    for i in range(first.size):
        point = {
            "x_m": round(float(mean_xyz[i, 0]), 4),
            "y_m": round(float(mean_xyz[i, 1]), 4),
            "z_m": round(float(mean_xyz[i, 2]), 4),
        }
        for name, arr in values.items():
            point[name] = round(float(arr[i]), 4)
        out.append(point)
    return out


def surface_maps(case: Path, pitch: float = 0.01) -> dict:
    import h5py

    cas = next(case.rglob("*.cas.h5"))
    dat = next(case.rglob("*.dat.h5"))
    surfaces = []
    with h5py.File(cas, "r") as mesh, h5py.File(dat, "r") as data:
        layout = {name: (packed_at, lo, hi) for name, packed_at, lo, hi in checked_layout(mesh, data)}
        for name, (code, label) in TARGETS.items():
            packed_at, min_id, max_id = layout[name]
            state = wall_state(mesh, data, packed_at, min_id, max_id)
            count = max_id - min_id + 1
            centers = state["centers"]
            pressure = state["pressure"]
            yplus = state["yplus"]
            shear = state["tau"]
            shear_mag = np.linalg.norm(shear, axis=1)
            points = _bins(
                centers,
                {
                    "cp": pressure / Q,
                    "cisnienie_Pa": pressure,
                    "yplus": yplus,
                    "naprezenie_x_Pa": shear[:, 0],
                    "naprezenie_Pa": shear_mag,
                },
                pitch,
            )
            surfaces.append(
                {
                    "id": code,
                    "nazwa": label,
                    "strefa": name,
                    "scianek": count,
                    "punktow": len(points),
                    "punkty": points,
                }
            )
    return {
        "opis": (
            "Mapa 3D na powierzchni, nie przekrój przez powietrze. "
            "Każdy punkt to średnia ścianek, których środek wpadł w kostkę 1 cm. "
            "X rośnie do tyłu, Y w bok (ujemne to połowa z symulacji), Z do góry."
        ),
        "skok_m": pitch,
        "parametry": {
            "cp": "współczynnik ciśnienia. Ciśnienie manometryczne z pliku podzielone przez 0.5*1.225*15^2.",
            "cisnienie_Pa": "ciśnienie manometryczne na ściance, paskale.",
            "yplus": "y+ na ściance, bez jednostki.",
            "naprezenie_x_Pa": "składowa X tarcia, które płyn wywiera na ściankę, w paskalach. Dodatnia to normalny przepływ do tyłu auta. Ujemna znaczy, że przepływ przy ścianie jest cofnięty (oderwanie). Liczone z y+ i prędkości przy ścianie, bo zapisane w pliku tarcie ma odwrócony znak i złe jednostki.",
            "naprezenie_Pa": "długość wektora tarcia ścianki, paskale.",
        },
        "powierzchnie": surfaces,
    }


def _along_x(x, z, cp, tau, step: float = 0.004) -> list[dict]:
    if x.size == 0:
        return []
    x0 = float(x.min())
    chord = float(x.max() - x.min()) or 1.0
    bucket = np.floor((x - x0) / step).astype(np.int32)
    order = np.argsort(bucket, kind="stable")
    bucket = bucket[order]
    x, z, cp, tau = x[order], z[order], cp[order], tau[order]
    change = np.diff(bucket) != 0
    first = np.r_[0, np.flatnonzero(change) + 1]
    ends = np.r_[first[1:], bucket.size]
    width = ends - first
    xm = np.add.reduceat(x, first) / width
    zm = np.add.reduceat(z, first) / width
    cpm = np.add.reduceat(cp, first) / width
    taum = np.add.reduceat(tau, first) / width
    rows = []
    for i in range(first.size):
        rows.append(
            {
                "x_m": round(float(xm[i]), 4),
                "z_m": round(float(zm[i]), 4),
                "x_przez_c": round(float((xm[i] - x0) / chord), 3),
                "cp": round(float(cpm[i]), 3),
                "naprezenie_x_Pa": round(float(taum[i]), 3),
            }
        )
    return rows


def _summarize(curve: list[dict]) -> dict:
    if not curve:
        return {}
    peak = min(curve, key=lambda row: row["cp"])
    reversed_rows = [row for row in curve if row["naprezenie_x_Pa"] < 0]
    return {
        "cp_min": peak["cp"],
        "x_cp_min_przez_c": peak["x_przez_c"],
        "udzial_cofniecia": round(len(reversed_rows) / len(curve), 3),
        "cofniecie_od_przez_c": reversed_rows[0]["x_przez_c"] if reversed_rows else None,
    }


def _stations(y: np.ndarray, count: int = 5) -> list[float]:
    side = y[y < -0.02]
    if side.size < 20:
        side = y
    lo, hi = np.quantile(side, [0.12, 0.88])
    return [round(float(v), 3) for v in np.linspace(lo, hi, count)]


def profile_sections(case: Path, band: float = 0.012) -> dict:
    """Full chord at several span stations. Not 1 cm cubes."""
    import h5py

    cas = next(case.rglob("*.cas.h5"))
    dat = next(case.rglob("*.dat.h5"))
    wings = []
    with h5py.File(cas, "r") as mesh, h5py.File(dat, "r") as data:
        layout = {name: (packed_at, lo, hi) for name, packed_at, lo, hi in checked_layout(mesh, data)}
        for name, (code, label) in TARGETS.items():
            packed_at, min_id, max_id = layout[name]
            state = wall_state(mesh, data, packed_at, min_id, max_id)
            centers, nz = state["centers"], state["normal"][:, 2]
            pressure = state["pressure"] / Q
            tau = state["tau"][:, 0]
            cuts = []
            for y0 in _stations(centers[:, 1]):
                sel = np.abs(centers[:, 1] - y0) <= band
                if int(sel.sum()) < 30:
                    continue
                x, z, cp, tx, normal = (
                    centers[sel, 0],
                    centers[sel, 2],
                    pressure[sel],
                    tau[sel],
                    nz[sel],
                )
                if code == "ut":
                    line = _along_x(x, z, cp, tx)
                    cuts.append(
                        {
                            "y_m": y0,
                            "rola": "linia wzdłuż podłogi, od przodu do dyfuzora",
                            "podsumowanie": _summarize(line),
                            "linia": line,
                        }
                    )
                    continue
                lower = _along_x(x[normal <= 0], z[normal <= 0], cp[normal <= 0], tx[normal <= 0])
                upper = _along_x(x[normal > 0], z[normal > 0], cp[normal > 0], tx[normal > 0])
                cuts.append(
                    {
                        "y_m": y0,
                        "rola": "cały profil w tym miejscu rozpiętości",
                        "dol": {
                            "opis": "Strona, której normalna patrzy w dół. Na skrzydle dociskowym to zwykle strona ssąca.",
                            "podsumowanie": _summarize(lower),
                            "przebieg": lower,
                        },
                        "gora": {
                            "opis": "Strona, której normalna patrzy w górę.",
                            "podsumowanie": _summarize(upper),
                            "przebieg": upper,
                        },
                    }
                )
            wings.append({"id": code, "nazwa": label, "strefa": name, "przekroje": cuts})
    return {
        "opis": (
            "Każdy przekrój to wąski pasek w poprzek rozpiętości, a punkty idą wzdłuż cięciwy. "
            "x_przez_c = 0 na początku paska, 1 na końcu. "
            "Ssanie to ujemne cp. Cofnięcie to ujemne tarcie w X: przepływ przy ścianie wraca do przodu, "
            "czyli profil w tym miejscu już nie dokłada docisku tak, jak przyklejony strumień. "
            "To nie jest kostka 1 cm i nie jest ślad w powietrzu za skrzydłem."
        ),
        "szerokosc_paska_m": band * 2,
        "skrzydla": wings,
    }


def write_profiles(case: Path, out: Path) -> dict:
    data = profile_sections(case)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def write_surfaces(case: Path, out: Path, pitch: float = 0.01) -> dict:
    data = surface_maps(case, pitch)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
