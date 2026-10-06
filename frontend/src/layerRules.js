// Client-side mirror of the geometry rules in backend/app/ifc_builder.py.

export const FALLBACK_CLASSES = [
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
];

const GUESSES = [
  [/wall|wand|mur/i, "IfcWall"],
  [/slab|floor|deck/i, "IfcSlab"],
  [/col/i, "IfcColumn"],
  [/beam/i, "IfcBeam"],
  [/door/i, "IfcDoor"],
  [/wind|glaz/i, "IfcWindow"],
  [/roof/i, "IfcRoof"],
  [/stair/i, "IfcStair"],
  [/rail/i, "IfcRailing"],
  [/furn/i, "IfcFurniture"],
  [/ceil|cover/i, "IfcCovering"],
];

/** Bound xref layers ("xref-Plan$0$A-WALL", "xref|A-WALL") -> { short: "A-WALL", prefix: "xref-Plan" }. */
export function splitLayerName(name) {
  const m = name.match(/^(.*?)(?:\$0\$|\|)([^$|]+)$/);
  return m ? { short: m[2], prefix: m[1] } : { short: name, prefix: "" };
}

export function guessClass(layerName) {
  const { short } = splitLayerName(layerName);
  return GUESSES.find(([re]) => re.test(short))?.[1] ?? "IfcBuildingElementProxy";
}

export const FIELDS = ["width", "height", "length"];

const TYPE_LABEL = {
  LINE: "Line",
  ARC: "Arc",
  SPLINE: "Spline",
  ELLIPSE: "Ellipse",
  LWPOLYLINE: "Polyline",
  POLYLINE: "Polyline",
  CIRCLE: "Circle",
  INSERT: "Block",
  POINT: "Point",
};

function pathLength(flat) {
  let d = 0;
  for (let i = 2; i < flat.length; i += 2) d += Math.hypot(flat[i] - flat[i - 2], flat[i + 1] - flat[i - 1]);
  return d;
}

/**
 * Selectable items of a layer for the chosen IFC class. Closed polylines on a wall
 * layer are split into one item per side, matching how the converter explodes them.
 */
export function layerItems(preview, ifcClass) {
  const out = [];
  for (const it of preview.items) {
    if (it.kind === "outline" && ifcClass === "IfcWall" && it.segments) {
      it.segments.forEach((seg, i) =>
        out.push({ id: `${it.id}:${i + 1}`, kind: "line", label: "Wall side", paths: [seg], size: pathLength(seg) }),
      );
      continue;
    }
    let label = TYPE_LABEL[it.type] ?? it.type;
    let size = null;
    if (it.kind === "line") size = pathLength(it.paths[0]);
    else if (it.kind === "outline") {
      label = `Closed ${label.toLowerCase()}`;
      size = pathLength(it.paths[0]);
    } else if (it.kind === "circle") size = it.radius * 2;
    else if (it.kind === "block") label = `Block ${it.block}`;
    out.push({ ...it, label, size });
  }
  out.forEach((it, i) => {
    it.n = i + 1;
    it.needsWidth = needsWidth(it, ifcClass);
  });
  return out;
}

/** Width is needed whenever something is extruded along a line or boxed around a point. */
function needsWidth(item, ifcClass) {
  if (item.kind === "line" || item.kind === "block" || item.kind === "point") return true;
  return item.kind === "outline" && ifcClass === "IfcWall"; // closed curve without segments
}

const positive = (v) => v !== "" && v != null && Number(v) > 0;
const badEntry = (v) => v !== "" && v != null && !positive(v);

/** Effective values and problems for one item; layer values are the defaults. */
export function itemState(item, setting, ov = {}) {
  const values = Object.fromEntries(FIELDS.map((f) => [f, positive(ov[f]) ? ov[f] : setting[f]]));
  const included = ov.include !== false;
  const issues = {};
  if (included) {
    if (!positive(values.height)) issues.height = true;
    if (item.needsWidth && !positive(values.width)) issues.width = true;
  }
  for (const f of FIELDS) if (badEntry(ov[f])) issues[f] = true;
  return {
    included,
    values,
    issues,
    overridden: FIELDS.some((f) => positive(ov[f])),
  };
}

/** Problems on the layer default fields plus how many items still need values. */
export function layerStatus(items, setting, overrides) {
  const issues = {};
  let bad = 0;
  let included = 0;
  for (const item of items) {
    const ov = overrides[item.id];
    const st = itemState(item, setting, ov);
    if (st.included) included++;
    if (Object.keys(st.issues).length) bad++;
    if (!st.included) continue;
    // Missing values the item would inherit are flagged on the layer field.
    if (st.issues.height && !positive(ov?.height)) issues.height = true;
    if (st.issues.width && !positive(ov?.width)) issues.width = true;
  }
  for (const f of FIELDS) if (badEntry(setting[f])) issues[f] = true;
  return { issues, bad, included, ok: !bad && !Object.keys(issues).length };
}

export function initialSettings(layers) {
  return Object.fromEntries(
    layers.map((l) => [l.name, { selected: false, ifc_class: guessClass(l.name), width: "", height: "", length: "" }]),
  );
}

export function formatSize(v, unit) {
  if (v == null) return "";
  const digits = unit === "m" || unit === "ft" ? 2 : unit === "mm" ? 0 : 1;
  return `${v.toLocaleString(undefined, { maximumFractionDigits: digits })} ${unit}`;
}
