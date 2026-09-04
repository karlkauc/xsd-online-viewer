import { useCallback, useRef, useState, type ReactNode } from "react";
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
  /** Never render as an inline button; stays in the "More" menu on wide screens too. */
  menuOnly?: boolean;
}

const MENU_ITEM_CLASS =
  "flex items-center gap-2 px-3 py-2 touch:py-3 text-sm text-left whitespace-nowrap " +
  "hover:bg-slate-50 dark:hover:bg-slate-700 focus:outline-none focus-visible:bg-slate-100 dark:focus-visible:bg-slate-700";

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
        className="btn px-2.5"
        aria-label="More actions"
        aria-haspopup="menu"
        aria-expanded={open}
        title="More actions"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true" className="text-base leading-none">⋯</span>
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

/**
 * Secondary header actions. On wide viewports they render as the familiar
 * row of `.btn` controls; below that they fold into a single "More" menu so
 * the header never overflows the viewport.
 */
export function HeaderActions({ actions, inline }: { actions: HeaderAction[]; inline: boolean }) {
  if (inline) {
    const buttons = actions.filter((a) => !a.menuOnly);
    const overflow = actions.filter((a) => a.menuOnly);
    return (
      <>
        {buttons.map((action) => (
          <ActionControl key={action.key} action={action} className="btn" />
        ))}
        {overflow.length > 0 && <HeaderMenu actions={overflow} />}
      </>
    );
  }
  return <HeaderMenu actions={actions} />;
}
