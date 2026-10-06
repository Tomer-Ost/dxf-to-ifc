"""HTTP API: upload a DXF, configure layers, download the generated IFC."""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path

from ezdxf.lldxf.const import DXFStructureError
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .dxf_reader import analyze, load_elements, read_dxf
from .ifc_builder import IFC_CLASSES, UNITS, ItemOverride, LayerSpec, build_ifc
from .report import write_csv

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
WORK_DIR = Path(tempfile.gettempdir()) / "dxf2ifc"
WORK_DIR.mkdir(exist_ok=True)
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
ID_RE = re.compile(r"^[0-9a-f]{32}$")

app = FastAPI(title="DXF to IFC")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ItemIn(BaseModel):
    id: str
    include: bool = True
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    length: float | None = Field(default=None, gt=0)


class LayerIn(BaseModel):
    name: str
    ifc_class: str
    height: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    length: float | None = Field(default=None, gt=0)
    items: list[ItemIn] = []


class ConvertIn(BaseModel):
    file_id: str
    unit: str = "mm"
    project_name: str = "DXF Import"
    storey_name: str = "Level 0"
    layers: list[LayerIn] = Field(min_length=1)


def _work_file(file_id: str, suffix: str) -> Path:
    if not ID_RE.match(file_id):
        raise HTTPException(400, "Invalid id")
    path = WORK_DIR / f"{file_id}{suffix}"
    if not path.exists():
        raise HTTPException(404, "File not found, please upload it again")
    return path


@app.get("/api/options")
def options():
    return {"ifc_classes": IFC_CLASSES, "units": list(UNITS)}


@app.post("/api/dxf")
async def upload_dxf(file: UploadFile):
    if not (file.filename or "").lower().endswith(".dxf"):
        raise HTTPException(400, "Please upload a .dxf file")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 200 MB")

    file_id = uuid.uuid4().hex
    path = WORK_DIR / f"{file_id}.dxf"
    path.write_bytes(data)
    try:
        summary = analyze(read_dxf(path))
    except (DXFStructureError, OSError, UnicodeDecodeError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not read DXF: {exc}") from exc
    return {"file_id": file_id, "filename": file.filename, **summary}


@app.post("/api/convert")
def convert(req: ConvertIn):
    if req.unit not in UNITS:
        raise HTTPException(400, f"Unknown unit {req.unit!r}")
    bad = [l.ifc_class for l in req.layers if l.ifc_class not in IFC_CLASSES]
    if bad:
        raise HTTPException(400, f"Unknown IFC class {bad[0]!r}")

    src = _work_file(req.file_id, ".dxf")
    specs = [
        LayerSpec(
            l.name,
            l.ifc_class,
            l.height,
            l.width,
            l.length,
            {i.id: ItemOverride(i.include, i.width, i.height, i.length) for i in l.items},
        )
        for l in req.layers
    ]
    result = build_ifc(load_elements(src), specs, req.unit, req.project_name, req.storey_name)

    out_id = uuid.uuid4().hex
    result.model.write(str(WORK_DIR / f"{out_id}.ifc"))
    write_csv(result.rows, req.unit, WORK_DIR / f"{out_id}.csv")
    return {
        "download_id": out_id,
        "created": dict(result.created),
        "skipped": dict(result.skipped),
        "total": sum(result.created.values()),
        "warnings": result.warnings,
    }


DOWNLOADS = {"ifc": "application/x-step", "csv": "text/csv"}


@app.get("/api/{kind}/{download_id}")
def download(kind: str, download_id: str, name: str = "model"):
    if kind not in DOWNLOADS:
        raise HTTPException(404, "Not found")
    safe = re.sub(r"[^\w\- .]", "_", name).strip() or "model"
    return FileResponse(
        _work_file(download_id, f".{kind}"), media_type=DOWNLOADS[kind], filename=f"{safe}.{kind}"
    )


# Serve the built React app when present, so `uvicorn` alone runs the whole tool.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="web")
