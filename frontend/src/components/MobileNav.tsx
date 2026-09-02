export type MobilePane = "structure" | "view" | "details";

const PANES: { pane: MobilePane; label: string; icon: string }[] = [
  { pane: "structure", label: "Structure", icon: "🌳" },
  { pane: "view", label: "View", icon: "👁" },
  { pane: "details", label: "Details", icon: "📋" },
];

export function MobileNav({
  pane,
  onChange,
}: {
  pane: MobilePane;
  onChange: (pane: MobilePane) => void;
}) {
  return (
    <nav
      aria-label="Panes"
      className="md:hidden shrink-0 flex border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 pb-[env(safe-area-inset-bottom)]"
    >
      {PANES.map((p) => (
        <button
          key={p.pane}
          type="button"
          aria-pressed={pane === p.pane}
          onClick={() => onChange(p.pane)}
          className={
            "flex-1 flex flex-col items-center gap-0.5 py-2 touch:py-2.5 text-xs font-medium " +
            (pane === p.pane
              ? "text-accent"
              : "text-slate-500 dark:text-slate-400")
          }
        >
          <span aria-hidden="true" className="text-base leading-none">
            {p.icon}
          </span>
          {p.label}
        </button>
      ))}
    </nav>
  );
}
