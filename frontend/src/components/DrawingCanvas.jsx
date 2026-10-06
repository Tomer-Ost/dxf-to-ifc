import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { readable } from "../color.js";
import { formatSize, splitLayerName } from "../layerRules.js";

const MUTED = "#d4d7dc";
const HOVER = "#2563eb";
const HIT_PX = 6; // pick tolerance around lines, in screen pixels
const CLICK_PX = 4; // pointer travel below this is a click, not a pan

function makePath(flats, ox, oy) {
  const path = new Path2D();
  const box = [Infinity, Infinity, -Infinity, -Infinity];
  for (const flat of flats) {
    path.moveTo(flat[0] - ox, flat[1] - oy);
    for (let i = 0; i < flat.length; i += 2) {
      const x = flat[i] - ox;
      const y = flat[i + 1] - oy;
      if (i) path.lineTo(x, y);
      box[0] = Math.min(box[0], x);
      box[1] = Math.min(box[1], y);
      box[2] = Math.max(box[2], x);
      box[3] = Math.max(box[3], y);
    }
  }
  return { path, box };
}

/**
 * Build Path2D geometry once per drawing, in world units offset to the drawing
 * origin (keeps float precision for survey coordinates).
 *   layers: name -> { all, other, color, points }   (whole-layer drawing / picking)
 *   items:  id   -> { path, box, point }            (per-line drawing / picking,
 *                                                   including wall sides "<id>:<n>")
 */
function buildGeometry(drawing) {
  const [ox, oy] = drawing.extents;
  const layers = new Map();
  const items = new Map();
  for (const layer of drawing.layers) {
    const { items: its, other } = drawing.preview[layer.name];
    const flats = [...other];
    const points = [];
    for (const it of its) {
      flats.push(...it.paths);
      const point = it.point ? [it.point[0] - ox, it.point[1] - oy] : null;
      if (point && !it.paths.length) points.push(point);
      items.set(it.id, { ...makePath(it.paths, ox, oy), point });
      it.segments?.forEach((seg, i) => items.set(`${it.id}:${i + 1}`, { ...makePath([seg], ox, oy), point: null }));
    }
    layers.set(layer.name, {
      all: makePath(flats, ox, oy).path,
      other: makePath(other, ox, oy).path,
      color: readable(layer.color),
      points,
    });
  }
  return { layers, items };
}

/**
 * 2D preview of the DXF. Unselected layers are picked as a whole; inside selected
 * layers every line is its own target. Wheel zooms around the cursor, drag pans,
 * double-click on empty space fits.
 */
