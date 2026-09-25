from pathlib import Path

import pytest

from ingest.pictures import component_stations, index_pictures
from ingest.rfile import parse_rfile
from ingest.slices import station_m, load_slices
from ingest.transcript import parse_transcript


def test_parse_mesh_transcript(tmp_path: Path):
    p = tmp_path / "mesh.trn"
    p.write_text(
        """
              Welcome to ANSYS Fluent 2023 R1
The octree hexcore cells will be refined using the computed Size Field.
processing scoped prisms...
Stair-stepping of all boundary layers occured at 16 locations
---------------- 11297889 cells were created in : 11.83 minutes
The final minimum Orthogonal Quality is 0.013
The final minimum Orthogonal Quality is 0.150
mrf_fan-body
""",
        encoding="utf-8",
    )
    out = parse_transcript(p)
    assert out["fluentVersion"] == "2023 R1"
    assert out["cells"] == 11_297_889
    assert out["minOrthogonalQuality"] == 0.15
    assert out["hexcore"] is True
    assert out["scopedPrisms"] is True
    assert out["prismStairstepLocations"] == 16
    assert out["mrfFan"] is True


def test_parse_solver_transcript(tmp_path: Path):
    p = tmp_path / "solver.trn"
    p.write_text(
        """
    11315396 cells,     4 cell zones ...
          56102 polygonal symmetry faces,  zone id: 374
            401 polygonal velocity-inlet faces,  zone id: 372
Written y-plus
***Memory allocation failed for gk_mcoremalloc: ptr.
""",
        encoding="utf-8",
    )
    out = parse_transcript(p)
    assert out["cells"] == 11_315_396
    assert out["halfModel"] is True
    assert out["inletFaces"] == 401
    assert out["yPlusExported"] is True
    assert out["memoryFailure"] is True


def test_parse_rfile(tmp_path: Path):
    p = tmp_path / "cx-rfile.out"
    p.write_text(
        '"cx-rfile"\n1 6.8 6.8\n1840 1.186406 1.186578\n',
        encoding="utf-8",
    )
    out = parse_rfile(p)
    assert out["monitor"] == "cx"
    assert out["iterations"] == 1840
    assert abs(out["averaged"] - 1.186406) < 1e-9


def test_transcript_residuals_and_yplus(tmp_path: Path):
    p = tmp_path / "solver.trn"
    p.write_text(
        """
iter continuity x-velocity y-velocity z-velocity k omega time/iter
  10  1.0e-02  1.0e-03  1.0e-03  1.0e-03  1.0e-03  1.0e-03  0:00:01  1
  20  4.2e-05  1.1e-05  1.2e-05  1.3e-05  2.0e-05  3.0e-05  0:00:02  1
area-weighted average of y-plus on surface_fw = 1.8
maximum of y-plus on surface_fw is 4.4
area-weighted average of y-plus on surface_ut = 2.4
""",
        encoding="utf-8",
    )
    out = parse_transcript(p)
    assert out["residuals"]["iteration"] == 20
    assert abs(out["residuals"]["continuity"] - 4.2e-05) < 1e-12
    assert abs(out["residuals"]["omega"] - 3.0e-05) < 1e-12
    assert abs(out["yPlus"]["wings"]["avg"] - 1.8) < 1e-12
    assert abs(out["yPlus"]["wings"]["max"] - 4.4) < 1e-12
    assert abs(out["yPlus"]["floor"]["avg"] - 2.4) < 1e-12


