import {
  Monitor,
  Split,
  DoorOpen,
  Server,
  Database,
  Zap,
  Layers,
  HardDrive,
  Globe,
  Signpost,
  Cog,
  Search,
  type LucideIcon,
} from "lucide-react";

export type PaletteItem = { id: string; label: string; icon: LucideIcon; tone: string };

export const PALETTE: PaletteItem[] = [
  { id: "client", label: "Client", icon: Monitor, tone: "var(--chart-1)" },
  { id: "dns", label: "DNS", icon: Signpost, tone: "var(--chart-1)" },
  { id: "cdn", label: "CDN", icon: Globe, tone: "var(--chart-1)" },
  { id: "lb", label: "Load Balancer", icon: Split, tone: "var(--chart-5)" },
  { id: "gateway", label: "API Gateway", icon: DoorOpen, tone: "var(--chart-5)" },
  { id: "service", label: "Service", icon: Server, tone: "var(--chart-2)" },
  { id: "worker", label: "Worker", icon: Cog, tone: "var(--chart-2)" },
  { id: "queue", label: "Queue", icon: Layers, tone: "var(--chart-3)" },
  { id: "cache", label: "Cache", icon: Zap, tone: "var(--chart-3)" },
  { id: "db", label: "Database", icon: Database, tone: "var(--chart-4)" },
  { id: "storage", label: "Object Storage", icon: HardDrive, tone: "var(--chart-4)" },
  { id: "search", label: "Search Index", icon: Search, tone: "var(--chart-4)" },
];

export const PALETTE_BY_ID = Object.fromEntries(PALETTE.map((p) => [p.id, p]));
