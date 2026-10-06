import { useEffect, useRef, useState } from "react";
import { readable } from "../color.js";
import { formatSize, splitLayerName } from "../layerRules.js";

const LIST_LIMIT = 100;

function summary({ lines, closed, circles, blocks }) {
  const parts = [];
  if (lines) parts.push(`${lines} line${lines > 1 ? "s" : ""}`);
  if (closed) parts.push(`${closed} outline${closed > 1 ? "s" : ""}`);
  if (circles) parts.push(`${circles} circle${circles > 1 ? "s" : ""}`);
  if (blocks) parts.push(`${blocks} block${blocks > 1 ? "s" : ""}`);
  return parts.join(" · ") || "no convertible geometry";
}

function NumberField({ label, value, onChange, placeholder, unit, invalid }) {
  return (
    <label className={`field${invalid ? " invalid" : ""}`}>
      {label && <span className="field-label">{label}</span>}
      <span className="field-input">
        <input
          type="number"
          min="0"
          step="any"
          inputMode="decimal"
          value={value ?? ""}
          placeholder={placeholder}
          aria-label={label}
          onChange={(e) => onChange(e.target.value)}
        />
        <span className="field-unit">{unit}</span>
      </span>
    </label>
  );
}

function ItemRow({ item, layerName, setting, unit, isActive, isHover, onItemChange, onHover, onActivate }) {
  const ref = useRef(null);
  const ov = item.ov ?? {};

  useEffect(() => {
    if (isActive) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [isActive]);

  // Placeholder shows what the line inherits from the layer.
  const inherited = (f) => {
    if (setting[f]) return setting[f];
    if (f === "height" || (f === "width" && item.needsWidth)) return "required";
    return "auto";
  };

  return (
    <li
      ref={ref}
      className={`item${isActive ? " active" : ""}${isHover ? " hovered" : ""}${item.included ? "" : " excluded"}`}
      onMouseEnter={() => onHover({ layer: layerName, item: item.id })}
      onMouseLeave={() => onHover(null)}
    >
      <div className="item-head" onClick={() => onActivate(layerName, item.id)}>
        <input
          type="checkbox"
          checked={item.included}
          title={item.included ? "Exclude from export" : "Include in export"}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onItemChange(item.id, { include: e.target.checked ? undefined : false })}
        />
        <span className="item-n">#{item.n}</span>
        <span className="item-label">{item.label}</span>
        {item.overridden && <span className="item-dot" title="Has its own values" />}
        {Object.keys(item.issues).length > 0 && (
          <span className="item-warn" title="Missing values">
            !
          </span>
        )}
        <span className="item-size">{item.size != null ? formatSize(item.size, unit) : ""}</span>
      </div>
      {isActive && (
        <div className="item-body">
          <div className="field-row">
            {["width", "height", "length"].map((f) => (
              <NumberField
                key={f}
                label={f[0].toUpperCase() + f.slice(1)}
                unit={unit}
                value={ov[f]}
                placeholder={inherited(f)}
                invalid={item.issues[f]}
                onChange={(v) => onItemChange(item.id, { [f]: v })}
              />
            ))}
          </div>
          <p className="muted small">
            Empty fields use the layer defaults.{" "}
            {item.overridden && (
              <button className="link" onClick={() => onItemChange(item.id, { width: "", height: "", length: "" })}>
                Reset
              </button>
            )}
          </p>
        </div>
      )}
    </li>
  );
}

function ItemList({ layerName, items, setting, unit, hover, active, handlers }) {
  const [showAll, setShowAll] = useState(false);
  const activeIndex = active?.layer === layerName ? items.findIndex((i) => i.id === active.item) : -1;
  const limit = showAll || activeIndex >= LIST_LIMIT ? items.length : LIST_LIMIT;
  const included = items.filter((i) => i.included).length;

  return (
    <div className="items">
      <div className="items-head">
        <span className="field-label">
          Lines · {included} of {items.length} included
        </span>
        <span className="items-bulk">
          <button className="link" onClick={() => handlers.onItemsBulk(layerName, true)}>
            All
          </button>
          <button className="link" onClick={() => handlers.onItemsBulk(layerName, false)}>
            None
          </button>
        </span>
      </div>
      <ul className="item-list">
        {items.slice(0, limit).map((item) => (
          <ItemRow
            key={item.id}
            item={item}
            layerName={layerName}
            setting={setting}
            unit={unit}
            isActive={active?.item === item.id}
            isHover={hover?.item === item.id}
            onItemChange={handlers.onItemChange}
            onHover={handlers.onHover}
            onActivate={handlers.onActivate}
          />
        ))}
      </ul>
      {items.length > limit && (
        <button className="link small show-all" onClick={() => setShowAll(true)}>
          Show all {items.length.toLocaleString()} lines
        </button>
      )}
    </div>
  );
}

