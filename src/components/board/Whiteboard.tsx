import { useEffect, useMemo, useRef, useState } from "react";
import {
  MousePointer2,
  Hand,
  StickyNote,
  Type,
  Spline,
  Pencil,
  Trash2,
  ZoomIn,
  ZoomOut,
  Maximize,
} from "lucide-react";
import { PALETTE, PALETTE_BY_ID } from "./palette";
import { type Cursor, type EdgeEl, type El, type ElMap, type NodeEl, type NoteEl, type TextEl, newId } from "./types";
import { cn } from "@/lib/utils";

type Tool = "select" | "hand" | "node" | "note" | "text" | "connect" | "pen";
type View = { x: number; y: number; z: number };
type Drag =
  | { type: "pan"; sx: number; sy: number; vx: number; vy: number }
  | { type: "move"; id: string; dx: number; dy: number }
  | { type: "resize"; id: string }
  | { type: "pen"; points: number[] }
  | { type: "connect"; from: string };

type Props = {
  elements: ElMap;
  commit: (els: El[]) => void;
  readOnly: boolean;
  cursors: Record<string, Cursor>;
  onCursor: (x: number, y: number) => void;
};

type Boxy = NodeEl | NoteEl;

function edgePoint(b: Boxy, tx: number, ty: number) {
  const cx = b.x + b.w / 2;
  const cy = b.y + b.h / 2;
  const dx = tx - cx;
  const dy = ty - cy;
  if (!dx && !dy) return { x: cx, y: cy };
  const t = Math.min(b.w / 2 / Math.abs(dx || 1e-9), b.h / 2 / Math.abs(dy || 1e-9));
  return { x: cx + dx * t, y: cy + dy * t };
}

