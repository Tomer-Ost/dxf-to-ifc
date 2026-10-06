# One-command launcher: sets up dependencies on first run, builds the web UI,
# and serves everything at http://localhost:8765
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Creating Python environment..."
    python -m venv (Join-Path $root "backend\.venv")
    & $py -m pip install -r (Join-Path $root "backend\requirements.txt")
}

Push-Location (Join-Path $root "frontend")
try {
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
} finally {
    Pop-Location
}

Write-Host "`nDXF to IFC running at http://localhost:8765  (Ctrl+C to stop)`n"
Push-Location (Join-Path $root "backend")
try {
    & $py -m uvicorn app.main:app --port 8765
} finally {
    Pop-Location
}
