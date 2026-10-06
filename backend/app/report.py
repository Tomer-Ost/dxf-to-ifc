"""CSV report of a conversion: one row per line/element of every selected layer."""

from __future__ import annotations

import csv
from pathlib import Path

from .dxf_reader import split_layer_name

# (header, row key)
COLUMNS = [
    ("Layer", "layer_short"),
    ("Xref", "xref"),
    ("Full layer name", "layer"),
    ("#", "n"),
    ("Item ID", "item_id"),
    ("DXF handle", "handle"),
    ("DXF type", "dxf_type"),
    ("Segment", "segment"),
    ("Block", "block"),
    ("IFC class", "ifc_class"),
    ("Status", "status"),
    ("Reason", "reason"),
    ("Width", "width"),
    ("Height", "height"),
    ("Length", "length"),
    ("Drawn size", "drawn_size"),
    ("Unit", "unit"),
    ("IFC name", "ifc_name"),
    ("IFC GlobalId", "ifc_global_id"),
]


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}" if abs(v) < 1e6 else f"{v:.0f}"
    return str(v)


def write_csv(rows: list[dict], unit: str, path: str | Path) -> None:
    # utf-8-sig so Excel detects the encoding (layer names may be non-ASCII).
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([h for h, _ in COLUMNS])
        for row in rows:
            short, xref = split_layer_name(row["layer"])
            full = {**row, "layer_short": short, "xref": xref, "unit": unit}
            w.writerow([_fmt(full.get(key)) for _, key in COLUMNS])