def test_build_pack_keeps_case_numbers(tmp_path: Path):
    from ingest.pack import build_pack

    case = tmp_path / "CASE1"
    (case / "Baseline002 Post pro" / "X" / "CpT").mkdir(parents=True)
    (case / "Baseline002 Post pro" / "X" / "CpT" / "AnimationFrame000001.jpg").write_bytes(b"x")
    (case / "fluent-20260101-000000-.trn").write_text(
        """
              Welcome to ANSYS Fluent 2023 R1
    11315396 cells,     4 cell zones ...
          56102 polygonal symmetry faces,  zone id: 374
iter continuity x-velocity y-velocity z-velocity k omega time/iter
  20  4.2e-05  1.0e-05  1.0e-05  1.0e-05  2.0e-05  3.0e-05  0:00:02  1
area-weighted average of y-plus on surface_fw = 1.8
area-weighted average of y-plus on surface_ut = 2.4
""",
        encoding="utf-8",
    )
    (case / "cx-rfile.out").write_text('"cx-rfile"\n20 1.20 1.21\n', encoding="utf-8")
    (case / "cz-rfile.out").write_text('"cz-rfile"\n20 3.10 3.11\n', encoding="utf-8")
    (case / "setup.cas").write_text(
        '(monitor/report-definitions (((name . "cx") (report-definition drag (force-vector 1. 0. 0.) '
        '(per-zone? . #f) (type "drag"))) ((name . "cz") (report-definition lift '
        '(force-vector 0. 0. -1.) (per-zone? . #f) (type "lift"))))',
        encoding="utf-8",
    )
    (case / "geometry.yaml").write_text(
        """
vehicle:
  name: TESTCAR
  frontalAreaM2: 0.42
  frontalAreaBasis: half
  wheelbaseMm: 1530
  speedMs: 20
devices:
  - id: fw-main
    chordMm: 200
    profile: TBD
""",
        encoding="utf-8",
    )
    pack = build_pack(case, tmp_path / "out")
    assert pack["identity"]["vehicle"] == "TESTCAR"
    assert pack["identity"]["speedMs"] == 20
    assert pack["kpis"]["frontalAreaM2"] == 0.42
    assert pack["kpis"]["Cd"] == 1.20
    assert abs(pack["kpis"]["Cl"] + 3.10) < 1e-9
    assert abs(pack["monitors"]["residuals"]["continuity"] - 4.2e-05) < 1e-12
    assert abs(pack["monitors"]["yPlus"]["wings"]["avg"] - 1.8) < 1e-12
    assert pack["geometry"]["deviceCount"] == 1
    assert pack["geometry"]["status"] == "1 karta, 1 z cięciwą, 1 profil TBD"
    assert pack["kpis"]["references"]["frontalAreaM2"]["source"] == "geometry.yaml"
    assert pack["kpis"]["references"]["speedMs"]["source"] == "geometry.yaml"
    assert any("assumed-air" in warning for warning in pack["warnings"])
    assert "0.42" in pack["notesForAgent"][0]
    assert "0.5 m²" not in pack["notesForAgent"][0]
    assert "20" in pack["notesForAgent"][0]
    assert "vehicle-filled, devices TBD" not in pack["geometry"]["status"]


def test_chord_from_two_ends():
    from ingest.cad_measure import _chord_from_points

    pts = [(-100.0, 10.0), (-90.0, 9.0), (0.0, 8.0), (200.0, 5.0), (199.0, 6.0)]
    chord = _chord_from_points(pts)
    assert chord is not None
    assert chord["le"]["xMm"] == -100.0
    assert chord["te"]["xMm"] == 200.0
    assert chord["chordMm"] > 299


def test_picture_index_from_cfdpost_layout(tmp_path: Path):
    rels = [
        "Baseline002 Post pro/X/CpT/AnimationFrame000020.jpg",
        "Baseline002 Post pro/X/CpT/AnimationFrame000080.jpg",
        "Baseline002 Post pro/Y/Velocity/AnimationFrame000001.jpg",
        "Baseline002 Post pro/Z/CpT/AnimationFrame000010.jpg",
        "Baseline002 Post pro/Surface/y_plus/y_plus_1.jpg",
        "Baseline002 Post pro/Surface/Cp/Cp_1.jpg",
    ]
    for rel in rels:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    out = index_pictures(tmp_path, rels)
    assert out["total"] == 6
    assert out["stationEncoded"] is True
    assert out["byAxis"]["x"] == 2
    x20 = next(e for e in out["index"] if "000020" in e["filename"])
    assert x20["stationM"] is not None
    heroes = [e for e in out["index"] if e["hero"]]
    assert any(e["field"] == "yplus" for e in heroes)
    assert any(e["axis"] == "x" and e["field"] == "cpt" for e in heroes)


