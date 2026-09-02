import { useState, type MouseEvent } from "react";

interface TapToRevealProps {
  /** Short text shown at first (typically the first documentation line). */
  summary: string;
  /** Full text; when it adds nothing beyond `summary` a plain span is rendered. */
  details?: string | null;
  /** `inline` grows in place (tables); `popover` floats below (diagram nodes). */
  mode?: "inline" | "popover";
  className?: string;
}

/**
 * Hover tooltips (`title=`) are unreachable on touch screens. This renders
 * the summary as a button that reveals the full text on tap, keeping `title`
 * for mouse users. The click never bubbles, so it can sit inside clickable
 * table rows and React Flow nodes without selecting them.
 */
export function TapToReveal({ summary, details, mode = "inline", className = "" }: TapToRevealProps) {
  const [open, setOpen] = useState(false);
  const full = details?.trim() ?? "";
  const hasMore = full.length > 0 && full !== summary.trim();

  if (!hasMore) {
    return <span className={className}>{summary}</span>;
  }

  const toggle = (event: MouseEvent) => {
    event.stopPropagation();
    setOpen((v) => !v);
  };

  return (
    <span className={"relative " + (mode === "popover" ? "block " : "") + className}>
      <button
        type="button"
        className={
          "nodrag text-left underline decoration-dotted underline-offset-2 cursor-pointer hover:text-slate-800 dark:hover:text-slate-200 " +
          (mode === "popover" ? "block max-w-full truncate" : "")
        }
        onClick={toggle}
        aria-expanded={open}
        title={open ? undefined : full}
      >
        <span aria-hidden="true" className="mr-1 not-italic">{open ? "▾" : "▸"}</span>
        {summary}
      </button>
      {open && (
        <span
          className={
            "nodrag block whitespace-pre-line text-left not-italic " +
            (mode === "popover"
              ? "absolute left-0 top-full mt-1 z-20 w-64 max-w-[80vw] p-2 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg text-slate-700 dark:text-slate-300"
              : "mt-1 text-slate-600 dark:text-slate-400")
          }
          onClick={(event) => event.stopPropagation()}
        >
          {full}
        </span>
      )}
    </span>
  );
}
