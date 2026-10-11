import { useCallback, useEffect, useRef, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { supabase } from "@/integrations/supabase/client";
import { type Canvas, type Cursor, type El, type ElMap, type Peer, fromCanvas, mergeElements, toCanvas } from "./types";

export type SessionEvent = { locked?: boolean; status?: string; revoked?: boolean };

type Opts = {
  sessionId: string;
  me: Peer;
  initial: unknown;
  canEdit: boolean;
  save: (canvas: Canvas) => Promise<void>;
  onSession?: ((e: SessionEvent) => void) | undefined;
};

export function useRoom({ sessionId, me, initial, canEdit, save, onSession }: Opts) {
  const [els, setEls] = useState<ElMap>(() => fromCanvas(initial));
  const elsRef = useRef(els);
  const chRef = useRef<RealtimeChannel | null>(null);
  const [peers, setPeers] = useState<Peer[]>([]);
  const [cursors, setCursors] = useState<Record<string, Cursor>>({});
  const [conn, setConn] = useState<"connecting" | "live" | "offline">("connecting");
  const [saveState, setSaveState] = useState<"saved" | "dirty" | "saving" | "error">("saved");

  const saveRef = useRef(save);
  saveRef.current = save;
  const onSessionRef = useRef(onSession);
  onSessionRef.current = onSession;
  const canEditRef = useRef(canEdit);
  canEditRef.current = canEdit;

  const dirty = useRef(false);
  const saveTimer = useRef<number | undefined>(undefined);
  const outbox = useRef<Record<string, El>>({});
  const outTimer = useRef<number | undefined>(undefined);
  const lastCursor = useRef(0);

  const apply = useCallback((incoming: El[]) => {
    const next = mergeElements(elsRef.current, incoming);
    if (next) {
      elsRef.current = next;
      setEls(next);
    }
  }, []);

  const flushSave = useCallback(async () => {
    if (!dirty.current) return;
    dirty.current = false;
    setSaveState("saving");
    try {
      await saveRef.current(toCanvas(elsRef.current));
      setSaveState(dirty.current ? "dirty" : "saved");
    } catch {
      dirty.current = true;
      setSaveState("error");
      window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(flushSave, 4000);
    }
  }, []);

  const flushOutbox = useCallback(() => {
    outTimer.current = undefined;
    const batch = Object.values(outbox.current);
    outbox.current = {};
    if (batch.length) chRef.current?.send({ type: "broadcast", event: "op", payload: { els: batch } });
  }, []);

  const commit = useCallback(
    (changes: El[]) => {
      if (!canEditRef.current || !changes.length) return;
      const now = Date.now();
      const stamped = changes.map((c) => ({ ...c, u: now, by: me.id }) as El);
      apply(stamped);
      for (const s of stamped) outbox.current[s.id] = s;
      if (!outTimer.current) outTimer.current = window.setTimeout(flushOutbox, 40);
      dirty.current = true;
      setSaveState("dirty");
      window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(flushSave, 1200);
    },
    [apply, flushOutbox, flushSave, me.id],
  );

  const sendCursor = useCallback(
    (x: number, y: number) => {
      const t = Date.now();
      if (t - lastCursor.current < 60) return;
      lastCursor.current = t;
      chRef.current?.send({
        type: "broadcast",
        event: "cursor",
        payload: { id: me.id, name: me.name, color: me.color, x, y },
      });
    },
    [me.id, me.name, me.color],
  );

  const broadcastSession = useCallback((payload: SessionEvent) => {
    chRef.current?.send({ type: "broadcast", event: "session", payload });
  }, []);

  useEffect(() => {
    const ch = supabase.channel(`room:${sessionId}`, {
      config: { broadcast: { self: false }, presence: { key: me.id } },
    });
    ch.on("broadcast", { event: "op" }, ({ payload }) => apply(payload.els as El[]))
      .on("broadcast", { event: "sync-req" }, () => {
        const all = Object.values(elsRef.current);
        if (all.length) ch.send({ type: "broadcast", event: "sync", payload: { els: all } });
      })
      .on("broadcast", { event: "sync" }, ({ payload }) => apply(payload.els as El[]))
      .on("broadcast", { event: "cursor" }, ({ payload }) =>
        setCursors((c) => ({ ...c, [payload.id]: { ...(payload as Cursor), t: Date.now() } })),
      )
      .on("broadcast", { event: "session" }, ({ payload }) => onSessionRef.current?.(payload as SessionEvent))
      .on("presence", { event: "sync" }, () => {
        const st = ch.presenceState<Peer>();
        setPeers(Object.values(st).map((arr) => arr[0]).filter(Boolean) as Peer[]);
      })
      .subscribe(async (status) => {
        if (status === "SUBSCRIBED") {
          setConn("live");
          await ch.track(me);
          ch.send({ type: "broadcast", event: "sync-req", payload: {} });
        } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
          setConn("offline");
        }
      });
    chRef.current = ch;

    const onOnline = () => setConn((c) => (c === "offline" ? "connecting" : c));
    window.addEventListener("online", onOnline);
    const prune = window.setInterval(() => {
      const cutoff = Date.now() - 6000;
      setCursors((c) => {
        const n = Object.fromEntries(Object.entries(c).filter(([, v]) => v.t > cutoff));
        return Object.keys(n).length === Object.keys(c).length ? c : n;
      });
    }, 3000);

    return () => {
      window.removeEventListener("online", onOnline);
      window.clearInterval(prune);
      void flushSave();
      supabase.removeChannel(ch);
      chRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, me.id]);

  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => {
      if (dirty.current) {
        void flushSave();
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [flushSave]);

  return { els, commit, peers, cursors, conn, saveState, sendCursor, broadcastSession };
}