export function Whiteboard({ elements, commit, readOnly, cursors, onCursor }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tool, setTool] = useState<Tool>("select");
  const [component, setComponent] = useState("service");
  const [view, setView] = useState<View>({ x: 0, y: 0, z: 1 });
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<number[] | null>(null);
  const [ghost, setGhost] = useState<{ from: string; x: number; y: number } | null>(null);
  const drag = useRef<Drag | null>(null);
  const space = useRef(false);

  const list = useMemo(() => Object.values(elements).filter((e) => !e.deleted), [elements]);
  const boxes = useMemo(() => {
    const m: Record<string, Boxy> = {};
    for (const e of list) if (e.kind === "node" || e.kind === "note") m[e.id] = e;
    return m;
  }, [list]);

  useEffect(() => {
    if (readOnly) {
      setTool((t) => (t === "hand" ? t : "select"));
      setEditing(null);
    }
  }, [readOnly]);

  const toWorld = (cx: number, cy: number) => {
    const r = svgRef.current!.getBoundingClientRect();
    return { x: (cx - r.left - view.x) / view.z, y: (cy - r.top - view.y) / view.z };
  };

  // wheel: zoom with ctrl/meta (and pinch), otherwise pan
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      setView((v) => {
        if (e.ctrlKey || e.metaKey) {
          const z = Math.min(3, Math.max(0.2, v.z * Math.exp(-e.deltaY * 0.01)));
          const px = e.clientX - r.left;
          const py = e.clientY - r.top;
          return { z, x: px - ((px - v.x) * z) / v.z, y: py - ((py - v.y) * z) / v.z };
        }
        return { ...v, x: v.x - e.deltaX, y: v.y - e.deltaY };
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  const deleteSelected = () => {
    if (!selected || readOnly) return;
    const el = elements[selected];
    if (!el) return;
    const dead: El[] = [{ ...el, deleted: true }];
    for (const e of list) if (e.kind === "edge" && (e.from === selected || e.to === selected)) dead.push({ ...e, deleted: true });
    commit(dead);
    setSelected(null);
  };

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA") return;
      if (e.code === "Space") space.current = true;
      if (e.key === "Delete" || e.key === "Backspace") deleteSelected();
      if (e.key === "Escape") {
        setSelected(null);
        setTool("select");
      }
      const map: Record<string, Tool> = { v: "select", h: "hand", n: "note", t: "text", c: "connect", p: "pen", b: "node" };
      const k = map[e.key.toLowerCase()];
      if (k && !e.metaKey && !e.ctrlKey && (!readOnly || k === "select" || k === "hand")) setTool(k);
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") space.current = false;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  });

  const onBgDown = (e: React.PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    const p = toWorld(e.clientX, e.clientY);
    setEditing(null);
    if (tool === "hand" || space.current || e.button === 1 || readOnly || tool === "select" || tool === "connect") {
      setSelected(null);
      drag.current = { type: "pan", sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
      return;
    }
    if (tool === "pen") {
      drag.current = { type: "pen", points: [p.x, p.y] };
      setDraft([p.x, p.y]);
      return;
    }
    const id = newId();
    let el: El;
    if (tool === "node") {
      el = { id, u: 0, kind: "node", component, x: p.x - 70, y: p.y - 32, w: 140, h: 64, label: PALETTE_BY_ID[component]?.label ?? "Service" };
    } else if (tool === "note") {
      el = { id, u: 0, kind: "note", x: p.x - 90, y: p.y - 60, w: 180, h: 120, text: "" };
    } else {
      el = { id, u: 0, kind: "text", x: p.x, y: p.y, text: "" };
    }
    commit([el]);
    setSelected(id);
    if (tool !== "node") setEditing(id);
    setTool("select");
  };

  const onElDown = (e: React.PointerEvent, el: El) => {
    if (tool === "hand" || space.current || e.button === 1) return; // bubble to bg pan
    e.stopPropagation();
    svgRef.current!.setPointerCapture(e.pointerId);
    setSelected(el.id);
    if (readOnly) return;
    const p = toWorld(e.clientX, e.clientY);
    if (tool === "connect" && (el.kind === "node" || el.kind === "note")) {
      drag.current = { type: "connect", from: el.id };
      setGhost({ from: el.id, x: p.x, y: p.y });
      return;
    }
    if (el.kind === "node" || el.kind === "note" || el.kind === "text") {
      drag.current = { type: "move", id: el.id, dx: p.x - el.x, dy: p.y - el.y };
    }
  };

  const onMove = (e: React.PointerEvent) => {
    const p = toWorld(e.clientX, e.clientY);
    onCursor(p.x, p.y);
    const d = drag.current;
    if (!d) return;
    if (d.type === "pan") setView((v) => ({ ...v, x: d.vx + e.clientX - d.sx, y: d.vy + e.clientY - d.sy }));
    else if (d.type === "move") {
      const el = elements[d.id];
      if (el && "x" in el) commit([{ ...el, x: Math.round(p.x - d.dx), y: Math.round(p.y - d.dy) }]);
    } else if (d.type === "resize") {
      const el = elements[d.id] as Boxy | undefined;
      if (el) commit([{ ...el, w: Math.max(80, Math.round(p.x - el.x)), h: Math.max(44, Math.round(p.y - el.y)) }]);
    } else if (d.type === "pen") {
      d.points.push(Math.round(p.x), Math.round(p.y));
      setDraft([...d.points]);
    } else if (d.type === "connect") setGhost({ from: d.from, x: p.x, y: p.y });
  };

  const onUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.type === "pen") {
      if (d.points.length >= 4) commit([{ id: newId(), u: 0, kind: "path", points: d.points }]);
      setDraft(null);
    } else if (d.type === "connect") {
      setGhost(null);
      const p = toWorld(e.clientX, e.clientY);
      const target = Object.values(boxes).find(
        (b) => b.id !== d.from && p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h,
      );
      if (target) commit([{ id: newId(), u: 0, kind: "edge", from: d.from, to: target.id, label: "" }]);
    }
  };

  const zoomBy = (f: number) => {
    const r = svgRef.current!.getBoundingClientRect();
    setView((v) => {
      const z = Math.min(3, Math.max(0.2, v.z * f));
      const px = r.width / 2;
      const py = r.height / 2;
      return { z, x: px - ((px - v.x) * z) / v.z, y: py - ((py - v.y) * z) / v.z };
    });
  };
  const fit = () => {
    const bs = list.filter((e) => "x" in e) as (Boxy | TextEl)[];
    const r = svgRef.current!.getBoundingClientRect();
    if (!bs.length) return setView({ x: 0, y: 0, z: 1 });
    const minX = Math.min(...bs.map((b) => b.x));
    const minY = Math.min(...bs.map((b) => b.y));
    const maxX = Math.max(...bs.map((b) => b.x + ("w" in b ? b.w : 120)));
    const maxY = Math.max(...bs.map((b) => b.y + ("h" in b ? b.h : 24)));
    const z = Math.min(1.5, Math.max(0.2, Math.min(r.width / (maxX - minX + 160), r.height / (maxY - minY + 160))));
    setView({ z, x: r.width / 2 - ((minX + maxX) / 2) * z, y: r.height / 2 - ((minY + maxY) / 2) * z });
  };

  const editEl = editing ? elements[editing] : null;
  const gs = 32 * view.z;
  const cursorClass =
    tool === "hand" ? "cursor-grab" : tool === "pen" ? "cursor-crosshair" : tool === "select" ? "cursor-default" : "cursor-copy";

  return (
    <div className="relative h-full w-full overflow-hidden bg-canvas">
      <svg
        ref={svgRef}
        className={cn("h-full w-full touch-none select-none", cursorClass)}
        onPointerDown={onBgDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
      >
        <defs>
          <pattern id="grid-s" width={gs / 4} height={gs / 4} patternUnits="userSpaceOnUse" x={view.x} y={view.y}>
            <path d={`M ${gs / 4} 0 L 0 0 0 ${gs / 4}`} fill="none" stroke="var(--grid)" strokeWidth="0.5" />
          </pattern>
          <pattern id="grid" width={gs} height={gs} patternUnits="userSpaceOnUse" x={view.x} y={view.y}>
            <rect width={gs} height={gs} fill="url(#grid-s)" />
            <path d={`M ${gs} 0 L 0 0 0 ${gs}`} fill="none" stroke="var(--grid-strong)" strokeWidth="1" />
          </pattern>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--edge)" />
          </marker>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
        <g transform={`translate(${view.x} ${view.y}) scale(${view.z})`}>
          {list.map((el) => {
            if (el.kind !== "path") return null;
            const d = el.points.reduce((s, v, i) => s + (i % 2 ? `,${v}` : `${i ? " L" : "M"}${v}`), "");
            return (
              <g key={el.id} onPointerDown={(e) => onElDown(e, el)}>
                <path d={d} fill="none" stroke="transparent" strokeWidth={14} />
                <path d={d} fill="none" stroke={selected === el.id ? "var(--primary)" : "var(--ink)"} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
              </g>
            );
          })}
          {list.map((el) => (el.kind === "edge" ? <EdgeView key={el.id} el={el} boxes={boxes} selected={selected === el.id} onDown={onElDown} onEdit={() => !readOnly && setEditing(el.id)} /> : null))}
          {ghost && boxes[ghost.from] && (
            <line
              {...(() => {
                const a = edgePoint(boxes[ghost.from]!, ghost.x, ghost.y);
                return { x1: a.x, y1: a.y, x2: ghost.x, y2: ghost.y };
              })()}
              stroke="var(--edge)"
              strokeDasharray="6 4"
              strokeWidth={2}
              markerEnd="url(#arrow)"
            />
          )}
          {list.map((el) => {
            if (el.kind === "node") {
              const item = (PALETTE_BY_ID[el.component] ?? PALETTE[5])!;
              const Icon = item.icon;
              const sel = selected === el.id;
              return (
                <g key={el.id} onPointerDown={(e) => onElDown(e, el)} onDoubleClick={() => !readOnly && setEditing(el.id)} className="cursor-move">
                  <rect x={el.x} y={el.y} width={el.w} height={el.h} rx={10} fill="var(--node)" stroke={sel ? "var(--primary)" : item.tone} strokeWidth={sel ? 2.5 : 1.5} />
                  <rect x={el.x} y={el.y} width={4} height={el.h} rx={2} fill={item.tone} />
                  <Icon x={el.x + 14} y={el.y + el.h / 2 - 10} width={20} height={20} color={item.tone} />
                  <foreignObject x={el.x + 40} y={el.y + 4} width={Math.max(10, el.w - 48)} height={el.h - 8} className="pointer-events-none">
                    <div className="flex h-full items-center text-sm font-medium leading-tight text-foreground">
                      <span className="line-clamp-3 break-words">{el.label}</span>
                    </div>
                  </foreignObject>
                  {sel && !readOnly && <ResizeHandle el={el} onDown={(e) => { e.stopPropagation(); svgRef.current!.setPointerCapture(e.pointerId); drag.current = { type: "resize", id: el.id }; }} />}
                </g>
              );
            }
            if (el.kind === "note") {
              const sel = selected === el.id;
              return (
                <g key={el.id} onPointerDown={(e) => onElDown(e, el)} onDoubleClick={() => !readOnly && setEditing(el.id)} className="cursor-move">
                  <rect x={el.x} y={el.y} width={el.w} height={el.h} rx={4} fill="var(--note)" stroke={sel ? "var(--primary)" : "none"} strokeWidth={2.5} />
                  <foreignObject x={el.x + 10} y={el.y + 8} width={el.w - 20} height={el.h - 16} className="pointer-events-none">
                    <div className="h-full overflow-hidden whitespace-pre-wrap break-words text-sm text-note-foreground">{el.text || (editing === el.id ? "" : "Double-click to write")}</div>
                  </foreignObject>
                  {sel && !readOnly && <ResizeHandle el={el} onDown={(e) => { e.stopPropagation(); svgRef.current!.setPointerCapture(e.pointerId); drag.current = { type: "resize", id: el.id }; }} />}
                </g>
              );
            }
            if (el.kind === "text") {
              return (
                <text
                  key={el.id}
                  x={el.x}
                  y={el.y}
                  dominantBaseline="hanging"
                  onPointerDown={(e) => onElDown(e, el)}
                  onDoubleClick={() => !readOnly && setEditing(el.id)}
                  className="cursor-move font-display"
                  fontSize={18}
                  fill={selected === el.id ? "var(--primary)" : "var(--ink)"}
                >
                  {el.text || (editing === el.id ? "" : "Text")}
                </text>
              );
            }
            return null;
          })}
          {draft && (
            <polyline points={draft.join(" ")} fill="none" stroke="var(--ink)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
          )}
          {Object.values(cursors).map((c) => (
            <g key={c.id} transform={`translate(${c.x} ${c.y}) scale(${1 / view.z})`} className="pointer-events-none transition-transform duration-75">
              <path d="M0,0 L0,16 L4.5,12 L8,19 L10.5,18 L7,11 L13,11 z" fill={c.color} stroke="var(--background)" strokeWidth={1} />
              <foreignObject x={12} y={16} width={160} height={24}>
                <span className="inline-block rounded px-1.5 py-0.5 text-[11px] font-medium text-primary-foreground" style={{ background: c.color }}>{c.name}</span>
              </foreignObject>
            </g>
          ))}
        </g>
      </svg>

      {editEl && (
        <EditOverlay
          key={editEl.id}
          el={editEl}
          view={view}
          boxes={boxes}
          onDone={(text) => {
            setEditing(null);
            if (editEl.kind === "node" || editEl.kind === "edge") commit([{ ...editEl, label: text }]);
            else if (editEl.kind === "note" || editEl.kind === "text") {
              if (!text.trim() && editEl.kind === "text") commit([{ ...editEl, deleted: true }]);
              else commit([{ ...editEl, text }]);
            }
          }}
        />
      )}

      {/* Toolbar */}
      <div className="absolute left-1/2 top-3 flex -translate-x-1/2 items-center gap-1 rounded-xl border bg-card/95 p-1 shadow-glow backdrop-blur">
        <ToolBtn active={tool === "select"} onClick={() => setTool("select")} label="Select (V)"><MousePointer2 className="size-4" /></ToolBtn>
        <ToolBtn active={tool === "hand"} onClick={() => setTool("hand")} label="Pan (H / hold Space)"><Hand className="size-4" /></ToolBtn>
        {!readOnly && (
          <>
            <div className="mx-1 h-6 w-px bg-border" />
            <ToolBtn active={tool === "connect"} onClick={() => setTool("connect")} label="Connect (C) — drag from one box to another"><Spline className="size-4" /></ToolBtn>
            <ToolBtn active={tool === "note"} onClick={() => setTool("note")} label="Sticky note (N)"><StickyNote className="size-4" /></ToolBtn>
            <ToolBtn active={tool === "text"} onClick={() => setTool("text")} label="Text (T)"><Type className="size-4" /></ToolBtn>
            <ToolBtn active={tool === "pen"} onClick={() => setTool("pen")} label="Draw (P)"><Pencil className="size-4" /></ToolBtn>
            <ToolBtn active={false} onClick={deleteSelected} label="Delete selected (Del)" disabled={!selected}><Trash2 className="size-4" /></ToolBtn>
          </>
        )}
      </div>

      {/* Palette */}
      {!readOnly && (
        <div className="absolute left-3 top-1/2 flex max-h-[80%] -translate-y-1/2 flex-col gap-0.5 overflow-y-auto rounded-xl border bg-card/95 p-1.5 shadow-glow backdrop-blur">
          <div className="px-2 pb-1 pt-0.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Components</div>
          {PALETTE.map((p) => {
            const Icon = p.icon;
            const active = tool === "node" && component === p.id;
            return (
              <button
                key={p.id}
                onClick={() => {
                  setComponent(p.id);
                  setTool("node");
                }}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent",
                  active && "bg-accent ring-1 ring-primary",
                )}
              >
                <Icon className="size-4 shrink-0" style={{ color: p.tone }} />
                {p.label}
              </button>
            );
          })}
          <div className="px-2 pt-1 text-[10px] text-muted-foreground">Pick, then click canvas</div>
        </div>
      )}

      {/* Zoom */}
      <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded-xl border bg-card/95 p-1 backdrop-blur">
        <ToolBtn active={false} onClick={() => zoomBy(1 / 1.2)} label="Zoom out"><ZoomOut className="size-4" /></ToolBtn>
        <span className="w-12 text-center font-mono text-xs text-muted-foreground">{Math.round(view.z * 100)}%</span>
        <ToolBtn active={false} onClick={() => zoomBy(1.2)} label="Zoom in"><ZoomIn className="size-4" /></ToolBtn>
        <ToolBtn active={false} onClick={fit} label="Fit to content"><Maximize className="size-4" /></ToolBtn>
      </div>
    </div>
  );
}

