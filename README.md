# DXF → IFC

A small local web tool. Open a DXF floor plan, pick the layers you want, set a
width, height and length per layer, and export an IFC4 model.

## Run it

```powershell
.\start.ps1
```

Then open http://localhost:8765. The first run creates the Python venv and installs npm packages.

For development with hot reload, use two terminals:

```powershell
# terminal 1: API on :8765
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8765 --reload
# terminal 2: UI on :5173 (proxies /api to :8765)
cd frontend; npm run dev
```

To try it with no drawing of your own, use `samples/simple_plan.dxf`. Regenerate it with
`backend\.venv\Scripts\python backend\scripts\make_sample.py`.

## Using it

1. Open a DXF. Click a line on the drawing, or tick a layer in the panel, to select its layer.
   Bound xref layers such as `xref-Plan$0$A-WALL` are shown as `A-WALL`.
2. Choose the IFC class and enter the **layer defaults** (width, height, length).
3. Inside a selected layer, each line can be picked on its own. Hover a line on the drawing
   or in the list to highlight it, and click it to edit it:
   - Enter its own width, height or length. Empty fields fall back to the layer defaults.
   - Untick it to leave it out of the export. **All / None** toggles every line in the layer.
4. Click **Export IFC** to download the model.

   Click **Export CSV** to download the line table, with one row per line of every selected layer:
   - **Identification:** layer (with the xref prefix in its own column), the `#` from the panel, item ID, DXF handle, type and segment, block name, IFC class
   - **Values:** the width, height and length actually used, plus the drawn length
   - **Result:** status (`exported`, `excluded` or `skipped`, with the reason), and the IFC name and GlobalId, which link each row to its object in the IFC file

   The file is UTF-8 with a byte-order mark, so Excel opens it with the right encoding. CSV export also works while some lines still lack values; those rows show as `skipped`.

## How DXF geometry becomes IFC

Each model-space entity on a selected layer becomes one IFC element of the class
you choose. The exception is polylines, which are exploded: every segment, straight
or bulge arc, becomes its own element. All values are in drawing units.

| DXF entity | Result | Width | Height | Length |
|---|---|---|---|---|
| LINE, ARC, SPLINE, ELLIPSE | One element along the centre line | thickness (required) | extrusion | overrides the drawn length on straight lines |
| Open LWPOLYLINE/POLYLINE | Exploded: **one element per segment** | thickness (required) | extrusion | overrides the length of each straight segment |
| Closed polyline | Outline extruded as-is (slab, column, room) | — | extrusion | — |
| Closed polyline on **IfcWall** | Exploded: one wall per side | thickness (required) | extrusion | per straight segment |
| CIRCLE | Circular profile | diameter (optional, defaults to drawn) | extrusion | — |
| INSERT (block), POINT | W × L box centred on the insertion point, rotated with the block | required | extrusion | defaults to width |

Arcs, splines and bulged polylines are flattened into short segments. Text,
dimensions, hatches and 3D entities are ignored.

Every element carries two property sets:
- `DXF_Source`: layer, entity type, handle, block name, and the segment number for exploded polylines, so you can trace each element back to the drawing.
- `DXF_Dimensions`: the width, height and length you entered.

The model structure is Project → Site → Building → Storey "Level 0". The length
unit is detected from `$INSUNITS` and can be changed in the UI.

## Project layout

```
backend/
  app/dxf_reader.py    DXF -> layers, preview polylines, elements   (ezdxf)
  app/ifc_builder.py   elements + layer settings -> IFC4 model       (IfcOpenShell)
  app/main.py          FastAPI: POST /api/dxf, POST /api/convert, GET /api/ifc/{id}
  tests/               pytest: parsing, IFC output, geometry, HTTP round trip
frontend/              React + Vite (2D canvas preview, layer panel)
samples/               example floor plan
```

Run the tests with `cd backend; .venv\Scripts\python -m pytest`.

## Known MVP limitations

- Wall segments are not mitred or joined, so corners overlap slightly.
- Doors and windows don't cut openings in the walls (no `IfcOpeningElement` yet).
- One storey, at elevation 0.
- DWG isn't read directly. Convert it to DXF first, for example with the ODA File Converter.
- Uploaded files are kept in the system temp folder (`%TEMP%\dxf2ifc`) and never cleaned up.
