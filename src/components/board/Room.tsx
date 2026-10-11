import { useEffect, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, Cloud, CloudOff, Loader2, Lock, WifiOff } from "lucide-react";
import { Whiteboard } from "./Whiteboard";
import { useRoom, type SessionEvent } from "./useRoom";
import type { Canvas, Peer } from "./types";
import { cn } from "@/lib/utils";

type Props = {
  sessionId: string;
  title: string;
  prompt: string;
  status: string;
  startedAt: string | null;
  durationMinutes: number;
  me: Peer;
  initialCanvas: unknown;
  canEdit: boolean;
  lockedNotice?: string | null;
  save: (c: Canvas) => Promise<void>;
  onSession?: (e: SessionEvent) => void;
  controls?: (api: { broadcastSession: (e: SessionEvent) => void }) => ReactNode;
  back?: ReactNode;
};

export function Room(p: Props) {
  const room = useRoom({
    sessionId: p.sessionId,
    me: p.me,
    initial: p.initialCanvas,
    canEdit: p.canEdit,
    save: p.save,
    onSession: p.onSession,
  });
  const [showPrompt, setShowPrompt] = useState(true);

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-card px-3">
        {p.back}
        <div className="min-w-0">
          <div className="truncate font-display text-sm font-semibold">{p.title}</div>
          <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
            <StatusDot status={p.status} />
            <Timer status={p.status} startedAt={p.startedAt} minutes={p.durationMinutes} />
          </div>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <SaveBadge conn={room.conn} save={room.saveState} />
          <div className="flex -space-x-2">
            {room.peers.map((peer) => (
              <div
                key={peer.id}
                title={`${peer.name} · ${peer.role}${peer.id === p.me.id ? " (you)" : ""}`}
                className="grid size-8 place-items-center rounded-full border-2 border-card text-xs font-semibold text-primary-foreground"
                style={{ background: peer.color }}
              >
                {peer.name.slice(0, 2).toUpperCase()}
              </div>
            ))}
          </div>
          {p.controls?.({ broadcastSession: room.broadcastSession })}
        </div>
      </header>

      {room.conn === "offline" && (
        <div className="flex items-center justify-center gap-2 bg-warning/15 py-1 text-xs text-warning">
          <WifiOff className="size-3.5" /> Connection lost — reconnecting. Your changes will sync when back online.
        </div>
      )}
      {p.lockedNotice && (
        <div className="flex items-center justify-center gap-2 bg-accent py-1 text-xs text-muted-foreground">
          <Lock className="size-3.5" /> {p.lockedNotice}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className={cn("relative shrink-0 border-r bg-card transition-all", showPrompt ? "w-80" : "w-0")}>
          <button
            onClick={() => setShowPrompt((s) => !s)}
            className="absolute -right-3 top-4 z-10 grid size-6 place-items-center rounded-full border bg-card text-muted-foreground hover:text-foreground"
            aria-label={showPrompt ? "Hide prompt" : "Show prompt"}
          >
            {showPrompt ? <ChevronLeft className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          </button>
          {showPrompt && (
            <div className="h-full overflow-y-auto p-5">
              <div className="font-mono text-[10px] uppercase tracking-widest text-primary">Prompt</div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                {p.prompt || "No prompt has been set for this interview."}
              </p>
              <div className="mt-8 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Participants</div>
              <ul className="mt-3 space-y-2">
                {room.peers.map((peer) => (
                  <li key={peer.id} className="flex items-center gap-2 text-sm">
                    <span className="size-2 rounded-full" style={{ background: peer.color }} />
                    {peer.name}
                    {peer.id === p.me.id && <span className="text-muted-foreground">(you)</span>}
                    <span className="ml-auto font-mono text-[10px] uppercase text-muted-foreground">{peer.role}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
        <main className="min-w-0 flex-1">
          <Whiteboard
            elements={room.els}
            commit={room.commit}
            readOnly={!p.canEdit}
            cursors={Object.fromEntries(Object.entries(room.cursors).filter(([id]) => room.peers.some((x) => x.id === id)))}
            onCursor={room.sendCursor}
          />
        </main>
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = { draft: "bg-muted-foreground", live: "bg-success animate-pulse", ended: "bg-destructive" };
  return (
    <span className="flex items-center gap-1.5 uppercase">
      <span className={cn("size-1.5 rounded-full", map[status])} />
      {status === "draft" ? "not started" : status}
    </span>
  );
}

function Timer({ status, startedAt, minutes }: { status: string; startedAt: string | null; minutes: number }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  if (status !== "live" || !startedAt || now === null) return <span>· {minutes} min</span>;
  const el = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
  const over = el > minutes * 60;
  const mm = String(Math.floor(el / 60)).padStart(2, "0");
  const ss = String(el % 60).padStart(2, "0");
  return (
    <span className={cn(over && "text-warning")}>
      · {mm}:{ss} / {minutes}:00
    </span>
  );
}

function SaveBadge({ conn, save }: { conn: string; save: string }) {
  if (conn === "offline")
    return (
      <span className="flex items-center gap-1 text-xs text-warning">
        <CloudOff className="size-3.5" /> Offline
      </span>
    );
  if (save === "saving" || save === "dirty")
    return (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" /> Saving
      </span>
    );
  if (save === "error")
    return (
      <span className="flex items-center gap-1 text-xs text-destructive">
        <CloudOff className="size-3.5" /> Save failed, retrying
      </span>
    );
  return (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      <Cloud className="size-3.5" /> Saved
    </span>
  );
}
