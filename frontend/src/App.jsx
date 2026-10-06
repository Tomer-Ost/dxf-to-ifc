import { useEffect, useMemo, useState } from "react";
import { convert, download, getOptions, uploadDxf } from "./api.js";
import DrawingCanvas from "./components/DrawingCanvas.jsx";
import DropZone from "./components/DropZone.jsx";
import LayerPanel from "./components/LayerPanel.jsx";
import {
  FALLBACK_CLASSES,
  FIELDS,
  initialSettings,
  itemState,
  layerItems,
  layerStatus,
  splitLayerName,
} from "./layerRules.js";

const UNITS = { mm: "Millimetres", cm: "Centimetres", m: "Metres", in: "Inches", ft: "Feet" };
const num = (v) => (v === "" || v == null ? null : Number(v));

/** Drop empty values so an item with nothing custom has no override entry at all. */
function mergeOverride(prev = {}, patch) {
  const next = { ...prev, ...patch };
  for (const k of Object.keys(next)) if (next[k] === "" || next[k] === undefined) delete next[k];
  return Object.keys(next).length ? next : null;
}

export default function App() {
  const [classes, setClasses] = useState(FALLBACK_CLASSES);
  const [drawing, setDrawing] = useState(null);
  const [settings, setSettings] = useState({});
  const [overrides, setOverrides] = useState({}); // item id -> { include?, width?, height?, length? }
  const [unit, setUnit] = useState("mm");
  const [projectName, setProjectName] = useState("");
  const [hover, setHover] = useState(null); // { layer, item }
  const [active, setActive] = useState(null); // { layer, item }: line being edited
  const [focus, setFocus] = useState(null); // { name, item, n }: panel scrolls to this
  const [busy, setBusy] = useState(null); // "upload" | "convert" | null
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    getOptions()
      .then((o) => setClasses(o.ifc_classes))
      .catch(() => {});
  }, []);

  async function openFile(file) {
    setBusy("upload");
    setError(null);
    setResult(null);
    try {
      const d = await uploadDxf(file);
      setDrawing(d);
      setSettings(initialSettings(d.layers));
      setOverrides({});
      setActive(null);
      setHover(null);
      setUnit(d.unit);
      setProjectName(file.name.replace(/\.dxf$/i, ""));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  const selectedLayers = useMemo(
    () => (drawing ? drawing.layers.filter((l) => settings[l.name]?.selected) : []),
    [drawing, settings],
  );
  const selectedNames = useMemo(() => new Set(selectedLayers.map((l) => l.name)), [selectedLayers]);

  // Item geometry/labels only change with the layer's class, not with typed values.
  const classKey = JSON.stringify(selectedLayers.map((l) => [l.name, settings[l.name].ifc_class]));
  const baseItems = useMemo(
    () => new Map(selectedLayers.map((l) => [l.name, layerItems(drawing.preview[l.name], settings[l.name].ifc_class)])),
    [drawing, classKey], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const { itemsByLayer, statusByLayer } = useMemo(() => {
    const items = new Map();
    const status = new Map();
    for (const [name, base] of baseItems) {
      const setting = settings[name];
      items.set(
        name,
        base.map((it) => ({ ...it, ov: overrides[it.id], ...itemState(it, setting, overrides[it.id]) })),
      );
      status.set(name, layerStatus(base, setting, overrides));
    }
    return { itemsByLayer: items, statusByLayer: status };
  }, [baseItems, settings, overrides]);

  const touch = () => setResult(null);

  const updateLayer = (name, patch) => {
    touch();
    setSettings((s) => ({ ...s, [name]: { ...s[name], ...patch } }));
    if (patch.selected === false && active?.layer === name) setActive(null);
  };

  const updateItem = (id, patch) => {
    touch();
    setOverrides((o) => {
      const merged = mergeOverride(o[id], patch);
      const next = { ...o };
      if (merged) next[id] = merged;
      else delete next[id];
      return next;
    });
  };

  const setLayerIncluded = (name, include) => {
    touch();
    setOverrides((o) => {
      const next = { ...o };
      for (const it of baseItems.get(name) ?? []) {
        const merged = mergeOverride(o[it.id], { include: include ? undefined : false });
        if (merged) next[it.id] = merged;
        else delete next[it.id];
      }
      return next;
    });
  };

  // Called on every pointer move; keep the previous object when nothing changed to avoid re-renders.
  const hoverTo = (h) =>
    setHover((prev) => (prev?.layer === h?.layer && prev?.item === h?.item ? prev : h));

  const focusOn = (name, item = null) => setFocus((f) => ({ name, item, n: (f?.n ?? 0) + 1 }));

  const pickLayer = (name) => {
    updateLayer(name, { selected: !settings[name].selected });
    focusOn(name);
  };
  const activateItem = (layer, item) => {
    setActive((a) => (a?.item === item ? null : { layer, item }));
    focusOn(layer, item);
  };

  const incomplete = selectedLayers.filter((l) => !statusByLayer.get(l.name)?.ok);

  const fileName = () => projectName.trim() || "model";

  /** Convert (unless the last result still matches the current settings), then download. */
  async function exportFile(kind) {
    if (result) {
      download(result.download_id, fileName(), kind);
      return;
    }
    setBusy(kind);
    setError(null);
    try {
      const name = fileName();
      const res = await convert({
        file_id: drawing.file_id,
        unit,
        project_name: name,
        layers: selectedLayers.map((l) => {
          const s = settings[l.name];
          return {
            name: l.name,
            ifc_class: s.ifc_class,
            ...Object.fromEntries(FIELDS.map((f) => [f, num(s[f])])),
            items: itemsByLayer
              .get(l.name)
              .filter((it) => it.ov)
              .map((it) => ({
                id: it.id,
                include: it.included,
                ...Object.fromEntries(FIELDS.map((f) => [f, num(it.ov[f])])),
              })),
          };
        }),
      });
      setResult(res);
      if (kind === "csv" || res.total > 0) download(res.download_id, name, kind);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  if (!drawing) {
    return (
      <div className="app empty">
        <header className="topbar">
          <Brand />
        </header>
        <main className="empty-main">
          <DropZone onFile={openFile} busy={busy === "upload"} error={error} />
        </main>
      </div>
    );
  }

  let exportHint = null;
  if (!selectedLayers.length) exportHint = "Select at least one layer";
  else if (incomplete.length) {
    const first = incomplete[0];
    const bad = statusByLayer.get(first.name).bad;
    exportHint =
      incomplete.length > 1
        ? `Complete the dimensions for ${incomplete.length} layers`
        : `Complete the dimensions for ${splitLayerName(first.name).short}${bad ? ` (${bad} line${bad > 1 ? "s" : ""})` : ""}`;
  }

  return (
    <div className="app">
      <header className="topbar">
        <Brand />
        <span className="filename" title={drawing.filename}>
          {drawing.filename}
        </span>
        <label className="ghost small file-button">
          {busy === "upload" ? "Reading…" : "Open another"}
          <input
            type="file"
            accept=".dxf"
            hidden
            disabled={!!busy}
            onChange={(e) => {
              if (e.target.files[0]) openFile(e.target.files[0]);
              e.target.value = "";
            }}
          />
        </label>
      </header>

      <main className="workspace">
        <DrawingCanvas
          drawing={drawing}
          unit={unit}
          selected={selectedNames}
          itemsByLayer={itemsByLayer}
          hover={hover}
          active={active}
          onHover={hoverTo}
          onPickLayer={pickLayer}
          onPickItem={activateItem}
          onClear={() => setActive(null)}
        />

        <aside className="panel">
          <LayerPanel
            layers={drawing.layers}
            settings={settings}
            statusByLayer={statusByLayer}
            itemsByLayer={itemsByLayer}
            unit={unit}
            classes={classes}
            focus={focus}
            hover={hover}
            active={active}
            handlers={{
              onChange: updateLayer,
              onItemChange: updateItem,
              onItemsBulk: setLayerIncluded,
              onHover: hoverTo,
              onActivate: activateItem,
            }}
          />

          <section className="panel-section export">
            <div className="field-row">
              <label className="field">
                <span className="field-label">Project</span>
                <input value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="model" />
              </label>
              <label className="field narrow">
                <span className="field-label">Units</span>
                <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                  {Object.entries(UNITS).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="export-actions">
              <button className="primary" disabled={!!busy || !!exportHint} onClick={() => exportFile("ifc")}>
                {busy === "ifc" ? "Generating…" : "Export IFC"}
              </button>
              <button
                className="secondary"
                disabled={!!busy || !selectedLayers.length}
                onClick={() => exportFile("csv")}
                title="Table of every line: layer, type, values used, status and IFC GlobalId"
              >
                {busy === "csv" ? "Generating…" : "Export CSV"}
              </button>
            </div>
            {exportHint && <p className="muted small center">{exportHint}</p>}
            {error && <p className="error small">{error}</p>}
            {result && <ResultSummary result={result} onDownload={(kind) => download(result.download_id, fileName(), kind)} />}
          </section>
        </aside>
      </main>
    </div>
  );
}

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">DXF</span>
      <span className="brand-arrow">→</span>
      <span className="brand-mark">IFC</span>
    </div>
  );
}

function ResultSummary({ result, onDownload }) {
  return (
    <div className={`result${result.total ? "" : " warn"}`}>
      {result.total ? (
        <p>
          <strong>{result.total}</strong> element{result.total === 1 ? "" : "s"} exported.
        </p>
      ) : (
        <p>No elements could be created from the selected layers.</p>
      )}
      <p className="small">
        Download{" "}
        {result.total > 0 && (
          <>
            <button className="link" onClick={() => onDownload("ifc")}>
              IFC
            </button>
            {" · "}
          </>
        )}
        <button className="link" onClick={() => onDownload("csv")}>
          CSV
        </button>
      </p>
      {result.warnings.map((w) => (
        <p key={w} className="muted small">
          {w}
        </p>
      ))}
    </div>
  );
}
