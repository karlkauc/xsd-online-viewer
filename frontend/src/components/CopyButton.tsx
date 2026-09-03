import { useCopy } from "../lib/useCopy";

interface Props {
  /** Text to put on the clipboard; a function is called at click time. */
  text: string | (() => string);
  /** Accessible name, e.g. "Copy XPath". */
  label: string;
  className?: string;
}

/** Small icon button that copies `text` and briefly shows a check mark. */
export function CopyButton({ text, label, className = "" }: Props) {
  const { copied, copy } = useCopy();
  return (
    <button
      type="button"
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
      className={
        "inline-flex items-center justify-center w-6 h-6 touch:w-8 touch:h-8 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-200/70 dark:hover:text-slate-200 dark:hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
        className
      }
      onClick={() => void copy(typeof text === "function" ? text() : text)}
    >
      {copied ? (
        <span aria-hidden="true" className="text-emerald-600 dark:text-emerald-400 text-xs">✓</span>
      ) : (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  );
}
