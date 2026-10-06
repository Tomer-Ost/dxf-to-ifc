import csv
import io
import sys
from pathlib import Path

import ezdxf
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.dxf_reader import analyze, load_elements, read_dxf  # noqa: E402
from app.ifc_builder import ItemOverride, LayerSpec, build_ifc  # noqa: E402
from app.main import app  # noqa: E402
from app.report import write_csv  # noqa: E402
from make_sample import make_sample  # noqa: E402

SPECS = [
    LayerSpec("A-WALL", "IfcWall", height=3000, width=200),
    LayerSpec("A-COLUMN", "IfcColumn", height=3000),
    LayerSpec("A-DOOR", "IfcDoor", height=2100, width=900, length=100),
    LayerSpec("A-WINDOW", "IfcWindow", height=1200, width=150, length=1000),
    LayerSpec("A-SLAB", "IfcSlab", height=250),
]


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    return make_sample(tmp_path_factory.mktemp("dxf") / "plan.dxf")


def test_analyze_lists_layers_and_counts(sample):
    info = analyze(read_dxf(sample))
    layers = {l["name"]: l for l in info["layers"]}
    assert info["unit"] == "mm"
    assert layers["A-WALL"]["counts"] == {"lines": 3, "closed": 1, "circles": 0, "blocks": 0}
    assert layers["A-COLUMN"]["counts"] == {"lines": 0, "closed": 4, "circles": 1, "blocks": 0}
    assert layers["A-DOOR"]["counts"]["blocks"] == 3
    doors = info["preview"]["A-DOOR"]["items"]
    assert len(doors) == 3 and all(d["kind"] == "block" and d["paths"] for d in doors), "block contents are previewed"
    assert info["preview"]["A-ANNO"] == {"items": [], "other": []}  # text is ignored entirely
    assert info["extents"][2] >= 12000


def test_build_ifc_creates_typed_elements_with_geometry(sample, tmp_path):
    result = build_ifc(load_elements(sample), SPECS, unit="mm")
    assert result.created == {"A-WALL": 7, "A-COLUMN": 5, "A-DOOR": 3, "A-WINDOW": 2, "A-SLAB": 1}
    assert not result.warnings

    out = tmp_path / "out.ifc"
    result.model.write(str(out))
    model = ifcopenshell.open(str(out))
    assert len(model.by_type("IfcWall")) == 7  # 4 sides of the closed outline + 2 lines + arc
    assert len(model.by_type("IfcDoor")) == 3
    assert model.by_type("IfcSIUnit")[0].Prefix == "MILLI"

    door = model.by_type("IfcDoor")[0]
    assert door.OverallHeight == 2100
    psets = ifcopenshell.util.element.get_psets(door)
    assert psets["DXF_Source"]["Layer"] == "A-DOOR"
    assert psets["DXF_Source"]["BlockName"] == "DOOR_900"
    assert psets["DXF_Dimensions"]["Height"] == 2100
    assert ifcopenshell.util.element.get_container(door).Name == "Level 0"

    # Every product must tessellate, i.e. viewers can actually display it.
    settings = ifcopenshell.geom.settings()
    for product in model.by_type("IfcBuildingElement"):
        shape = ifcopenshell.geom.create_shape(settings, product)
        assert len(shape.geometry.verts) > 0, product


def test_slab_volume_matches_inputs(sample):
    result = build_ifc(load_elements(sample), [LayerSpec("A-SLAB", "IfcSlab", height=250)], unit="mm")
    settings = ifcopenshell.geom.settings()
    shape = ifcopenshell.geom.create_shape(settings, result.model.by_type("IfcSlab")[0])
    zs = shape.geometry.verts[2::3]
    # geometry is reported in metres
    assert max(zs) - min(zs) == pytest.approx(0.25)


def test_missing_width_is_reported_not_fatal(sample):
    result = build_ifc(load_elements(sample), [LayerSpec("A-WALL", "IfcWall", height=3000)], unit="mm")
    assert result.created["A-WALL"] == 0
    assert result.skipped["A-WALL"] == 7
    assert "width required" in result.warnings[0]