def test_component_stations_use_group_envelope():
    stations = component_stations(
        {
            "devices": [
                {"group": "front-wing", "le": {"xMm": -100}, "te": {"xMm": 50}},
                {"group": "front-wing", "le": {"xMm": -200}, "te": {"xMm": 80}},
                {"group": "body", "le": {"xMm": 0}, "te": {"xMm": 1000}},
            ]
        }
    )
    assert [s["component"] for s in stations] == ["FW"]
    fw = stations[0]
    assert fw["xMinM"] == -0.2
    assert fw["xMaxM"] == 0.08
    features = {t["feature"]: t["xM"] for t in fw["targets"]}
    assert features["leading_edge"] == -0.2
    assert features["mid_chord"] == -0.06
    assert features["trailing_edge_wake"] == 0.13


def test_x_heroes_follow_geometry_features(tmp_path: Path):
    slices = {
        "x": {"startM": 0.0, "endM": 1.0},
        "y": {"startM": 0.0, "endM": 1.0},
        "z": {"startM": 0.0, "endM": 1.0},
    }
    rels = [f"Post/X/CpT/AnimationFrame{i:06d}.jpg" for i in range(1, 12)]
    for rel in rels:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    geometry = {
        "devices": [
            {"group": "front-wing", "le": {"xMm": 0}, "te": {"xMm": 180}},
            {"group": "floor", "le": {"xMm": 400}, "te": {"xMm": 620}},
            {"group": "rear-wing", "le": {"xMm": 800}, "te": {"xMm": 1000}},
        ]
    }
    out = index_pictures(tmp_path, rels, slices, geometry)
    tagged = {
        (e["component"], e["feature"]): e["stationM"]
        for e in out["index"]
        if e.get("component")
    }
    assert tagged[("FW", "leading_edge")] == 0.0
    assert tagged[("FW", "mid_chord")] == 0.1
    assert tagged[("FW", "trailing_edge_wake")] == 0.2
    assert tagged[("Floor", "leading_edge")] == 0.4
    assert tagged[("Floor", "mid_chord")] == 0.5
    assert tagged[("Floor", "trailing_edge_wake")] == 0.7
    assert tagged[("RW", "leading_edge")] == 0.8
    assert tagged[("RW", "mid_chord")] == 0.9
    assert tagged[("RW", "trailing_edge_wake")] == 1.0
    assert all(e["hero"] and e["axis"] == "x" and e["field"] == "cpt" for e in out["index"] if e.get("feature"))


def test_x_slice_range_from_postpro_script():
    slices = load_slices()
    assert station_m("x", 1, 150, slices) == -1.1
    assert station_m("x", 150, 150, slices) == 2.5
    assert station_m("y", 1, 150, slices) == -0.01
    assert station_m("z", 1, 150, slices) == 0.0
    assert station_m("z", 150, 150, slices) == 1.5
    assert slices["fields"]["vel"]["kind"] == "V/Vinf"
    assert slices["fields"]["cpt"]["legend"] == [-1.0, 1.0]


def test_cas_force_vector_from_scheme():
    from ingest.cas_setup import parse_report_blob
    from ingest.pack import interpret_kpis

    blob = (
        '(monitor/report-definitions ('
        '((name . "cx") (report-definition drag (force-vector 1. 0. 0.) '
        '(thread-names surface_fw surface_rw surface_ut) (per-zone? . #f) '
        '(scaled? . #t) (type "drag"))) '
        '((name . "cz") (report-definition lift (force-vector 0. 0. -1.) '
        '(thread-names surface_fw surface_rw surface_ut) (per-zone? . #f) '
        '(scaled? . #t) (type "lift"))))'
    )
    parsed = parse_report_blob(blob)
    assert parsed["reports"]["cx"]["forceVector"] == [1.0, 0.0, 0.0]
    assert parsed["reports"]["cz"]["forceVector"] == [0.0, 0.0, -1.0]
    assert parsed["reports"]["cz"]["positiveMeans"] == "downforce"
    assert parsed["reports"]["cz"]["perZone"] is False
    kpis, warns = interpret_kpis(1.186, 3.677, 0.1, {
        "verified": True,
        "czPositiveMeans": "downforce",
        "cxForceVector": [1.0, 0.0, 0.0],
        "czForceVector": [0.0, 0.0, -1.0],
        "source": "fixture.cas",
    })
    assert warns == []
    assert kpis["downforceCoeff"] == 3.677
    assert abs(kpis["Cl"] + 3.677) < 1e-9
    assert kpis["forceVectorVerified"] is True