function ToolBtn({ active, onClick, label, children, disabled }: { active: boolean; onClick: () => void; label: string; children: React.ReactNode; disabled?: boolean }) {
  return (
    <button
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "grid size-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-40",
        active && "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
      )}
    >
      {children}
    </button>
  );
}

function ResizeHandle({ el, onDown }: { el: Boxy; onDown: (e: React.PointerEvent) => void }) {
  return <rect x={el.x + el.w - 6} y={el.y + el.h - 6} width={12} height={12} rx={2} fill="var(--primary)" className="cursor-nwse-resize" onPointerDown={onDown} />;
}

function EdgeView({ el, boxes, selected, onDown, onEdit }: { el: EdgeEl; boxes: Record<string, Boxy>; selected: boolean; onDown: (e: React.PointerEvent, el: El) => void; onEdit: () => void }) {
  const a = boxes[el.from];
  const b = boxes[el.to];
  if (!a || !b) return null;
  const p1 = edgePoint(a, b.x + b.w / 2, b.y + b.h / 2);
  const p2 = edgePoint(b, a.x + a.w / 2, a.y + a.h / 2);
  const mx = (p1.x + p2.x) / 2;
  const my = (p1.y + p2.y) / 2;
  return (
    <g onPointerDown={(e) => onDown(e, el)} onDoubleClick={onEdit} className="cursor-pointer">
      <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="transparent" strokeWidth={14} />
      <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="var(--edge)" strokeWidth={selected ? 3 : 1.75} markerEnd="url(#arrow)" opacity={selected ? 1 : 0.85} />
      {el.label && (
        <foreignObject x={mx - 80} y={my - 12} width={160} height={24} className="pointer-events-none">
          <div className="flex justify-center">
            <span className="rounded bg-background px-1.5 py-0.5 font-mono text-[11px] text-primary">{el.label}</span>
          </div>
        </foreignObject>
      )}
    </g>
  );
}

