import { useCallback, useRef, useState } from "react";
import { useDismiss } from "../../lib/useDismiss";

export type ExportFormat = "svg" | "png";

interface DiagramToolbarProps {
  /** Icon-only layout with export folded into a menu (phones). */
  compact: boolean;
  minimapVisible: boolean;
  canExpand: boolean;
  canCollapse: boolean;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  onToggleMinimap: () => void;
  onExport: (format: ExportFormat) => void;
}

const ICON_BTN = "btn px-2.5 min-w-[2.5rem] justify-center";

function ExportMenu({ onExport }: { onExport: (format: ExportFormat) => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(rootRef, open, close);
  const pick = (format: ExportFormat) => {
    close();
    onExport(format);
  };
  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className={ICON_BTN}
        aria-label="Export"
        title="Export diagram as image"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">⬇</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1 z-20 min-w-[9rem] py-1 flex flex-col rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg"
        >
          <button type="button" role="menuitem" className="px-3 py-2 touch:py-3 text-sm text-left hover:bg-slate-50 dark:hover:bg-slate-700" onClick={() => pick("svg")}>
            Export SVG
          </button>
          <button type="button" role="menuitem" className="px-3 py-2 touch:py-3 text-sm text-left hover:bg-slate-50 dark:hover:bg-slate-700" onClick={() => pick("png")}>
            Export PNG
          </button>
        </div>
      )}
    </div>
  );
}

export function DiagramToolbar({
  compact,
  minimapVisible,
  canExpand,
  canCollapse,
  onExpandAll,
  onCollapseAll,
  onToggleMinimap,
  onExport,
}: DiagramToolbarProps) {
  const minimapLabel = minimapVisible ? "Hide minimap" : "Show minimap";

  if (compact) {
    return (
      <div className="absolute top-2 right-2 z-10 flex gap-1">
        <button type="button" className={ICON_BTN} onClick={onExpandAll} disabled={!canExpand} aria-label="Expand all" title="Expand every element that has child content">
          <span aria-hidden="true">⤢</span>
        </button>
        <button type="button" className={ICON_BTN} onClick={onCollapseAll} disabled={!canCollapse} aria-label="Collapse all" title="Collapse every expanded element">
          <span aria-hidden="true">⤡</span>
        </button>
        <button type="button" className={ICON_BTN} onClick={onToggleMinimap} aria-label={minimapLabel} title={minimapLabel} aria-pressed={minimapVisible}>
          <span aria-hidden="true">🗺️</span>
        </button>
        <ExportMenu onExport={onExport} />
      </div>
    );
  }

  return (
    <div className="absolute top-2 right-2 z-10 flex flex-wrap justify-end gap-1">
      <button type="button" className="btn" onClick={onExpandAll} disabled={!canExpand} title="Expand every element that has child content">
        Expand all
      </button>
      <button type="button" className="btn" onClick={onCollapseAll} disabled={!canCollapse} title="Collapse every expanded element">
        Collapse all
      </button>
      <button type="button" className="btn" onClick={onToggleMinimap} title={minimapLabel} aria-pressed={minimapVisible}>
        🗺️ {minimapLabel}
      </button>
      <button type="button" className="btn" onClick={() => onExport("svg")}>
        Export SVG
      </button>
      <button type="button" className="btn" onClick={() => onExport("png")}>
        Export PNG
      </button>
    </div>
  );
}