def test_wall_force_groups_skip_tunnel():
    from ingest.wall_forces import parse_force_report, group_zones

    text = """
Forces - Direction Vector (0 0 -1)
Zone                 Pressure Viscous Total Pressure Viscous Total
surface_fw           10 1 11 1.0 0.1 1.1
surface_rw           20 2 22 2.0 0.2 2.2
surface_ut           5 0.5 5.5 0.5 0.05 0.55
domain_ground        8 0 8 0.8 0 0.8
Net                  43 3.5 46.5 4.3 0.35 4.65
"""
    grouped = group_zones(parse_force_report(text))
    assert grouped["direction"] is None or grouped["format"] in {"scalar", "vector"}
    assert grouped["groups"]["fw"]["C_total"] == 1.1
    assert grouped["groups"]["rw"]["C_total"] == 2.2
    assert grouped["groups"]["floor"]["C_total"] == 0.55
    assert "tunnel" not in grouped["groups"]
    assert "domain_ground" in grouped["excluded"]
    assert abs(grouped["vehicle"]["C_total"] - 3.85) < 1e-9


def test_vector_dump_checksum_and_shares():
    from ingest.wall_forces import parse_force_report, group_zones, attach_shares

    text = """
Forces
Zone Pressure Viscous Total Pressure Viscous Total
surface_fw (1 0 -10) (0.1 0 0) (1.1 0 -10) (0.2 0 -1.5) (0.01 0 0) (0.21 0 -1.5)
surface_rw (2 0 -5) (0.2 0 0) (2.2 0 -5) (0.4 0 -0.8) (0.02 0 0) (0.42 0 -0.8)
surface_ut (0.5 0 -2) (0.05 0 0) (0.55 0 -2) (0.1 0 -0.3) (0.005 0 0) (0.105 0 -0.3)
domain_ground (0 0 20) (0 0 0) (0 0 20) (0 0 3) (0 0 0) (0 0 3)
Net (3.6 0 3) (0.35 0 0) (3.95 0 3) (0.7 0 0.4) (0.035 0 0) (0.735 0 0.4)
"""
    grouped = attach_shares(group_zones(parse_force_report(text)), cd_total=0.735, cl_total=-2.6, downforce_total=2.6)
    assert grouped["checksum"]["ok"] is True
    assert grouped["groups"]["fw"]["shareDownforcePct"] is not None
    assert abs(sum(g["shareDragPct"] for g in grouped["groups"].values()) - 100) < 0.05
    assert "domain_ground" in grouped["excluded"]


def test_postpro_station_lands_on_car_parts():
    from ingest.car_layout import parts_at, segments_along_x, stamp_frames

    floor = {
        "id": "floor",
        "onCar": True,
        "bboxMm": {"xmin": 200, "xmax": 1200, "ymin": -600, "ymax": -150, "zmin": -20, "zmax": 400},
    }
    wing = {
        "id": "fw",
        "onCar": True,
        "bboxMm": {"xmin": -900, "xmax": -300, "ymin": -600, "ymax": 0, "zmin": 40, "zmax": 120},
    }
    mesh = {
        "id": "box",
        "onCar": False,
        "bboxMm": {"xmin": -1000, "xmax": 2000, "ymin": -800, "ymax": 0, "zmin": 0, "zmax": 800},
    }
    assert parts_at([floor, wing, mesh], "x", 0.5) == ["floor"]
    assert parts_at([floor, wing, mesh], "x", -0.5) == ["fw"]
    assert parts_at([floor, wing], "z", 0.05) == ["floor", "fw"]
    segments = segments_along_x([floor, wing])
    assert segments[0]["partIds"] == ["fw"]
    assert "floor" in segments[-1]["partIds"]
    frame = {"axis": "x", "stationM": 0.5}
    surface = {"axis": "full", "stationM": None}
    stamp_frames([frame, surface], [floor, wing, mesh])
    assert frame["onCar"] == ["floor"]
    assert surface["where"].startswith("cały bolid")