def test_open_polyline_is_exploded_into_segments(tmp_path):
    doc = ezdxf.new()
    # 3 segments: straight, bulge arc, straight
    doc.modelspace().add_lwpolyline(
        [(0, 0, 0, 0, 0), (4000, 0, 0, 0, 0.5), (4000, 3000, 0, 0, 0), (0, 3000, 0, 0, 0)],
        format="xyseb",
        dxfattribs={"layer": "W"},
    )
    path = tmp_path / "open.dxf"
    doc.saveas(path)

    elements = load_elements(path)
    assert [e.segment for e in elements] == [1, 2, 3]
    assert analyze(read_dxf(path))["layers"][0]["counts"]["lines"] == 3

    result = build_ifc(elements, [LayerSpec("W", "IfcWall", height=3000, width=200, length=1000)])
    walls = result.model.by_type("IfcWall")
    assert len(walls) == 3
    assert [ifcopenshell.util.element.get_psets(w)["DXF_Source"]["Segment"] for w in walls] == [1, 2, 3]
    # length overrides each straight segment individually; the arc keeps its drawn shape
    settings = ifcopenshell.geom.settings()
    first = ifcopenshell.geom.create_shape(settings, walls[0]).geometry.verts
    xs = first[0::3]
    assert max(xs) - min(xs) == pytest.approx(1.0)  # metres


def test_closed_polyline_stays_whole_for_slabs(sample):
    result = build_ifc(load_elements(sample), [LayerSpec("A-WALL", "IfcSlab", height=200)])
    assert result.created["A-WALL"] == 1  # only the closed outline makes a footprint
    assert result.skipped["A-WALL"] == 3  # 2 lines + arc have no width


def test_preview_item_ids_match_converter_ids(sample):
    info = analyze(read_dxf(sample))
    preview_ids = {it["id"] for layer in info["preview"].values() for it in layer["items"]}
    assert preview_ids == {el.id for el in load_elements(sample)}
    outline = next(it for it in info["preview"]["A-WALL"]["items"] if it["kind"] == "outline")
    assert len(outline["segments"]) == 4  # sides offered individually when the class is IfcWall


def test_item_overrides_and_exclusion(sample):
    elements = [e for e in load_elements(sample) if e.layer == "A-WALL"]
    line_a, line_b = [e for e in elements if e.dxf_type == "LINE"]
    outline = next(e for e in elements if e.closed)
    spec = LayerSpec(
        "A-WALL",
        "IfcWall",
        height=3000,
        width=200,
        overrides={
            line_a.id: ItemOverride(include=False),
            line_b.id: ItemOverride(width=300, height=2500),
            f"{outline.id}:2": ItemOverride(include=False),  # drop one side of the closed outline
        },
    )
    result = build_ifc(elements, [spec])
    assert result.created["A-WALL"] == 7 - 2

    dims = {
        ifcopenshell.util.element.get_psets(w)["DXF_Source"]["Handle"]: ifcopenshell.util.element.get_psets(w)["DXF_Dimensions"]
        for w in result.model.by_type("IfcWall")
    }
    assert line_a.handle not in dims
    assert dims[line_b.handle] == {**dims[line_b.handle], "Width": 300, "Height": 2500}


