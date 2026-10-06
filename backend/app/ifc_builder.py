"""Turn extracted DXF elements plus per-layer settings into an IFC4 model.

Layer values are defaults; any single element (by id) can override width, height
and length, or be excluded.

Geometry rules (all values in drawing units):
  * lines / arcs -> each straight piece becomes a rectangle `width` wide, extruded
    `height` up. On a single straight segment `length` overrides the drawn length.
  * open polylines are exploded: every segment is a separate element (see dxf_reader).
  * closed polylines -> the outline is extruded `height` up (slabs, columns, rooms...).
    On the IfcWall class the polyline is exploded instead: one wall per segment.
  * circles -> circular profile (diameter = `width` if given, else the drawn radius).
  * blocks / points -> a `width` x `length` box centred on the insertion point,
    rotated with the block. `length` defaults to `width`.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass, field, replace

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial

from .dxf_reader import Element

IFC_CLASSES = [
    "IfcWall",
    "IfcSlab",
    "IfcColumn",
    "IfcBeam",
    "IfcDoor",
    "IfcWindow",
    "IfcRoof",
    "IfcStair",
    "IfcRailing",
    "IfcCovering",
    "IfcFurniture",
    "IfcBuildingElementProxy",
]

# unit key -> (SI prefix or None, conversion-based name, metres per unit)
UNITS = {
    "mm": ("MILLI", None, 0.001),
    "cm": ("CENTI", None, 0.01),
    "m": (None, None, 1.0),
    "in": (None, "inch", 0.0254),
    "ft": (None, "foot", 0.3048),
}

Pt = tuple[float, float]


@dataclass
class ItemOverride:
    include: bool = True
    width: float | None = None
    height: float | None = None
    length: float | None = None


@dataclass
class LayerSpec:
    name: str
    ifc_class: str
    height: float | None = None
    width: float | None = None
    length: float | None = None
    overrides: dict[str, ItemOverride] = field(default_factory=dict)

    def for_item(self, item_id: str) -> "LayerSpec | None":
        """Effective settings for one element, or None if it is excluded."""
        o = self.overrides.get(item_id)
        if o is None:
            return self
        if not o.include:
            return None
        return replace(
            self,
            width=o.width or self.width,
            height=o.height or self.height,
            length=o.length or self.length,
        )


@dataclass
class BuildResult:
    model: ifcopenshell.file
    created: Counter
    skipped: Counter
    warnings: list[str]
    rows: list[dict] = field(default_factory=list)  # one per element of a selected layer, for the CSV report


def drawn_size(el: Element) -> float | None:
    """Length of a line, perimeter of an outline, diameter of a circle."""
    if el.kind == "circle":
        return el.radius * 2
    if el.kind != "path":
        return None
    pts = el.points + el.points[:1] if el.closed else el.points
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


# ---------------------------------------------------------------- geometry ---


def _segment_rect(a: Pt, b: Pt, width: float) -> list[Pt]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    nx, ny = -dy / n * width / 2, dx / n * width / 2
    return [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]


def _rotated_box(c: Pt, width: float, length: float, rotation_deg: float) -> list[Pt]:
    r = math.radians(rotation_deg)
    cos, sin = math.cos(r), math.sin(r)
    hw, hl = width / 2, length / 2
    return [(c[0] + x * cos - y * sin, c[1] + x * sin + y * cos) for x, y in ((-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl))]


def _area(pts: list[Pt]) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def _profiles(el: Element, spec: LayerSpec) -> tuple[list[list[Pt] | float], str | None]:
    """Return (profiles, skip_reason). A profile is a polygon or a circle radius."""
    w, length = spec.width, spec.length
    if not spec.height:
        return [], "height required"

    if el.kind == "circle":
        r = w / 2 if w else el.radius
        return ([r], None) if r > 0 else ([], "zero radius")

    if el.kind == "point":
        if not w:
            return [], "width required for blocks/points"
        return [_rotated_box(el.points[0], w, length or w, el.rotation)], None

    pts = el.points
    if el.closed and spec.ifc_class != "IfcWall":
        return ([pts], None) if _area(pts) > 1e-9 else ([], "degenerate outline")

    if not w:
        return [], "width required for lines"
    edges = list(zip(pts, pts[1:] + pts[:1])) if el.closed else list(zip(pts, pts[1:]))
    if length and len(edges) == 1:
        (a, b), = edges
        d = math.dist(a, b)
        if d > 0:
            edges = [(a, (a[0] + (b[0] - a[0]) / d * length, a[1] + (b[1] - a[1]) / d * length))]
    rects = [_segment_rect(a, b, w) for a, b in edges if math.dist(a, b) > 1e-9]
    return (rects, None) if rects else ([], "zero-length geometry")


# --------------------------------------------------------------- IFC model ---


class _Writer:
    def __init__(self, unit: str, project_name: str, storey_name: str):
        self.f = ifcopenshell.file(schema="IFC4")
        f = self.f
        project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name=project_name)
        f.createIfcUnitAssignment([self._length_unit(unit)])
        project.UnitsInContext = f.by_type("IfcUnitAssignment")[0]

        model_ctx = ifcopenshell.api.context.add_context(f, context_type="Model")
        self.body = ifcopenshell.api.context.add_context(
            f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx
        )

        site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Site")
        building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Building")
        self.storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=storey_name)
        self.storey.Elevation = 0.0
        ifcopenshell.api.aggregate.assign_object(f, products=[site], relating_object=project)
        ifcopenshell.api.aggregate.assign_object(f, products=[building], relating_object=site)
        ifcopenshell.api.aggregate.assign_object(f, products=[self.storey], relating_object=building)

        parent = None
        for obj in (site, building, self.storey):
            obj.ObjectPlacement = parent = f.createIfcLocalPlacement(parent, self._axis3d((0.0, 0.0, 0.0)))
        self.storey_placement = parent
        self.z_dir = f.createIfcDirection((0.0, 0.0, 1.0))

    def _length_unit(self, unit: str):
        f = self.f
        prefix, conv_name, factor = UNITS[unit]
        if conv_name is None:
            return f.createIfcSIUnit(None, "LENGTHUNIT", prefix, "METRE")
        metre = f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")
        dims = f.createIfcDimensionalExponents(1, 0, 0, 0, 0, 0, 0)
        measure = f.createIfcMeasureWithUnit(f.create_entity("IfcLengthMeasure", factor), metre)
        return f.createIfcConversionBasedUnit(dims, "LENGTHUNIT", conv_name, measure)

    def _axis3d(self, xyz):
        return self.f.createIfcAxis2Placement3D(self.f.createIfcCartesianPoint(xyz), None, None)

    def _solid(self, profile: list[Pt] | float, origin: Pt, height: float):
        f = self.f
        if isinstance(profile, float):
            pdef = f.createIfcCircleProfileDef(
                "AREA", None, f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((0.0, 0.0)), None), profile
            )
        else:
            local = [f.createIfcCartesianPoint((x - origin[0], y - origin[1])) for x, y in profile]
            pdef = f.createIfcArbitraryClosedProfileDef("AREA", None, f.createIfcPolyline(local + local[:1]))
        return f.createIfcExtrudedAreaSolid(pdef, self._axis3d((0.0, 0.0, 0.0)), self.z_dir, height)

    def add(self, el: Element, spec: LayerSpec, profiles, index: int):
        f = self.f
        origin = el.points[0]
        product = ifcopenshell.api.root.create_entity(f, ifc_class=spec.ifc_class, name=f"{spec.name} {index}")
        product.ObjectPlacement = f.createIfcLocalPlacement(self.storey_placement, self._axis3d((*origin, 0.0)))
        solids = [self._solid(p, origin, spec.height) for p in profiles]
        rep = f.createIfcShapeRepresentation(self.body, "Body", "SweptSolid", solids)
        product.Representation = f.createIfcProductDefinitionShape(None, None, [rep])
        if spec.ifc_class in ("IfcDoor", "IfcWindow"):
            product.OverallHeight = spec.height
            if spec.width:
                product.OverallWidth = spec.width

        self._pset(
            product,
            "DXF_Source",
            Layer=el.layer,
            EntityType=el.dxf_type,
            Handle=el.handle,
            BlockName=el.block,
            Segment=el.segment,
        )
        self._pset(product, "DXF_Dimensions", Width=spec.width, Height=spec.height, Length=spec.length)
        return product

    def _pset(self, product, name: str, **props):
        pset = ifcopenshell.api.pset.add_pset(self.f, product=product, name=name)
        ifcopenshell.api.pset.edit_pset(
            self.f, pset=pset, properties={k: v for k, v in props.items() if v not in (None, "")}
        )

    def finish(self, products):
        if products:
            ifcopenshell.api.spatial.assign_container(self.f, products=products, relating_structure=self.storey)
        self.f.header.file_name.name = "dxf2ifc"
        self.f.header.file_name.time_stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.f.header.file_name.originating_system = "DXF to IFC MVP"


def _explode_walls(elements: list[Element], by_layer: dict[str, LayerSpec]):
    """Closed polylines on wall layers become one open element per segment."""
    for el in elements:
        spec = by_layer.get(el.layer)
        if spec and spec.ifc_class == "IfcWall" and el.closed and el.segments:
            for i, seg in enumerate(el.segments, start=1):
                yield replace(el, points=seg, closed=False, segments=[], segment=i, id=f"{el.id}:{i}")
        else:
            yield el


def build_ifc(
    elements: list[Element],
    specs: list[LayerSpec],
    unit: str = "mm",
    project_name: str = "DXF Import",
    storey_name: str = "Level 0",
) -> BuildResult:
    if unit not in UNITS:
        raise ValueError(f"unsupported unit {unit!r}")
    by_layer = {s.name: s for s in specs}
    writer = _Writer(unit, project_name, storey_name)
    created: Counter = Counter()
    skipped: Counter = Counter()
    reasons: Counter = Counter()
    products = []
    rows = []
    numbers: Counter = Counter()  # per-layer item number, same order as the viewer's list

    for el in _explode_walls(elements, by_layer):
        layer_spec = by_layer.get(el.layer)
        if layer_spec is None:
            continue
        numbers[el.layer] += 1
        spec = layer_spec.for_item(el.id)
        row = {
            "layer": el.layer,
            "n": numbers[el.layer],
            "item_id": el.id,
            "handle": el.handle,
            "dxf_type": el.part or el.dxf_type,
            "segment": el.segment,
            "block": el.block,
            "ifc_class": layer_spec.ifc_class,
            "drawn_size": drawn_size(el),
        }
        rows.append(row)
        if spec is None:
            row["status"] = "excluded"
            continue
        row.update(width=spec.width, height=spec.height, length=spec.length)
        profiles, reason = _profiles(el, spec)
        if reason:
            skipped[el.layer] += 1
            reasons[(el.layer, reason)] += 1
            row.update(status="skipped", reason=reason)
            continue
        created[el.layer] += 1
        product = writer.add(el, spec, profiles, created[el.layer])
        products.append(product)
        row.update(status="exported", ifc_name=product.Name, ifc_global_id=product.GlobalId)

    writer.finish(products)
    warnings = [f"{layer}: {n} skipped ({why})" for (layer, why), n in reasons.items()]
    return BuildResult(writer.f, created, skipped, warnings, rows)