def test_step_card_sets_hero_from_this_chord():
    from ingest.pictures import component_stations
    from ingest.step_cards import card_from_measure

    card = card_from_measure(
        "PM09-A-FW-Main_Profile-CFD",
        {
            "bboxMm": {
                "xmin": -902, "xmax": -462, "ymin": -637, "ymax": 0,
                "zmin": 41, "zmax": 114, "dx": 440, "dy": 637, "dz": 73,
            },
            "sectionYMm": -318.5,
            "sectionLoops": [[[-900.0, 86.0], [-567.0, 85.0]]],
            "chord": {
                "chordMm": 333.0,
                "incidenceDeg": -0.3,
                "le": {"xMm": -900.0, "zMm": 86.0},
                "te": {"xMm": -567.0, "zMm": 85.0},
            },
        },
    )
    assert card is not None
    assert card["profile"] != "TBD"
    assert card["sectionMm"]
    stations = component_stations({"devices": [card]})
    features = {item["feature"]: item["xM"] for item in stations[0]["targets"]}
    assert features["leading_edge"] == -0.9


def test_ground_layer_without_first_height(tmp_path: Path):
    from ingest.wft_mesh import ground_layer_warnings, parse_wft

    path = tmp_path / "mesh.wft"
    path.write_text(
        """
        {"workflow": {"version": "23.1", "ROOT": {
          "a": {"_name_": "uniform_1", "State": "Out-of-date", "Arguments": {
            "BLControlName": "uniform_1", "NumberOfLayers": "15",
            "FirstHeight": "2e-05", "BLZoneList": ["surface_fw"]
          }},
          "b": {"_name_": "uniform_2", "State": "Out-of-date", "Arguments": {
            "BLControlName": "uniform_2", "NumberOfLayers": "4",
            "BLZoneList": ["domain_ground"]
          }}
        }}}
        """,
        encoding="utf-8",
    )
    parsed = parse_wft(path)
    assert parsed["boundaryLayers"][0]["firstHeightM"] == 2e-05
    assert parsed["boundaryLayers"][1]["firstHeightM"] is None
    text = " ".join(ground_layer_warnings(parsed))
    assert "domain_ground" in text
    assert "FirstHeight" in text


def test_diff_reports_shared_component_only():
    from ingest.diff_pack import diff_packs

    base = {
        "identity": {"caseId": "baza"},
        "kpis": {
            "Cd": 1.2,
            "Cl": -3.0,
            "LOverD": 2.5,
            "cm": -0.4,
            "cz": 3.0,
            "references": {"referenceLengthM": {"value": 1.53}},
            "components": {"groups": {"fw": {"Cd": 0.2, "downforceCoeff": 1.0}, "rw": {"Cd": 0.4, "downforceCoeff": 1.2}}},
        },
    }
    new = {
        "identity": {"caseId": "nowa"},
        "kpis": {
            "Cd": 1.3,
            "Cl": -3.4,
            "LOverD": 2.6,
            "cm": -0.5,
            "cz": 3.4,
            "references": {"referenceLengthM": {"value": 1.53}},
            "components": {"groups": {"fw": {"Cd": 0.25, "downforceCoeff": 1.12}}},
        },
    }
    out = diff_packs(base, new)
    assert out["delta_cd"] == 0.1
    assert out["delta_cl"] == -0.4
    assert [item["nazwa"] for item in out["komponenty"]] == ["fw"]
    assert out["komponenty"][0]["delta_docisk"] == 0.12
    assert out["przesuniecie_srodka_parcia_m"] is not None


def test_vortex_core_follows_rotating_low_pressure():
    import numpy as np

    from ingest.field_grid import vortex_from_samples

    y = [0.0, 0.04, 0.0, -0.04, 0.0]
    z = [0.0, 0.0, 0.04, 0.0, -0.04]
    cp = [-2.0, -0.4, -0.4, -0.4, -0.4]
    # extra ring points so the count clears the threshold
    for ang in range(8):
        radius = 0.04
        yy = radius * np.cos(ang)
        zz = radius * np.sin(ang)
        y.append(float(yy))
        z.append(float(zz))
        cp.append(-0.5)
    y = np.array(y)
    z = np.array(z)
    cp = np.array(cp)
    radius = np.hypot(y, z)
    safe = np.where(radius == 0, 1.0, radius)
    vy = -z / safe
    vz = y / safe
    core = vortex_from_samples(y, z, cp, vy, vz, box=(-0.2, 0.2, -0.2, 0.2))
    assert core["znaleziony"] is True
    assert core["y_m"] == 0.0
    assert core["cp"] == -2.0
    assert core["kreci_sie"] is True