function LayerRow({ layer, setting, status, items, unit, classes, focus, hover, active, handlers }) {
  const { counts } = layer;
  const ref = useRef(null);
  const [flash, setFlash] = useState(false);
  const convertible = counts.lines + counts.closed + counts.circles + counts.blocks > 0;
  const { short, prefix } = splitLayerName(layer.name);
  const isHover = hover?.layer === layer.name && !hover.item;
  const widthRequired = items.some((i) => i.needsWidth && i.included);

  // Picked on the drawing: bring the row into view and flash it.
  useEffect(() => {
    if (focus?.name !== layer.name || focus.item) return;
    ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 900);
    return () => clearTimeout(t);
  }, [focus, layer.name]);

  return (
    <li
      ref={ref}
      className={`layer${setting.selected ? " selected" : ""}${isHover ? " hovered" : ""}${flash ? " flash" : ""}${convertible ? "" : " disabled"}`}
    >
      <label
        className="layer-head"
        title={layer.name}
        onMouseEnter={() => handlers.onHover({ layer: layer.name, item: null })}
        onMouseLeave={() => handlers.onHover(null)}
      >
        <input
          type="checkbox"
          checked={setting.selected}
          disabled={!convertible}
          onChange={(e) => handlers.onChange(layer.name, { selected: e.target.checked })}
        />
        <span className="swatch" style={{ background: readable(layer.color) }} />
        <span className="layer-name">{short}</span>
        <span className="layer-meta">
          {prefix && <span className="layer-prefix">{prefix} · </span>}
          {summary(counts)}
        </span>
      </label>

      {setting.selected && (
        <div className="layer-body">
          <label className="field wide">
            <span className="field-label">IFC class</span>
            <select
              value={setting.ifc_class}
              onChange={(e) => handlers.onChange(layer.name, { ifc_class: e.target.value })}
            >
              {classes.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/^Ifc/, "")}
                </option>
              ))}
            </select>
          </label>
          <div className="field-group">
            <span className="field-label">Layer defaults</span>
            <div className="field-row">
              {["width", "height", "length"].map((f) => (
                <NumberField
                  key={f}
                  label={f[0].toUpperCase() + f.slice(1)}
                  unit={unit}
                  value={setting[f]}
                  placeholder={f === "height" || (f === "width" && widthRequired) ? "required" : "auto"}
                  invalid={status.issues[f]}
                  onChange={(v) => handlers.onChange(layer.name, { [f]: v })}
                />
              ))}
            </div>
          </div>
          <ItemList
            layerName={layer.name}
            items={items}
            setting={setting}
            unit={unit}
            hover={hover}
            active={active}
            handlers={handlers}
          />
        </div>
      )}
    </li>
  );
}

export default function LayerPanel({
  layers,
  settings,
  statusByLayer,
  itemsByLayer,
  unit,
  classes,
  focus,
  hover,
  active,
  handlers,
}) {
  const [query, setQuery] = useState("");

  // A layer picked on the drawing must not be hidden by the filter.
  useEffect(() => {
    if (focus && !focus.name.toLowerCase().includes(query.trim().toLowerCase())) setQuery("");
  }, [focus]); // eslint-disable-line react-hooks/exhaustive-deps

  const q = query.trim().toLowerCase();
  const visible = q ? layers.filter((l) => l.name.toLowerCase().includes(q)) : layers;
  const selectedCount = layers.filter((l) => settings[l.name].selected).length;

  return (
    <section className="panel-section grow">
      <div className="section-head">
        <h2>Layers</h2>
        <span className="muted small">
          {selectedCount} of {layers.length} selected
        </span>
      </div>
      {layers.length > 8 && (
        <input
          className="search"
          type="search"
          placeholder="Filter layers"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      )}
      <ul className="layer-list">
        {visible.map((layer) => (
          <LayerRow
            key={layer.name}
            layer={layer}
            setting={settings[layer.name]}
            status={statusByLayer.get(layer.name) ?? { issues: {} }}
            items={itemsByLayer.get(layer.name) ?? []}
            unit={unit}
            classes={classes}
            focus={focus}
            hover={hover}
            active={active}
            handlers={handlers}
          />
        ))}
      </ul>
    </section>
  );
}
