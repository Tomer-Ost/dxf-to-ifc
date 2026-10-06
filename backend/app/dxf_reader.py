"""Read a DXF drawing into layer summaries, preview geometry and convertible elements.

Every model-space entity becomes at most one `Element`, except open polylines,
which are exploded so each segment (straight or bulge arc) is its own element.
Closed polylines stay whole, keeping their segments for classes that explode
them (walls). Block references (INSERT) are kept as single point-like elements
so a door block becomes one IfcDoor, not a pile of lines.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ezdxf import bbox, colors, recover
from ezdxf import path as ezpath
from ezdxf.disassemble import recursive_decompose
from ezdxf.document import Drawing

# $INSUNITS code -> (unit key, metres per unit)
INSUNITS = {
    1: ("in", 0.0254),
    2: ("ft", 0.3048),
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
}
DEFAULT_UNIT = "mm"

PATH_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "ELLIPSE", "SPLINE"}
POINT_TYPES = {"INSERT", "POINT"}


@dataclass
class Element:
    layer: str
    dxf_type: str
    handle: str
    kind: str  # "path" | "point" | "circle"
    points: list[tuple[float, float]] = field(default_factory=list)
    closed: bool = False
    rotation: float = 0.0  # degrees, point-like elements only
    radius: float = 0.0  # circles only
    block: str | None = None
    segment: int | None = None  # 1-based index within the source polyline
    segments: list[list[tuple[float, float]]] = field(default_factory=list)  # closed polylines only
    id: str = ""  # stable per drawing: entity handle, plus ":<segment>" for polyline segments
    part: str | None = None  # LINE or ARC for polyline segments


_XREF_LAYER = re.compile(r"^(.*?)(?:\$0\$|\|)([^$|]+)$")


def split_layer_name(name: str) -> tuple[str, str]:
    """Bound xref layers ("xref-Plan$0$A-WALL", "xref|A-WALL") -> ("A-WALL", "xref-Plan")."""
    m = _XREF_LAYER.match(name)
    return (m.group(2), m.group(1)) if m else (name, "")


def read_dxf(path: str | Path) -> Drawing:
    """Read a DXF file, repairing minor structural errors instead of failing."""
    doc, _auditor = recover.readfile(str(path))
    return doc


def detect_unit(doc: Drawing) -> str:
    code = doc.header.get("$INSUNITS", 0)
    return INSUNITS.get(code, (DEFAULT_UNIT, 0))[0]


def flatten_tolerance(doc: Drawing) -> float:
    ext = bbox.extents(doc.modelspace(), fast=True)
    if not ext.has_data:
        return 0.01
    diag = math.hypot(ext.size.x, ext.size.y)
    return max(diag / 5000.0, 1e-6)


def _dedupe(points: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in points:
        if not out or math.dist(out[-1], p) > eps:
            out.append(p)
    return out


def _flatten(entity, tol: float) -> tuple[list[tuple[float, float]], bool] | None:
    try:
        p = ezpath.make_path(entity)
    except (TypeError, ValueError):
        return None
    if len(p) == 0:
        return None
    pts = _dedupe([(v.x, v.y) for v in p.flattening(tol)], tol * 1e-3)
    closed = bool(getattr(entity, "closed", False)) or (
        len(pts) > 2 and math.dist(pts[0], pts[-1]) <= tol * 1e-3
    )
    if closed and len(pts) > 1 and math.dist(pts[0], pts[-1]) <= tol * 1e-3:
        pts = pts[:-1]
    return pts, closed


def _explode(entity, tol: float) -> list[tuple[str, list[tuple[float, float]]]]:
    """Polyline -> (LINE|ARC, flattened points) for every DXF segment."""
    segments = []
    for sub in entity.virtual_entities():
        flat = _flatten(sub, tol)
        if flat is not None and len(flat[0]) >= 2:
            segments.append((sub.dxftype(), flat[0]))
    return segments


def _entity_elements(e, index: int, tol: float) -> list[Element]:
    """Convertible elements for one model-space entity (empty if not convertible)."""
    t = e.dxftype()
    layer = e.dxf.get("layer", "0")
    handle = e.dxf.get("handle", "")
    eid = handle or f"n{index}"
    if t in PATH_TYPES:
        if t == "POLYLINE" and not e.is_2d_polyline:
            return []  # 3D polylines and meshes are out of scope
        flat = _flatten(e, tol)
        if flat is None or len(flat[0]) < 2:
            return []
        pts, closed = flat
        closed = closed and len(pts) > 2
        if t not in ("LWPOLYLINE", "POLYLINE"):
            return [Element(layer, t, handle, "path", pts, closed=closed, id=eid)]
        if closed:
            segs = [seg for _, seg in _explode(e, tol)]
            return [Element(layer, t, handle, "path", pts, closed=True, segments=segs, id=eid)]
        return [
            Element(layer, t, handle, "path", seg, segment=i, id=f"{eid}:{i}", part=part)
            for i, (part, seg) in enumerate(_explode(e, tol), start=1)
        ]
    if t == "CIRCLE":
        c = e.dxf.center
        return [Element(layer, t, handle, "circle", [(c.x, c.y)], radius=e.dxf.radius, id=eid)]
    if t in POINT_TYPES:
        loc = e.dxf.insert if t == "INSERT" else e.dxf.location
        return [
            Element(
                layer,
                t,
                handle,
                "point",
                [(loc.x, loc.y)],
                rotation=e.dxf.get("rotation", 0.0) if t == "INSERT" else 0.0,
                block=e.dxf.name if t == "INSERT" else None,
                id=eid,
            )
        ]
    return []


def extract_elements(doc: Drawing, tol: float | None = None) -> list[Element]:
    tol = tol if tol is not None else flatten_tolerance(doc)
    elements: list[Element] = []
    for index, e in enumerate(doc.modelspace()):
        elements.extend(_entity_elements(e, index, tol))
    return elements


def _layer_color(doc: Drawing, name: str) -> str:
    if name in doc.layers:
        layer = doc.layers.get(name)
        if layer.rgb is not None:
            r, g, b = layer.rgb
        else:
            r, g, b = colors.aci2rgb(abs(layer.dxf.get("color", 7)) or 7)
    else:
        r, g, b = colors.aci2rgb(7)
    return f"#{r:02x}{g:02x}{b:02x}"


def _flat(pts: list[tuple[float, float]], closed: bool = False) -> list[float]:
    if closed:
        pts = pts + [pts[0]]
    return [round(c, 6) for p in pts for c in p]


def _entity_paths(e, tol: float) -> list[list[float]]:
    """Display polylines for any entity; block contents are decomposed recursively."""
    out = []
    for sub in recursive_decompose([e]) if e.dxftype() == "INSERT" else [e]:
        flat = _flatten(sub, tol)
        if flat is not None and len(flat[0]) >= 2:
            out.append(_flat(*flat))
    return out


def _item(el: Element, e, tol: float) -> dict:
    """One selectable thing in the viewer, mirroring a convertible element."""
    item: dict = {"id": el.id, "type": el.part or el.dxf_type}
    if el.kind == "path":
        item["kind"] = "outline" if el.closed else "line"
        item["paths"] = [_flat(el.points, el.closed)]
        if el.segments:
            item["segments"] = [_flat(seg) for seg in el.segments]
    elif el.kind == "circle":
        item["kind"] = "circle"
        item["paths"] = _entity_paths(e, tol)
        item["radius"] = round(el.radius, 6)
    else:
        item["kind"] = "block" if el.block else "point"
        item["paths"] = _entity_paths(e, tol)
        item["point"] = _flat(el.points)
        if el.block:
            item["block"] = el.block
    return item


def analyze(doc: Drawing) -> dict:
    """Summary sent to the web client: layers, counts, extents and per-item preview geometry.

    `items` are the selectable, convertible elements of a layer; `other` is geometry
    that is drawn for context only (hatches, 3D polylines, ...).
    """
    tol = flatten_tolerance(doc)
    items: dict[str, list[dict]] = defaultdict(list)
    other: dict[str, list[list[float]]] = defaultdict(list)
    for index, e in enumerate(doc.modelspace()):
        layer = e.dxf.get("layer", "0")
        elements = _entity_elements(e, index, tol)
        if elements:
            items[layer].extend(_item(el, e, tol) for el in elements)
        else:
            other[layer].extend(_entity_paths(e, tol))

    xs: list[float] = []
    ys: list[float] = []
    flats = [f for paths in other.values() for f in paths]
    for layer_items in items.values():
        for it in layer_items:
            flats.extend(it["paths"])
            if "point" in it:
                flats.append(it["point"])
    for flat in flats:
        xs.extend(flat[0::2])
        ys.extend(flat[1::2])
    extents = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 1, 1]

    def counts(layer_items: list[dict]) -> dict[str, int]:
        c = {"lines": 0, "closed": 0, "circles": 0, "blocks": 0}
        key = {"line": "lines", "outline": "closed", "circle": "circles", "block": "blocks", "point": "blocks"}
        for it in layer_items:
            c[key[it["kind"]]] += 1
        return c

    names = sorted(set(items) | set(other), key=str.lower)
    return {
        "unit": detect_unit(doc),
        "extents": extents,
        "layers": [{"name": n, "color": _layer_color(doc, n), "counts": counts(items.get(n, []))} for n in names],
        "preview": {n: {"items": items.get(n, []), "other": other.get(n, [])} for n in names},
    }


def load_elements(path: str | Path) -> list[Element]:
    return extract_elements(read_dxf(path))


__all__ = ["Element", "INSUNITS", "analyze", "detect_unit", "extract_elements", "load_elements", "read_dxf", "split_layer_name"]