def test_chord_curve_marks_reversed_shear():
    import numpy as np

    from ingest.surface_field import _along_x, _summarize

    curve = _along_x(
        np.array([0.0, 0.03, 0.06, 0.09]),
        np.array([0.1, 0.1, 0.1, 0.1]),
        np.array([-2.0, -1.0, -0.4, -0.2]),
        np.array([1.0, 0.2, -0.3, -0.5]),
        step=0.02,
    )
    summary = _summarize(curve)
    assert summary["cp_min"] == -2.0
    assert summary["x_cp_min_przez_c"] == 0.0
    assert summary["udzial_cofniecia"] > 0


def test_bin_means_average_two_points_in_one_cell():
    import numpy as np

    from ingest.field_grid import bin_means

    grid = bin_means(
        np.array([0.01, 0.02]),
        np.array([0.01, 0.015]),
        np.array([2.0, 4.0]),
        0.05,
    )
    assert grid["rows"] == [[3.0]]


def test_colourbar_pixel_becomes_scale_min(tmp_path: Path):
    import numpy as np
    from PIL import Image

    from ingest.screen_quant import quantify_image

    rgb = np.zeros((120, 200, 3), dtype=np.uint8)
    rgb[:] = 255
    # vertical bar, top red = max, bottom blue = min
    for i, y in enumerate(range(20, 100)):
        t = i / 79
        rgb[y, 12:20] = (int(200 * (1 - t)), 0, int(200 * t))
    # a patch of the bottom colour in the plot
    rgb[40:80, 80:140] = (0, 0, 200)
    path = tmp_path / "frame.jpg"
    Image.fromarray(rgb).save(path)
    row = quantify_image(path, "cpt", "x", 1, 2)
    assert row is not None
    assert row["mean"] < -0.5


def test_setup_trace_keeps_values_not_a_journal(tmp_path: Path):
    from ingest.setup_trace import extract_setup_trace

    path = tmp_path / "fluent.trn"
    path.write_text(
        """
> /define/boundary-conditions/wall domain_ground
> /define/boundary-conditions/wall domain_ground
(cx-gui-do cx-set-real-entry-list "Reference Values*RealEntry8(Velocity)" '( 15))
(cx-gui-do cx-set-toggle-button2 "Viscous Model*k-omega (2 eqn)" #t)
""",
        encoding="utf-8",
    )
    trace = extract_setup_trace(path)
    assert trace["tui"] == ["/define/boundary-conditions/wall domain_ground"]
    assert any(item.startswith("Velocity") for item in trace["values"])
    assert "k-omega (2 eqn)" in trace["models"]


# Fragments copied from Baseline002.cas.h5 /settings (Rampant + Thread Variables).
CASE_SETTINGS = (
    '0.6786817908287048))))) (monitor/report-definitions (((name . "cm") (report-definition moment '
    '(mom-center 0.765 0. 0.) (mom-axis 0. 1. 0.) (reference-frame . "global") (old-props mom-center '
    '(0.765 0. 0.) mom-axis (0. 1. 0.) reference-frame "global" per-zone? #f average-over 100 '
    'thread-names (surface_fw surface_rw surface_ut) header "" scaled? #t name "cm" type "moment") '
    '(per-zone? . #f) (scaled? . #t))) ((name . "cx") (report-definition drag (force-vector 1. 0. 0.) '
    '(per-zone? . #f) (type "drag"))) ((name . "cz") (report-definition lift (force-vector 0. 0. -1.) '
    '(old-props force-vector (0. 0. -1.) name "cz" type "lift") (per-zone? . #f) (scaled? . #t))))\n'
    "(reference-velocity 15.)\n(reference-length 1.529999971389771)\n(reference-density 1.225)\n"
    "(reference-viscosity 1.7894e-05)\n(reference-area 0.4940756857395172)\n"
    "(39 (377 wall surface_front_wheel-steady 1)(  (rotating? . #f)  (omega . 0)  (x-origin . 0) ))\n"
    "(39 (378 wall surface_front_wheel-rotary 1)(  (rotating? . #t)  (omega . -72.90000000000001)  "
    "(x-origin . 0.)  (y-origin . -0.7)  (z-origin . 0.20574)  (ai . 0)  (aj . 1)  (ak . 0) ))\n"
    "(39 (379 wall surface_rear_wheel-rotary 1)(  (rotating? . #t)  (omega . -72.90000000000001)  "
    "(x-origin . 1.53)  (y-origin . -0.7)  (z-origin . 0.20574)  (ai . 0)  (aj . 1)  (ak . 0) ))\n"
)


