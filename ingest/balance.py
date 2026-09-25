"""Front/rear aero load split from the solver's own moment report.

Moment M about centre P along axis a is reported as cm = (M . a) / (q A L_ref).
Moving it to the rear contact patch R and balancing the two axle reactions gives
N_front = M_R,y / (x_front - x_rear). Everything stays in coefficient form, so
q and A cancel and a half model gives the same split as the full car.
"""

from __future__ import annotations

AXIS_TOL = 1e-3


def _is_pitch_axis(axis: list[float] | None) -> float | None:
    if not axis or len(axis) != 3:
        return None
    ax, ay, az = axis
    if abs(ax) > AXIS_TOL or abs(az) > AXIS_TOL or abs(abs(ay) - 1.0) > AXIS_TOL:
        return None
    return 1.0 if ay > 0 else -1.0


def aero_balance(
    *,
    cd: float | None,
    downforce: float | None,
    cm: float | None,
    moment_center_m: list[float] | None,
    moment_axis: list[float] | None,
    moment_scaled: bool | None,
    reference_length_m: float | None,
    front_axle_x_m: float | None,
    rear_axle_x_m: float | None,
    ground_z_m: float | None,
    cx_vector: list[float] | None,
) -> dict:
    """Coefficient-form axle split. Z must point up; downforce is positive down."""
    missing: list[str] = []
    if downforce is None:
        missing.append("docisk z zweryfikowanym znakiem cz")
    if cd is None:
        missing.append("Cd")
    if cm is None:
        missing.append("monitor cm")
    if moment_center_m is None:
        missing.append("punkt momentu cm z case'a")
    sign = _is_pitch_axis(moment_axis)
    if moment_axis is None:
        missing.append("oś momentu cm z case'a")
    elif sign is None:
        missing.append(f"oś momentu {moment_axis} to nie pochylanie (0, ±1, 0)")
    if moment_scaled is False:
        missing.append("cm jest w N·m, nie współczynnikiem")
    if reference_length_m is None:
        missing.append("długość odniesienia")
    if front_axle_x_m is None or rear_axle_x_m is None:
        missing.append("położenie osi kół (X)")
    elif abs(front_axle_x_m - rear_axle_x_m) < 1e-6:
        missing.append("osie kół w tym samym X")
    if downforce is not None and abs(downforce) < 1e-9:
        missing.append("docisk równy zero")
    if missing:
        return {"frontPct": None, "missing": missing}

    ground = 0.0 if ground_z_m is None else ground_z_m
    drag_dir = cx_vector[0] if cx_vector else 1.0
    fx = cd * drag_dir
    fz = -downforce
    xp, _yp, zp = moment_center_m
    moment_rear = sign * cm * reference_length_m + (zp - ground) * fx - (xp - rear_axle_x_m) * fz
    front = moment_rear / (front_axle_x_m - rear_axle_x_m)
    share = front / downforce
    cop_x = rear_axle_x_m + share * (front_axle_x_m - rear_axle_x_m)

    assumptions = []
    if ground_z_m is None:
        assumptions.append("ziemia w Z = 0")
    if not cx_vector:
        assumptions.append("opór wzdłuż +X")
    return {
        "frontPct": round(100.0 * share, 1),
        "rearPct": round(100.0 * (1.0 - share), 1),
        "frontDownforceCoeff": round(front, 4),
        "rearDownforceCoeff": round(downforce - front, 4),
        "copXM": round(cop_x, 4),
        "inputs": {
            "cd": cd,
            "downforceCoeff": downforce,
            "cm": cm,
            "momentCenterM": moment_center_m,
            "momentAxis": moment_axis,
            "referenceLengthM": reference_length_m,
            "frontAxleXM": front_axle_x_m,
            "rearAxleXM": rear_axle_x_m,
            "groundZM": ground,
        },
        "assumptions": assumptions,
        "method": (
            "Moment cm przeniesiony do styku tylnego koła z ziemią, potem równowaga reakcji osi. "
            "Liczone na współczynnikach, więc Aref i połowa modelu się skracają."
        ),
    }