function EditOverlay({ el, view, boxes, onDone }: { el: El; view: View; boxes: Record<string, Boxy>; onDone: (t: string) => void }) {
  const initial = el.kind === "node" || el.kind === "edge" ? el.label : el.kind === "path" ? "" : el.text;
  const [val, setVal] = useState(initial);
  let x = 0, y = 0, w = 180, h = 32;
  if (el.kind === "node" || el.kind === "note") {
    x = el.x; y = el.y; w = el.w; h = el.h;
  } else if (el.kind === "text") {
    x = el.x; y = el.y; w = 260; h = 32;
  } else if (el.kind === "edge" && boxes[el.from] && boxes[el.to]) {
    const a = boxes[el.from]!, b = boxes[el.to]!;
    x = (a.x + a.w / 2 + b.x + b.w / 2) / 2 - 90; y = (a.y + a.h / 2 + b.y + b.h / 2) / 2 - 16;
  }
  const style = { left: view.x + x * view.z, top: view.y + y * view.z, width: w * view.z, height: h * view.z };
  const multiline = el.kind === "note";
  const common = {
    autoFocus: true,
    value: val,
    onFocus: (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => e.currentTarget.select(),
    onBlur: () => onDone(val),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Escape" || (e.key === "Enter" && (!multiline || e.metaKey || e.ctrlKey))) {
        e.preventDefault();
        onDone(val);
      }
    },
    className: cn(
      "absolute z-10 rounded-md border-2 border-primary px-2 text-sm outline-none",
      multiline ? "resize-none bg-note py-2 text-note-foreground" : "bg-card text-foreground",
    ),
    style,
  };
  return multiline ? (
    <textarea {...common} onChange={(e) => setVal(e.target.value)} />
  ) : (
    <input {...common} placeholder={el.kind === "edge" ? "Label (e.g. HTTPS)" : "Label"} onChange={(e) => setVal(e.target.value)} />
  );
}