def test_case_settings_give_moment_references_and_wheels():
    from ingest.cas_setup import parse_settings_text

    out = parse_settings_text(CASE_SETTINGS)
    cm = out["reports"]["cm"]
    assert cm["type"] == "moment"
    assert cm["momentCenterM"] == [0.765, 0.0, 0.0]
    assert cm["momentAxis"] == [0.0, 1.0, 0.0]
    assert cm["scaled"] is True
    assert out["reports"]["cz"]["forceVector"] == [0.0, 0.0, -1.0]
    assert abs(out["references"]["lengthM"] - 1.53) < 1e-6
    assert abs(out["references"]["areaM2"] - 0.49407) < 1e-5
    assert out["references"]["velocityMs"] == 15.0
    assert set(out["wheels"]) == {"front", "rear"}
    assert out["wheels"]["front"]["zone"] == "surface_front_wheel-rotary"
    assert out["wheels"]["front"]["originM"] == [0.0, -0.7, 0.20574]
    assert out["wheels"]["rear"]["originM"][0] == 1.53


def test_cas_h5_settings_are_read_without_the_mesh(tmp_path: Path):
    h5py = pytest.importorskip("h5py")
    import numpy as np

    from ingest.cas_setup import parse_cas_setup

    path = tmp_path / "case.cas.h5"
    rampant, threads = CASE_SETTINGS.split("(39 ", 1)
    with h5py.File(path, "w") as handle:
        settings = handle.create_group("settings")
        settings.create_dataset("Rampant Variables", data=np.array([rampant.encode()]))
        settings.create_dataset("Thread Variables", data=np.array([("(39 " + threads).encode()]))
    out = parse_cas_setup([path])
    assert out["verified"] is True
    assert out["czPositiveMeans"] == "downforce"
    assert out["reports"]["cm"]["momentCenterM"] == [0.765, 0.0, 0.0]
    assert out["referencesSource"] == "case.cas.h5"
    assert out["wheels"]["rear"]["originM"][0] == 1.53


def test_gzipped_ascii_case_is_decompressed(tmp_path: Path):
    import gzip

    from ingest.cas_setup import parse_cas_setup

    path = tmp_path / "case.cas.gz"
    with gzip.open(path, "wt", encoding="latin1") as handle:
        handle.write(CASE_SETTINGS)
    out = parse_cas_setup([path])
    assert out["verified"] is True
    assert out["reports"]["cm"]["momentAxis"] == [0.0, 1.0, 0.0]


def test_balance_from_baseline002_moment():
    from ingest.balance import aero_balance

    # Baseline002 monitors after 1840 iterations; cm about x=0.765 m, axis +Y, L_ref = wheelbase.
    out = aero_balance(
        cd=1.186406,
        downforce=3.677229,
        cm=-0.6699572,
        moment_center_m=[0.765, 0.0, 0.0],
        moment_axis=[0.0, 1.0, 0.0],
        moment_scaled=True,
        reference_length_m=1.53,
        front_axle_x_m=0.0,
        rear_axle_x_m=1.53,
        ground_z_m=0.0,
        cx_vector=[1.0, 0.0, 0.0],
    )
    # centre at mid-wheelbase on the ground: front share = 0.5 - cm / downforce
    assert out["frontPct"] == round(100 * (0.5 + 0.6699572 / 3.677229), 1) == 68.2
    assert abs(out["frontDownforceCoeff"] + out["rearDownforceCoeff"] - 3.677229) < 1e-3
    assert out["assumptions"] == []


