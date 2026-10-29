import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Room } from "@/components/board/Room";
import { colorFor, newId, type Canvas, type Peer } from "@/components/board/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Logo } from "@/components/Logo";
import type { Json } from "@/integrations/supabase/types";

export const Route = createFileRoute("/join/$token")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Join interview — Blueprint Interviews" },
      { name: "description", content: "Join a live system design interview." },
      { property: "og:title", content: "Join interview — Blueprint Interviews" },
      { property: "og:description", content: "Join a live system design interview." },
      { name: "robots", content: "noindex" },
    ],
  }),
  loader: async ({ params }) => {
    const { data, error } = await supabase.rpc("get_session_by_token", { _token: params.token });
    if (error) throw error;
    return data?.[0] ?? null;
  },
  component: JoinPage,
});

function JoinPage() {
  const session = Route.useLoaderData();
  const { token } = Route.useParams();
  const [name, setName] = useState("");
  const [joined, setJoined] = useState<Peer | null>(null);
  const [status, setStatus] = useState(session?.status ?? "draft");
  const [locked, setLocked] = useState(session?.candidate_editing_locked ?? false);
  const [revoked, setRevoked] = useState(false);

  useEffect(() => {
    const saved = sessionStorage.getItem(`bp-guest-${token}`);
    if (saved) setJoined(JSON.parse(saved));
    else setName(localStorage.getItem("bp-name") ?? "");
  }, [token]);

  const save = useMemo(
    () => async (canvas: Canvas) => {
      const { data, error } = await supabase.rpc("save_canvas_by_token", { _token: token, _canvas: canvas as unknown as Json });
      if (error) throw error;
      if (!data) throw new Error("Not allowed");
    },
    [token],
  );

  if (!session || revoked) {
    return (
      <Shell>
        <h1 className="text-xl font-semibold">This link isn't valid</h1>
        <p className="mt-2 text-sm text-muted-foreground">It may have been revoked. Ask your interviewer for a new link.</p>
      </Shell>
    );
  }

  if (!joined) {
    return (
      <Shell>
        <div className="font-mono text-xs uppercase tracking-widest text-primary">You're invited</div>
        <h1 className="mt-1 text-xl font-semibold">{session.title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {session.duration_minutes} minute system design interview. Enter the name your interviewer will see.
        </p>
        <form
          className="mt-6 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const n = name.trim().slice(0, 40);
            if (!n) return;
            const id = newId();
            const peer: Peer = { id, name: n, role: "candidate", color: colorFor(id) };
            localStorage.setItem("bp-name", n);
            sessionStorage.setItem(`bp-guest-${token}`, JSON.stringify(peer));
            setJoined(peer);
          }}
        >
          <Input autoFocus required maxLength={40} placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
          <Button type="submit" className="w-full">Join interview</Button>
        </form>
      </Shell>
    );
  }

  const canEdit = status === "live" && !locked;
  const notice =
    status === "draft"
      ? "Waiting for the interviewer to start. You can read the prompt in the meantime."
      : status === "ended"
        ? "This interview has ended. Thanks for participating!"
        : locked
          ? "The interviewer has paused editing."
          : null;

  return (
    <Room
      sessionId={session.id}
      title={session.title}
      prompt={session.prompt}
      status={status}
      startedAt={session.started_at}
      durationMinutes={session.duration_minutes}
      me={joined}
      initialCanvas={session.canvas}
      canEdit={canEdit}
      lockedNotice={notice}
      save={save}
      onSession={(e) => {
        if (e.revoked) setRevoked(true);
        if (e.status) setStatus(e.status);
        if (e.locked !== undefined) setLocked(e.locked);
      }}
    />
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="blueprint-grid flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border bg-card p-8 shadow-glow">
        <Logo />
        <div className="mt-8">{children}</div>
      </div>
    </div>
  );
}
