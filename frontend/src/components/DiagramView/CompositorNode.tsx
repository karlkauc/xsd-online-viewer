import { Handle, Position } from "@xyflow/react";

type CompositorKind = "sequence" | "choice" | "all" | "any" | "group-ref";

interface CompositorData {
  kind: CompositorKind;
  label: string;
  // XSD 1.1: when present, the owning complexType declares xs:openContent.
  // Render a dashed border + corner "+" glyph as a visual cue.
  openContentMode?: "interleave" | "suffix" | "none";
}

const BG: Record<CompositorKind, string> = {
  sequence: "bg-slate-200 dark:bg-slate-700",
  choice: "bg-amber-200 dark:bg-amber-800",
  all: "bg-emerald-200 dark:bg-emerald-800",
  any: "bg-fuchsia-200 dark:bg-fuchsia-800",
  "group-ref": "bg-pink-200 dark:bg-pink-800",
};

const TITLE: Record<CompositorKind, string> = {
  sequence: "sequence — children appear in the given order",
  choice: "choice — exactly one of the children is chosen",
  all: "all — every child appears, order does not matter",
  any: "any — wildcard element content",
  "group-ref": "group reference",
};

function CompositorIcon({ kind }: { kind: CompositorKind }) {
  // Icons are drawn in currentColor so they inherit the text color and work
  // in both light and dark themes.
  const common = {
    width: 36,
    height: 18,
    fill: "none" as const,
    stroke: "currentColor",
    strokeWidth: 1.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  switch (kind) {
    case "sequence":
      // Three boxes chained left-to-right with arrow heads — order matters.
      return (
        <svg {...common} viewBox="0 0 36 18" aria-hidden>
          <rect x="0.7" y="4" width="8" height="10" rx="1.2" />
          <path d="M8.7 9 H12.3" />
          <path d="M10.8 7.3 L12.6 9 L10.8 10.7" />
          <rect x="12.7" y="4" width="8" height="10" rx="1.2" />
          <path d="M20.7 9 H24.3" />
          <path d="M22.8 7.3 L24.6 9 L22.8 10.7" />
          <rect x="24.7" y="4" width="8" height="10" rx="1.2" />
        </svg>
      );
    case "choice":
      // One node branches to three — pick one of the alternatives.
      return (
        <svg {...common} viewBox="0 0 36 18" aria-hidden>
          <circle cx="4" cy="9" r="2.2" />
          <path d="M6.2 9 L28.5 2.8" />
          <path d="M6.2 9 L28.5 9" />
          <path d="M6.2 9 L28.5 15.2" />
          <circle cx="30.6" cy="2.8" r="2.2" />
          <circle cx="30.6" cy="9" r="2.2" />
          <circle cx="30.6" cy="15.2" r="2.2" />
        </svg>
      );
    case "all":
      // Unordered-list style: bullets with bars — all items, any order.
      return (
        <svg {...common} viewBox="0 0 36 18" aria-hidden>
          <circle cx="3" cy="3" r="1.6" fill="currentColor" stroke="none" />
          <path d="M7.5 3 H33" />
          <circle cx="3" cy="9" r="1.6" fill="currentColor" stroke="none" />
          <path d="M7.5 9 H33" />
          <circle cx="3" cy="15" r="1.6" fill="currentColor" stroke="none" />
          <path d="M7.5 15 H33" />
        </svg>
      );
    case "any":
      // Six-point asterisk — wildcard.
      return (
        <svg {...common} viewBox="0 0 36 18" aria-hidden>
          <g transform="translate(18 9)">
            <path d="M0 -7 V7" strokeWidth="1.8" />
            <path d="M-6 -3.5 L6 3.5" strokeWidth="1.8" />
            <path d="M-6 3.5 L6 -3.5" strokeWidth="1.8" />
          </g>
        </svg>
      );
    case "group-ref":
      // Two interlocking rings joined by a bar — chain link, i.e. a reference
      // to a named group.
      return (
        <svg {...common} viewBox="0 0 36 18" aria-hidden>
          <rect x="3" y="3.5" width="12" height="11" rx="5.5" ry="5.5" />
          <rect x="21" y="3.5" width="12" height="11" rx="5.5" ry="5.5" />
          <path d="M13 9 H23" />
        </svg>
      );
  }
}

export function CompositorNode({ data }: { data: CompositorData }) {
  const { kind, openContentMode } = data;
  // group-ref uses the supplied label; xs:all may be tagged "all+" to flag
  // XSD 1.1 relaxations (maxOccurs > 1 or wildcard children); other
  // compositors fall back to their kind name.
  const showLabel =
    kind === "group-ref" || (kind === "all" && data.label === "all+")
      ? data.label
      : kind;
  const openContentTitle =
    openContentMode === "none"
      ? `${TITLE[kind]} · open content disabled (mode="none")`
      : openContentMode
        ? `${TITLE[kind]} · open content (${openContentMode})`
        : TITLE[kind];
  return (
    <div
      className={`relative flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-md px-1 py-1 text-slate-900 dark:text-slate-100 ${BG[kind]} ${openContentMode && openContentMode !== "none" ? "border-2 border-dashed border-sky-500/70 dark:border-sky-300/70" : ""}`}
      style={{ width: 70, height: 40 }}
      title={openContentTitle}
    >
      <Handle type="target" position={Position.Left} />
      <CompositorIcon kind={kind} />
      <span className="truncate font-mono text-[9px] leading-none" style={{ maxWidth: 64 }}>
        {showLabel}
      </span>
      {openContentMode && openContentMode !== "none" && (
        <span
          className="absolute -top-1.5 -right-1.5 inline-flex items-center justify-center w-4 h-4 rounded-full bg-sky-500 text-white text-[9px] font-bold leading-none shadow-sm"
          aria-label={`open content: ${openContentMode}`}
        >
          +
        </span>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