export default function DrawingCanvas({
  drawing,
  unit,
  selected,
  itemsByLayer, // selected layer -> [{ id, n, label, size, included, overridden }]
  hover, // { layer, item } | null
  active, // { layer, item } | null
  onHover,
  onPickLayer,
  onPickItem,
  onClear,
}) {
  const canvasRef = useRef(null);
  const view = useRef({ scale: 1, tx: 0, ty: 0 });
  const drag = useRef(null);
  const autoFit = useRef(true); // refit on resize until the user pans or zooms
  const [tip, setTip] = useState(null);

  const geo = useMemo(() => buildGeometry(drawing), [drawing]);
  const names = useMemo(() => drawing.layers.map((l) => l.name), [drawing]);
  const pickable = useMemo(
    () => new Set(drawing.layers.filter((l) => drawing.preview[l.name].items.length).map((l) => l.name)),
    [drawing],
  );

  // Bottom to top. Hit testing walks it in reverse so the visible line wins.
  const ordered = useMemo(
    () => [...names.filter((n) => !selected.has(n)), ...names.filter((n) => selected.has(n))],
    [names, selected],
  );

  const setViewTransform = (ctx) => {
    const dpr = window.devicePixelRatio || 1;
    const { scale, tx, ty } = view.current;
    ctx.setTransform(scale * dpr, 0, 0, -scale * dpr, tx * dpr, ty * dpr);
  };

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const { scale } = view.current;
    const px = (n) => n / scale;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setViewTransform(ctx);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    const dots = (points, color, r) => {
      ctx.fillStyle = color;
      for (const [x, y] of points) {
        ctx.beginPath();
        ctx.arc(x, y, px(r), 0, Math.PI * 2);
        ctx.fill();
      }
    };
    const strokeItem = (g, color, width, dash) => {
      ctx.setLineDash(dash ? [px(4), px(4)] : []);
      ctx.strokeStyle = color;
      ctx.lineWidth = px(width);
      ctx.stroke(g.path);
      if (g.point) dots([g.point], color, width + 1.5);
    };

    for (const name of ordered) {
      const L = geo.layers.get(name);
      const items = itemsByLayer.get(name);
      if (!items) {
        const isHover = hover?.layer === name && !hover.item;
        ctx.setLineDash([]);
        ctx.strokeStyle = isHover ? HOVER : MUTED;
        ctx.lineWidth = px(isHover ? 2 : 1);
        ctx.stroke(L.all);
        dots(L.points, ctx.strokeStyle, isHover ? 3.5 : 2.5);
        continue;
      }
      ctx.setLineDash([]);
      ctx.strokeStyle = L.color;
      ctx.lineWidth = px(1);
      ctx.stroke(L.other);
      for (const it of items) {
        const g = geo.items.get(it.id);
        if (it.included) strokeItem(g, L.color, it.overridden ? 2 : 1.25);
        else strokeItem(g, MUTED, 1, true);
      }
    }

    // Highlights on top of everything.
    const hl = (ref, width) => {
      const g = ref?.item && geo.items.get(ref.item);
      if (g) strokeItem(g, HOVER, width);
      return g;
    };
    hl(hover, 2.5);
    const g = hl(active, 3);
    if (g) {
      ctx.setLineDash([]);
      ctx.strokeStyle = HOVER;
      ctx.lineWidth = px(1);
      const [x0, y0, x1, y1] = g.box;
      const pad = px(6);
      ctx.strokeRect(x0 - pad, y0 - pad, x1 - x0 + pad * 2, y1 - y0 + pad * 2);
    }
  }, [geo, ordered, itemsByLayer, hover, active]);

  /** What is under a point given in CSS pixels: { layer, item } or null. */
  const hitTest = useCallback(
    (mx, my) => {
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      const { scale, tx, ty } = view.current;
      const wx = (mx - tx) / scale;
      const wy = (ty - my) / scale;
      const tol = HIT_PX / scale;
      const near = ([x, y]) => Math.hypot(x - wx, y - wy) <= tol;
      const inBox = ([x0, y0, x1, y1]) => wx >= x0 - tol && wx <= x1 + tol && wy >= y0 - tol && wy <= y1 + tol;

      ctx.save();
      setViewTransform(ctx);
      ctx.lineWidth = tol * 2;
      const stroked = (path) => ctx.isPointInStroke(path, mx * dpr, my * dpr);
      try {
        for (let i = ordered.length - 1; i >= 0; i--) {
          const name = ordered[i];
          if (!pickable.has(name)) continue;
          const items = itemsByLayer.get(name);
          if (items) {
            // the active line wins over neighbours drawn later
            const sorted = active
              ? [...items.filter((it) => it.id !== active.item), ...items.filter((it) => it.id === active.item)]
              : items;
            for (let j = sorted.length - 1; j >= 0; j--) {
              const g = geo.items.get(sorted[j].id);
              if (!inBox(g.box) && !(g.point && near(g.point))) continue;
              if (stroked(g.path) || (g.point && near(g.point))) return { layer: name, item: sorted[j].id };
            }
          } else {
            const L = geo.layers.get(name);
            if (stroked(L.all) || L.points.some(near)) return { layer: name, item: null };
          }
        }
        return null;
      } finally {
        ctx.restore();
      }
    },
    [geo, ordered, pickable, itemsByLayer, active],
  );

  const fit = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const [x0, y0, x1, y1] = drawing.extents;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const pad = 48;
    const dw = Math.max(x1 - x0, 1e-9);
    const dh = Math.max(y1 - y0, 1e-9);
    const scale = Math.min((w - pad * 2) / dw, (h - pad * 2) / dh);
    view.current = {
      scale,
      tx: (w - dw * scale) / 2,
      ty: h - (h - dh * scale) / 2,
    };
    autoFit.current = true;
    draw();
  }, [drawing, draw]);

  // Keep the backing store matched to the element size; refit on new drawings.
  useEffect(() => {
    const canvas = canvasRef.current;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(canvas.clientWidth * dpr);
      canvas.height = Math.round(canvas.clientHeight * dpr);
      if (autoFit.current) fit();
      else draw();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();
    return () => ro.disconnect();
  }, [draw, fit]);

  useEffect(fit, [drawing]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(draw, [draw]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const onWheel = (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const k = Math.exp(-e.deltaY * 0.0015);
      const v = view.current;
      autoFit.current = false;
      view.current = {
        scale: v.scale * k,
        tx: mx - (mx - v.tx) * k,
        ty: my - (my - v.ty) * k,
      };
      draw();
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [draw]);

  const local = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  };

  const describe = (hit) => {
    const { short } = splitLayerName(hit.layer);
    if (!hit.item) {
      return { title: short, sub: selected.has(hit.layer) ? "Click to deselect" : "Click to select layer" };
    }
    const it = itemsByLayer.get(hit.layer).find((i) => i.id === hit.item);
    const size = it.size != null ? ` · ${formatSize(it.size, unit)}` : "";
    return {
      title: `#${it.n} ${it.label}${size}`,
      sub: `${short}${it.included ? "" : " · excluded"} · click to edit`,
    };
  };

  const updateHover = (e) => {
    const [mx, my] = local(e);
    const hit = hitTest(mx, my);
    onHover(hit);
    setTip(hit ? { x: mx, y: my, ...describe(hit) } : null);
  };

  const onPointerDown = (e) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, moved: false, ...view.current };
  };
  const onPointerMove = (e) => {
    const d = drag.current;
    if (!d) {
      updateHover(e);
      return;
    }
    if (!d.moved && Math.hypot(e.clientX - d.x, e.clientY - d.y) < CLICK_PX) return;
    if (!d.moved) {
      d.moved = true;
      setTip(null);
    }
    autoFit.current = false;
    view.current = { scale: d.scale, tx: d.tx + e.clientX - d.x, ty: d.ty + e.clientY - d.y };
    draw();
  };
  const onPointerUp = (e) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (!d.moved) {
      const hit = hitTest(...local(e));
      if (!hit) onClear();
      else if (hit.item) onPickItem(hit.layer, hit.item);
      else onPickLayer(hit.layer);
    }
    updateHover(e);
  };
  const onPointerLeave = () => {
    if (drag.current) return;
    setTip(null);
    onHover(null);
  };
  const onDoubleClick = (e) => {
    if (!hitTest(...local(e))) fit();
  };

  return (
    <div className="canvas-wrap">
      <canvas
        ref={canvasRef}
        className={`canvas${tip ? " picking" : ""}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => (drag.current = null)}
        onPointerLeave={onPointerLeave}
        onDoubleClick={onDoubleClick}
      />
      {tip && (
        <div className="canvas-tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          <strong>{tip.title}</strong>
          <span>{tip.sub}</span>
        </div>
      )}
      <div className="canvas-tools">
        <button className="ghost small" onClick={fit} title="Fit drawing (double-click empty space)">
          Fit
        </button>
      </div>
      <div className="canvas-hint">Click a layer, then click its lines to edit them · scroll to zoom · drag to pan</div>
    </div>
  );
}
