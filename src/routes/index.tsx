import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Link2, MousePointer2, Save, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Logo";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Blueprint — Live system design interviews" },
      { name: "description", content: "A real-time shared canvas for running system design interviews. Share a link, draw together, review later." },
      { property: "og:title", content: "Blueprint — Live system design interviews" },
      { property: "og:description", content: "A real-time shared canvas for running system design interviews." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  return (
    <div className="blueprint-grid min-h-screen">
      <header className="mx-auto flex h-16 max-w-6xl items-center px-6">
        <Logo />
        <Button asChild variant="ghost" className="ml-auto"><Link to="/dashboard">Sign in</Link></Button>
      </header>
      <main className="mx-auto max-w-6xl px-6 pb-24 pt-16">
        <div className="max-w-2xl">
          <div className="font-mono text-xs uppercase tracking-[0.25em] text-primary">System design interviews</div>
          <h1 className="mt-4 text-5xl font-semibold leading-[1.05] md:text-6xl">
            Whiteboard the architecture,<br /><span className="text-primary">together, live.</span>
          </h1>
          <p className="mt-6 text-lg text-muted-foreground">
            Create a session, send one link, and design with your candidate on an infinite shared canvas. Everything saves for review.
          </p>
          <div className="mt-8 flex gap-3">
            <Button asChild size="lg"><Link to="/dashboard">Start an interview <ArrowRight className="size-4" /></Link></Button>
          </div>
        </div>

        <DiagramPreview />

        <div className="mt-16 grid gap-4 md:grid-cols-4">
          {[
            { icon: Link2, t: "One secure link", d: "Candidates join as guests with just a name. Revoke anytime." },
            { icon: MousePointer2, t: "Real-time canvas", d: "Components, arrows, notes and freehand — live cursors included." },
            { icon: Users, t: "You stay in control", d: "Start, end, reopen, and lock candidate editing." },
            { icon: Save, t: "Autosaved", d: "The final canvas is kept for every session." },
          ].map((f) => (
            <div key={f.t} className="rounded-xl border bg-card/80 p-5 backdrop-blur">
              <f.icon className="size-5 text-primary" />
              <div className="mt-3 font-display font-semibold">{f.t}</div>
              <p className="mt-1 text-sm text-muted-foreground">{f.d}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}

function DiagramPreview() {
  const boxes = [
    { x: 20, y: 90, l: "Client", c: "var(--chart-1)" },
    { x: 220, y: 90, l: "Load Balancer", c: "var(--chart-5)" },
    { x: 440, y: 30, l: "API Service", c: "var(--chart-2)" },
    { x: 440, y: 150, l: "API Service", c: "var(--chart-2)" },
    { x: 660, y: 30, l: "Cache", c: "var(--chart-3)" },
    { x: 660, y: 150, l: "Database", c: "var(--chart-4)" },
  ];
  const lines: [number, number][] = [[0, 1], [1, 2], [1, 3], [2, 4], [3, 5], [2, 5]];
  return (
    <div className="mt-16 overflow-hidden rounded-2xl border bg-canvas p-6 shadow-glow">
      <svg viewBox="0 0 820 230" className="w-full">
        <defs>
          <marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--edge)" />
          </marker>
        </defs>
        {lines.map(([a, b], i) => (
          <line key={i} x1={boxes[a]!.x + 140} y1={boxes[a]!.y + 25} x2={boxes[b]!.x} y2={boxes[b]!.y + 25} stroke="var(--edge)" strokeWidth="1.5" markerEnd="url(#a)" opacity="0.8" />
        ))}
        {boxes.map((b, i) => (
          <g key={i}>
            <rect x={b.x} y={b.y} width="140" height="50" rx="9" fill="var(--node)" stroke={b.c} strokeWidth="1.5" />
            <rect x={b.x} y={b.y} width="4" height="50" rx="2" fill={b.c} />
            <text x={b.x + 18} y={b.y + 30} fill="var(--ink)" fontSize="14" className="font-sans">{b.l}</text>
          </g>
        ))}
        <g transform="translate(560 120)">
          <path d="M0,0 L0,16 L4.5,12 L8,19 L10.5,18 L7,11 L13,11 z" fill="var(--chart-3)" />
          <rect x="12" y="16" width="64" height="18" rx="3" fill="var(--chart-3)" />
          <text x="18" y="29" fontSize="11" fill="var(--primary-foreground)">Candidate</text>
        </g>
      </svg>
    </div>
  );
}
