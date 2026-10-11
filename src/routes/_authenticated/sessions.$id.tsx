import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, Copy, Lock, LockOpen, Play, RotateCcw, Square, RefreshCw } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { Room } from "@/components/board/Room";
import { colorFor, type Canvas, type Peer } from "@/components/board/types";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { Json } from "@/integrations/supabase/types";

export const Route = createFileRoute("/_authenticated/sessions/$id")({
  head: () => ({
    meta: [
      { title: "Interview room — Blueprint Interviews" },
      { name: "description", content: "Live collaborative system design canvas." },
      { property: "og:title", content: "Interview room — Blueprint Interviews" },
      { property: "og:description", content: "Live collaborative system design canvas." },
    ],
  }),
  loader: async ({ params }) => {
    const { data, error } = await supabase.from("interview_sessions").select("*").eq("id", params.id).single();
    if (error) throw error;
    return data;
  },
  component: InterviewerRoom,
});

function randomToken() {
  const b = new Uint8Array(18);
  crypto.getRandomValues(b);
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

function InterviewerRoom() {
  const initial = Route.useLoaderData();
  const { user } = Route.useRouteContext();
  const [s, setS] = useState(initial);
  const me: Peer = useMemo(
    () => ({ id: user.id, name: (user.email ?? "Interviewer").split("@")[0], role: "interviewer", color: colorFor(user.id) }),
    [user.id, user.email],
  );

  const update = async (patch: Partial<typeof s>) => {
    const { data, error } = await supabase.from("interview_sessions").update(patch).eq("id", s.id).select("*").single();
    if (error) {
      toast.error(error.message);
      return null;
    }
    setS(data);
    return data;
  };

  const save = async (canvas: Canvas) => {
    const { error } = await supabase.from("interview_sessions").update({ canvas: canvas as unknown as Json }).eq("id", s.id);
    if (error) throw error;
  };

  const link = typeof window !== "undefined" ? `${window.location.origin}/join/${s.candidate_token}` : "";

  return (
    <Room
      sessionId={s.id}
      title={s.title}
      prompt={s.prompt}
      status={s.status}
      startedAt={s.started_at}
      durationMinutes={s.duration_minutes}
      me={me}
      initialCanvas={initial.canvas}
      canEdit={s.status !== "ended"}
      lockedNotice={s.status === "ended" ? "This interview has ended. The canvas is read-only — reopen to edit." : null}
      save={save}
      onSession={(e) => setS((prev) => ({ ...prev, ...(e.status ? { status: e.status } : {}), ...(e.locked !== undefined ? { candidate_editing_locked: e.locked } : {}) }))}
      back={
        <Button asChild variant="ghost" size="icon" aria-label="Back to dashboard">
          <Link to="/dashboard"><ArrowLeft className="size-4" /></Link>
        </Button>
      }
      controls={({ broadcastSession }) => (
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" size="sm"><Copy className="size-4" /> Invite</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <div className="break-all px-2 py-1.5 font-mono text-[11px] text-muted-foreground">{link}</div>
              <DropdownMenuItem onClick={() => { navigator.clipboard.writeText(link); toast.success("Candidate link copied"); }}>
                <Copy className="size-4" /> Copy candidate link
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive"
                onClick={async () => {
                  if (!confirm("Revoke the current link? Anyone using it will be removed.")) return;
                  if (await update({ candidate_token: randomToken() })) {
                    broadcastSession({ revoked: true });
                    toast.success("Old link revoked. Copy the new one to invite.");
                  }
                }}
              >
                <RefreshCw className="size-4" /> Revoke & regenerate link
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {s.status !== "ended" && (
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                const locked = !s.candidate_editing_locked;
                if (await update({ candidate_editing_locked: locked })) broadcastSession({ locked });
              }}
            >
              {s.candidate_editing_locked ? <><Lock className="size-4" /> Candidate locked</> : <><LockOpen className="size-4" /> Candidate can edit</>}
            </Button>
          )}
          {s.status === "draft" && (
            <Button size="sm" onClick={async () => { if (await update({ status: "live", started_at: new Date().toISOString() })) broadcastSession({ status: "live" }); }}>
              <Play className="size-4" /> Start
            </Button>
          )}
          {s.status === "live" && (
            <Button variant="destructive" size="sm" onClick={async () => { if (confirm("End this interview? Everyone's canvas becomes read-only.") && (await update({ status: "ended", ended_at: new Date().toISOString() }))) broadcastSession({ status: "ended" }); }}>
              <Square className="size-4" /> End
            </Button>
          )}
          {s.status === "ended" && (
            <Button variant="secondary" size="sm" onClick={async () => { if (await update({ status: "live", ended_at: null })) broadcastSession({ status: "live" }); }}>
              <RotateCcw className="size-4" /> Reopen
            </Button>
          )}
        </div>
      )}
    />
  );
}
