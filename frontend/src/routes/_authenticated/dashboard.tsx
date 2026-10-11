import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { queryOptions, useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Copy, LogOut, MoreHorizontal, Plus, Trash2, Files } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

const sessionsQuery = queryOptions({
  queryKey: ["sessions"],
  queryFn: async () => {
    const { data, error } = await supabase
      .from("interview_sessions")
      .select("id,title,prompt,status,duration_minutes,created_at,updated_at,candidate_token,canvas")
      .order("updated_at", { ascending: false });
    if (error) throw error;
    return data;
  },
});

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({
    meta: [
      { title: "Your interviews — Blueprint Interviews" },
      { name: "description", content: "Create, run and review system design interview sessions." },
      { property: "og:title", content: "Your interviews — Blueprint Interviews" },
      { property: "og:description", content: "Create, run and review system design interview sessions." },
    ],
  }),
  loader: ({ context }) => context.queryClient.ensureQueryData(sessionsQuery),
  component: Dashboard,
});

export function candidateLink(token: string) {
  return `${window.location.origin}/join/${token}`;
}

function Dashboard() {
  const { data } = useSuspenseQuery(sessionsQuery);
  const { user } = Route.useRouteContext();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const duplicate = useMutation({
    mutationFn: async (id: string) => {
      const s = data.find((x) => x.id === id)!;
      const { data: row, error } = await supabase
        .from("interview_sessions")
        .insert({ owner_id: user.id, title: `${s.title} (copy)`, prompt: s.prompt, duration_minutes: s.duration_minutes, canvas: s.canvas })
        .select("id")
        .single();
      if (error) throw error;
      return row.id;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      toast.success("Duplicated as a new draft");
    },
    onError: (e) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from("interview_sessions").delete().eq("id", id);
      if (error) throw error;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
    onError: (e) => toast.error(e.message),
  });

  const signOut = async () => {
    await qc.cancelQueries();
    qc.clear();
    await supabase.auth.signOut();
    navigate({ to: "/auth", replace: true });
  };

  return (
    <div className="min-h-screen">
      <header className="border-b bg-card">
        <div className="mx-auto flex h-14 max-w-6xl items-center px-6">
          <Link to="/"><Logo /></Link>
          <div className="ml-auto flex items-center gap-3 text-sm text-muted-foreground">
            {user.email}
            <Button variant="ghost" size="sm" onClick={signOut}><LogOut className="size-4" /> Sign out</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="flex items-end justify-between">
          <div>
            <div className="font-mono text-xs uppercase tracking-widest text-primary">Dashboard</div>
            <h1 className="mt-1 text-3xl font-semibold">Interviews</h1>
          </div>
          <NewSessionDialog userId={user.id} onCreated={(id) => navigate({ to: "/sessions/$id", params: { id } })} />
        </div>

        {data.length === 0 ? (
          <div className="blueprint-grid mt-10 rounded-2xl border border-dashed p-16 text-center">
            <h2 className="text-lg font-semibold">No interviews yet</h2>
            <p className="mt-1 text-sm text-muted-foreground">Create your first session and share the link with a candidate.</p>
          </div>
        ) : (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.map((s) => {
              const count = ((s.canvas as { elements?: unknown[] })?.elements ?? []).length;
              return (
                <div key={s.id} className="group relative rounded-xl border bg-card p-5 transition-shadow hover:shadow-glow">
                  <div className="flex items-start justify-between gap-2">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider",
                        s.status === "live" && "bg-success/15 text-success",
                        s.status === "draft" && "bg-muted text-muted-foreground",
                        s.status === "ended" && "bg-destructive/15 text-destructive",
                      )}
                    >
                      {s.status === "draft" ? "not started" : s.status}
                    </span>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="size-7"><MoreHorizontal className="size-4" /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => { navigator.clipboard.writeText(candidateLink(s.candidate_token)); toast.success("Candidate link copied"); }}>
                          <Copy className="size-4" /> Copy candidate link
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => duplicate.mutate(s.id)}><Files className="size-4" /> Duplicate as template</DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive" onClick={() => confirm("Delete this interview permanently?") && remove.mutate(s.id)}>
                          <Trash2 className="size-4" /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  <Link to="/sessions/$id" params={{ id: s.id }} className="mt-3 block after:absolute after:inset-0 after:content-['']">
                    <h3 className="font-semibold">{s.title}</h3>
                  </Link>
                  <p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted-foreground">{s.prompt || "No prompt"}</p>
                  <div className="mt-4 flex justify-between font-mono text-[11px] text-muted-foreground">
                    <span>{s.duration_minutes} min · {count} elements</span>
                    <span>{new Date(s.updated_at).toLocaleDateString()}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}

function NewSessionDialog({ userId, onCreated }: { userId: string; onCreated: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(60);
  const [busy, setBusy] = useState(false);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const { data, error } = await supabase
      .from("interview_sessions")
      .insert({ owner_id: userId, title: title.trim() || "Untitled interview", prompt, duration_minutes: duration })
      .select("id")
      .single();
    setBusy(false);
    if (error) { toast.error(error.message); return; }
    setOpen(false);
    onCreated(data.id);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><Plus className="size-4" /> New interview</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>New interview</DialogTitle></DialogHeader>
        <form onSubmit={create} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="t">Title</Label>
            <Input id="t" value={title} maxLength={120} placeholder="Design a URL shortener" onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p">Prompt for the candidate</Label>
            <Textarea id="p" rows={6} value={prompt} maxLength={5000} placeholder="Requirements, scale, constraints…" onChange={(e) => setPrompt(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="d">Duration (minutes)</Label>
            <Input id="d" type="number" min={10} max={240} value={duration} onChange={(e) => setDuration(Number(e.target.value) || 60)} />
          </div>
          <Button type="submit" className="w-full" disabled={busy}>Create</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
