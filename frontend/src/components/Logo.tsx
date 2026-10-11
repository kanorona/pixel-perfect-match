export function Logo() {
  return (
    <span className="flex items-center gap-2 font-display text-base font-semibold tracking-tight">
      <span className="grid size-7 place-items-center rounded-md border border-primary/60 bg-primary/10">
        <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="var(--primary)" strokeWidth="1.6">
          <rect x="2" y="2" width="6" height="5" rx="1" />
          <rect x="12" y="13" width="6" height="5" rx="1" />
          <path d="M5 7v5h10v1" />
        </svg>
      </span>
      Blueprint
    </span>
  );
}