def test_csv_report_rows(sample, tmp_path):
    elements = load_elements(sample)
    line_a, line_b = [e for e in elements if e.layer == "A-WALL" and e.dxf_type == "LINE"]
    specs = [
        LayerSpec(
            "A-WALL",
            "IfcWall",
            height=3000,
            width=200,
            overrides={line_a.id: ItemOverride(include=False), line_b.id: ItemOverride(width=300)},
        ),
        LayerSpec("A-DOOR", "IfcDoor", height=2100),  # no width -> skipped
    ]
    result = build_ifc(elements, specs)
    out = tmp_path / "r.csv"
    write_csv(result.rows, "mm", out)
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))

    walls = [r for r in rows if r["Layer"] == "A-WALL"]
    assert [r["#"] for r in walls] == [str(i) for i in range(1, 8)]  # matches the viewer's numbering
    by_id = {r["Item ID"]: r for r in rows}
    assert by_id[line_a.id]["Status"] == "excluded" and by_id[line_a.id]["IFC GlobalId"] == ""
    assert by_id[line_b.id]["Width"] == "300" and by_id[line_b.id]["Height"] == "3000"
    assert by_id[line_b.id]["Drawn size"] == "7000"
    side = by_id[f"{next(e for e in elements if e.layer == 'A-WALL' and e.closed).id}:1"]
    assert side["Segment"] == "1" and side["Drawn size"] == "12000"

    gids = {w.GlobalId for w in result.model.by_type("IfcWall")}
    assert {r["IFC GlobalId"] for r in walls if r["Status"] == "exported"} == gids

    doors = [r for r in rows if r["Layer"] == "A-DOOR"]
    assert len(doors) == 3
    assert all(r["Status"] == "skipped" and "width required" in r["Reason"] for r in doors)
    assert doors[0]["Block"] == "DOOR_900"


def test_csv_splits_xref_layer_names(tmp_path):
    write_csv([{"layer": "xref-Bishop-Overland-08$0$A-WALL", "n": 1}], "mm", tmp_path / "x.csv")
    row = next(csv.DictReader((tmp_path / "x.csv").open(encoding="utf-8-sig")))
    assert (row["Layer"], row["Xref"], row["Unit"]) == ("A-WALL", "xref-Bishop-Overland-08", "mm")


def test_item_can_supply_height_missing_on_layer(sample):
    door = next(e for e in load_elements(sample) if e.layer == "A-DOOR")
    spec = LayerSpec("A-DOOR", "IfcDoor", width=900, overrides={door.id: ItemOverride(height=2100)})
    result = build_ifc(load_elements(sample), [spec])
    assert result.created["A-DOOR"] == 1
    assert result.skipped["A-DOOR"] == 2 and "height required" in result.warnings[0]


def test_imperial_units(sample):
    result = build_ifc(load_elements(sample), [LayerSpec("A-SLAB", "IfcSlab", height=1)], unit="ft")
    unit = result.model.by_type("IfcConversionBasedUnit")[0]
    assert unit.Name == "foot"


def test_http_round_trip(sample):
    client = TestClient(app)
    with sample.open("rb") as fh:
        r = client.post("/api/dxf", files={"file": ("plan.dxf", fh, "application/dxf")})
    assert r.status_code == 200, r.text
    file_id = r.json()["file_id"]

    r = client.post(
        "/api/convert",
        json={
            "file_id": file_id,
            "unit": "mm",
            "layers": [{"name": "A-WALL", "ifc_class": "IfcWall", "height": 3000, "width": 200}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 7

    r = client.get(f"/api/ifc/{body['download_id']}", params={"name": "plan"})
    assert r.status_code == 200
    assert r.content.startswith(b"ISO-10303-21")
    assert 'filename="plan.ifc"' in r.headers["content-disposition"]

    r = client.get(f"/api/csv/{body['download_id']}", params={"name": "plan"})
    assert r.status_code == 200
    assert 'filename="plan.csv"' in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(rows) == 7 and {row["Status"] for row in rows} == {"exported"}
    assert client.get(f"/api/exe/{body['download_id']}").status_code == 404


def test_http_rejects_bad_input():
    client = TestClient(app)
    assert client.post("/api/dxf", files={"file": ("x.dwg", b"0", "application/octet-stream")}).status_code == 400
    assert client.get("/api/ifc/../../etc").status_code in (400, 404)
    r = client.post("/api/convert", json={"file_id": "0" * 32, "layers": [{"name": "a", "ifc_class": "IfcWall", "height": 0}]})
    assert r.status_code == 422
