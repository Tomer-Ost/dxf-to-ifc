"""Generate samples/simple_plan.dxf: a small floor plan (millimetres) with typical layers."""

from pathlib import Path

import ezdxf
from ezdxf import units


def make_sample(path: Path) -> Path:
    doc = ezdxf.new("R2018", setup=True)
    doc.units = units.MM
    for name, color in [("A-WALL", 7), ("A-COLUMN", 1), ("A-DOOR", 3), ("A-WINDOW", 5), ("A-SLAB", 8), ("A-ANNO", 2)]:
        doc.layers.add(name, color=color)

    door = doc.blocks.new("DOOR_900")
    door.add_line((-450, 0), (450, 0))
    door.add_arc((-450, 0), 900, 0, 90)

    msp = doc.modelspace()
    # Outer walls as one closed centre-line polyline, plus interior walls.
    msp.add_lwpolyline([(0, 0), (12000, 0), (12000, 8000), (0, 8000)], close=True, dxfattribs={"layer": "A-WALL"})
    msp.add_line((5000, 0), (5000, 8000), dxfattribs={"layer": "A-WALL"})
    msp.add_line((5000, 4000), (12000, 4000), dxfattribs={"layer": "A-WALL"})
    msp.add_arc((2500, 8000), 1500, 0, 180, dxfattribs={"layer": "A-WALL"})

    for x, y in [(0, 0), (12000, 0), (12000, 8000), (0, 8000)]:
        msp.add_lwpolyline(
            [(x - 200, y - 200), (x + 200, y - 200), (x + 200, y + 200), (x - 200, y + 200)],
            close=True,
            dxfattribs={"layer": "A-COLUMN"},
        )
    msp.add_circle((5000, 4000), 250, dxfattribs={"layer": "A-COLUMN"})

    msp.add_blockref("DOOR_900", (2500, 0), dxfattribs={"layer": "A-DOOR"})
    msp.add_blockref("DOOR_900", (5000, 2000), dxfattribs={"layer": "A-DOOR", "rotation": 90})
    msp.add_blockref("DOOR_900", (8500, 4000), dxfattribs={"layer": "A-DOOR"})

    for x in (8500, 10500):
        msp.add_line((x - 600, 8000), (x + 600, 8000), dxfattribs={"layer": "A-WINDOW"})

    msp.add_lwpolyline([(0, 0), (12000, 0), (12000, 8000), (0, 8000)], close=True, dxfattribs={"layer": "A-SLAB"})
    msp.add_text("LIVING", height=300, dxfattribs={"layer": "A-ANNO"}).set_placement((2000, 4000))

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return path


if __name__ == "__main__":
    out = make_sample(Path(__file__).resolve().parents[2] / "samples" / "simple_plan.dxf")
    print(f"wrote {out}")
