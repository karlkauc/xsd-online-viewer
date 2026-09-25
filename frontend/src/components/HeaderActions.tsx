import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { countInlineActions } from "../lib/headerOverflow";
import { useDismiss } from "../lib/useDismiss";

export interface HeaderAction {
  key: string;
  label: ReactNode;
  title: string;
  /** Accessible name when the visible label is not descriptive enough. */
  ariaLabel?: string;
  href?: string;
  external?: boolean;
  onClick?: () => void;
}

const MENU_ITEM_CLASS =
  "flex items-center gap-2 px-3 py-2 touch:py-3 text-sm text-left whitespace-nowrap " +
  "hover:bg-slate-50 dark:hover:bg-slate-700 focus:outline-none focus-visible:bg-slate-100 dark:focus-visible:bg-slate-700";

const MENU_BUTTON_CLASS = "btn px-2.5";
const MENU_GLYPH = "⋯";

function ActionControl({
  action,
  className,
  role,
  onActivate,
}: {
  action: HeaderAction;
  className: string;
  role?: "menuitem";
  onActivate?: () => void;
}) {
  const common = { className, title: action.title, "aria-label": action.ariaLabel, role };
  if (action.href) {
    return (
      <a
        {...common}
        href={action.href}
        {...(action.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
        onClick={onActivate}
      >
        {action.label}
      </a>
    );
  }
  return (
    <button
      {...common}
      type="button"
      onClick={() => {
        action.onClick?.();
        onActivate?.();
      }}
    >
      {action.label}
    </button>
  );
}

function HeaderMenu({ actions }: { actions: HeaderAction[] }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(rootRef, open, close);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className={MENU_BUTTON_CLASS}
        aria-label="More actions"
        aria-haspopup="menu"
        aria-expanded={open}
        title="More actions"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true" className="text-base leading-none">{MENU_GLYPH}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1 z-40 min-w-[12rem] py-1 flex flex-col rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg"
        >
          {actions.map((action) => (
            <ActionControl
              key={action.key}
              action={action}
              role="menuitem"
              className={MENU_ITEM_CLASS}
              onActivate={close}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function px(value: string): number {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : NaN;
}

function width(el: Element): number {
  return el.getBoundingClientRect().width;
}

/**
 * The width a flex row cannot give up: `shrink-0` children keep their full
 * width, shrinkable children keep their CSS `min-width` (so a truncating
 * label reserves whatever `min-w-*` it declares, and nothing with `min-w-0`).
 */
function requiredWidth(row: Element): number {
  let total = 0;
  let visible = 0;
  for (const child of Array.from(row.children)) {
    const style = getComputedStyle(child);
    if (style.display === "none") continue;
    visible += 1;
    const min = px(style.minWidth);
    total += style.flexShrink === "0" || !Number.isFinite(min) ? width(child) : min;
  }
  const gap = px(getComputedStyle(row).columnGap) || 0;
  return total + gap * Math.max(0, visible - 1);
}

/**
 * Secondary header actions. As many as fit next to the title render as the
 * familiar row of `.btn` controls, in order; the rest fold into a single
 * "More" menu. The split is measured, not tied to a breakpoint: an invisible
 * probe renders every control once so their widths are known, and the room
 * left in the header is what the other header children do not need.
 */
export function HeaderActions({ actions }: { actions: HeaderAction[] }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const probeRef = useRef<HTMLDivElement | null>(null);
  const [inlineCount, setInlineCount] = useState(actions.length);

  const measure = useCallback(() => {
    const host = hostRef.current;
    const probe = probeRef.current;
    const group = host?.parentElement;
    const header = host?.closest("header");
    if (!host || !probe || !group || !header) {
      setInlineCount(actions.length);
      return;
    }
    const headerStyle = getComputedStyle(header);
    const headerInner = header.clientWidth - (px(headerStyle.paddingLeft) || 0) - (px(headerStyle.paddingRight) || 0);
    // No layout engine (hidden, detached, jsdom): keep what we have.
    if (headerInner <= 0) return;

    const headerGap = px(headerStyle.columnGap) || 0;
    let othersRequired = 0;
    let headerChildren = 0;
    for (const child of Array.from(header.children)) {
      if (getComputedStyle(child).display === "none") continue;
      headerChildren += 1;
      if (child !== group) othersRequired += requiredWidth(child);
    }

    const groupGap = px(getComputedStyle(group).columnGap) || 0;
    let siblings = 0;
    for (const child of Array.from(group.children)) {
      if (child === host || getComputedStyle(child).display === "none") continue;
      siblings += width(child) + groupGap;
    }

    const probeItems = Array.from(probe.children);
    const menuWidth = width(probeItems[probeItems.length - 1]);
    const widths = probeItems.slice(0, -1).map(width);
    const available = headerInner - headerGap * Math.max(0, headerChildren - 1) - othersRequired - siblings;
    setInlineCount(countInlineActions(widths, menuWidth, groupGap, available));
  }, [actions.length]);

  useLayoutEffect(() => {
    measure();
    const host = hostRef.current;
    const header = host?.closest("header");
    if (!header || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    for (const child of Array.from(header.children)) observer.observe(child);
    if (host?.parentElement) {
      for (const child of Array.from(host.parentElement.children)) {
        if (child !== host) observer.observe(child);
      }
    }
    // Web fonts arriving late change every width.
    void document.fonts?.ready.then(measure);
    return () => observer.disconnect();
    // `actions` is in the deps because a label change (e.g. "Link copied ✓")
    // resizes the probe without any observed element changing.
  }, [measure, actions]);

  const inline = actions.slice(0, inlineCount);
  const overflow = actions.slice(inlineCount);
  return (
    <div ref={hostRef} className="contents">
      {inline.map((action) => (
        <ActionControl key={action.key} action={action} className="btn" />
      ))}
      {overflow.length > 0 && <HeaderMenu actions={overflow} />}
      {/* Measuring probe: the same controls, laid out but never seen. */}
      <div
        ref={probeRef}
        aria-hidden="true"
        className="fixed top-0 left-0 invisible pointer-events-none flex items-center"
      >
        {actions.map((action) => (
          <span key={action.key} className="btn">
            {action.label}
          </span>
        ))}
        <span className={MENU_BUTTON_CLASS}>
          <span className="text-base leading-none">{MENU_GLYPH}</span>
        </span>
      </div>
    </div>
  );
}
