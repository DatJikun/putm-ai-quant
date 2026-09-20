from pathlib import Path

from ingest.pictures import index_pictures
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