def test_balance_point_load_on_front_axle_is_all_front():
    from ingest.balance import aero_balance

    # 2.0 downforce exactly on the front axle, moment taken about a raised point behind it
    xp, zp, cd, df = 0.9, 0.3, 1.0, 2.0
    cm_times_l = (0.0 - xp) * df + (0.2 - zp) * cd  # drag acting at z = 0.2 m
    out = aero_balance(
        cd=cd,
        downforce=df,
        cm=cm_times_l / 1.5,
        moment_center_m=[xp, 0.0, zp],
        moment_axis=[0.0, 1.0, 0.0],
        moment_scaled=True,
        reference_length_m=1.5,
        front_axle_x_m=0.0,
        rear_axle_x_m=1.5,
        ground_z_m=0.0,
        cx_vector=[1.0, 0.0, 0.0],
    )
    # drag 0.2 m above the ground unloads the front by cd * 0.2 / wheelbase
    expected_front = df - cd * 0.2 / 1.5
    assert abs(out["frontDownforceCoeff"] - expected_front) < 1e-4


def test_balance_refuses_yaw_axis_and_missing_axles():
    from ingest.balance import aero_balance

    out = aero_balance(
        cd=1.2,
        downforce=3.6,
        cm=-0.6,
        moment_center_m=[0.765, 0.0, 0.0],
        moment_axis=[0.0, 0.0, 1.0],
        moment_scaled=True,
        reference_length_m=1.53,
        front_axle_x_m=None,
        rear_axle_x_m=None,
        ground_z_m=None,
        cx_vector=None,
    )
    assert out["frontPct"] is None
    assert any("pochylanie" in item for item in out["missing"])
    assert any("osi kół" in item for item in out["missing"])


def test_transcript_flags_divergence_and_crash(tmp_path: Path):
    p = tmp_path / "fluent-20260920-203616-5464.trn"
    p.write_text(
        """
  iter  continuity  x-velocity  y-velocity  z-velocity           k       omega          cx          cz          cm     time/iter

WARNING: The wall motion has a significant normal component on 3325 faces of face zone 283.
Divergence detected in AMG solver: pressure correction        Stabilizing k to enhance linear solver robustness.
Divergence detected in AMG solver: k        Stabilizing omega to enhance linear solver robustness.
Divergence detected in AMG solver: pressure correction
Error at host: floating point exception
=   BAD TERMINATION OF ONE OF YOUR APPLICATION PROCESSES
""",
        encoding="utf-8",
    )
    health = parse_transcript(p)["solverHealth"]
    assert health["crashed"] is True
    assert health["crashReasons"] == ["floating point exception"]
    assert health["divergence"] == {"pressure correction": 2, "k": 1}
    assert health["wallMotionNormal"] == [{"faces": 3325, "zoneId": 283}]


def test_build_pack_balance_from_case_settings(tmp_path: Path):
    from ingest.pack import build_pack

    case = tmp_path / "CASE2"
    case.mkdir()
    (case / "setup.cas").write_text(CASE_SETTINGS, encoding="utf-8")
    (case / "cx-rfile.out").write_text('"cx-rfile"\n1840 1.186406 1.186578\n', encoding="utf-8")
    (case / "cz-rfile.out").write_text('"cz-rfile"\n1840 3.677229 3.677\n', encoding="utf-8")
    (case / "cm-rfile.out").write_text('"cm-rfile"\n1840 -0.6699572 -0.67\n', encoding="utf-8")
    (case / "geometry.yaml").write_text(
        "vehicle:\n  name: PM09\n  frontalAreaM2: 0.5\n  frontAxleXMm: 35\n  rearAxleXMm: 1585\n",
        encoding="utf-8",
    )
    pack = build_pack(case, tmp_path / "out")
    refs = pack["kpis"]["references"]
    assert refs["frontalAreaM2"]["source"] == "case:setup.cas"
    assert abs(refs["frontalAreaM2"]["value"] - 0.49407) < 1e-5
    assert abs(refs["referenceLengthM"]["value"] - 1.53) < 1e-6
    balance = pack["kpis"]["aeroBalance"]
    assert balance["frontPct"] == 68.2
    assert balance["sources"]["axles"].startswith("case:setup.cas")
    assert balance["inputs"]["groundZM"] == 0.0
    assert pack["methods"]["wheelRotation"]["front"]["omegaRadS"] == -72.9
    assert not any(w.startswith("Balans aero niepoliczony") for w in pack["warnings"])

