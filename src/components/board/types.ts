export type ElBase = { id: string; u: number; by?: string; deleted?: boolean };
export type NodeEl = ElBase & {
  kind: "node";
  component: string;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
};
export type NoteEl = ElBase & { kind: "note"; x: number; y: number; w: number; h: number; text: string };
export type TextEl = ElBase & { kind: "text"; x: number; y: number; text: string };
export type EdgeEl = ElBase & { kind: "edge"; from: string; to: string; label: string };
export type PathEl = ElBase & { kind: "path"; points: number[] };
export type El = NodeEl | NoteEl | TextEl | EdgeEl | PathEl;
export type ElMap = Record<string, El>;

export type Peer = { id: string; name: string; role: "interviewer" | "candidate"; color: string };
export type Cursor = { id: string; name: string; color: string; x: number; y: number; t: number };

export type Canvas = { elements: El[] };

export function newId() {
  return crypto.randomUUID();
}

/** Last-writer-wins merge by element timestamp. Returns null when nothing changed. */
export function mergeElements(current: ElMap, incoming: El[]): ElMap | null {
  let next: ElMap | null = null;
  for (const e of incoming) {
    const cur = (next ?? current)[e.id];
    if (!cur || cur.u <= e.u) {
      if (!next) next = { ...current };
      next[e.id] = e;
    }
  }
  return next;
}

export function toCanvas(map: ElMap): Canvas {
  return { elements: Object.values(map).filter((e) => !e.deleted) };
}

export function fromCanvas(c: unknown): ElMap {
  const els = (c as Canvas | null)?.elements ?? [];
  const m: ElMap = {};
  for (const e of els) m[e.id] = e;
  return m;
}

const COLORS: string[] = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
export function colorFor(id: string) {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length]!;
}
