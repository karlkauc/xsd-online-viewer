import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, sendFeedback } from "../api/client";
import { useSelection } from "../stores/selectionStore";

interface OpenDetail {
  errorDetail?: string;
  schemaName?: string;
}

type Status = { kind: "idle" } | { kind: "sending" } | { kind: "sent" } | { kind: "error"; message: string };

/**
 * Modal feedback form. Opened from anywhere via
 * `window.dispatchEvent(new CustomEvent("xsdv:open-feedback", { detail }))`
 * — the same mechanism the search palette uses.
 */
export function FeedbackDialog() {
  const [open, setOpen] = useState(false);
  const [context, setContext] = useState<OpenDetail>({});
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const model = useSelection((s) => s.model);

  useEffect(() => {
    const onOpen = (event: Event) => {
      setContext((event as CustomEvent<OpenDetail>).detail ?? {});
      setStatus({ kind: "idle" });
      setOpen(true);
    };
    window.addEventListener("xsdv:open-feedback", onOpen);
    return () => window.removeEventListener("xsdv:open-feedback", onOpen);
  }, []);

  useEffect(() => {
    if (open) textareaRef.current?.focus();
  }, [open]);

  const close = useCallback(() => setOpen(false), []);

  const submit = useCallback(async () => {
    if (!message.trim()) return;
    setStatus({ kind: "sending" });
    try {
      await sendFeedback({
        message: message.trim(),
        email: email.trim() || undefined,
        page: window.location.pathname,
        schema_name: context.schemaName ?? model?.files.find((f) => f.relationship === "main")?.filename,
        error_detail: context.errorDetail,
        website,
      });
      setStatus({ kind: "sent" });
      setMessage("");
    } catch (err) {
      setStatus({ kind: "error", message: err instanceof ApiError ? err.message : String(err) });
    }
  }, [message, email, website, context, model]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-black/30 flex items-start justify-center pt-[10vh] px-4 z-50"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") close();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-title"
        className="w-full max-w-lg bg-white dark:bg-slate-900 rounded-lg shadow-xl border border-slate-200 dark:border-slate-800 p-5"
      >
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h2 id="feedback-title" className="text-base font-semibold">
              Send feedback
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Bug, missing feature, a schema that does not load — anything helps.
            </p>
          </div>
          <button type="button" className="btn" onClick={close} aria-label="Close feedback dialog">
            ✕
          </button>
        </div>

        {status.kind === "sent" ? (
          <div className="py-4">
            <p className="text-sm text-green-700 dark:text-green-400" role="status">
              Thanks — your feedback was sent.
            </p>
            <button type="button" className="btn btn-primary mt-4" onClick={close}>
              Close
            </button>
          </div>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            {context.errorDetail && (
              <p className="mb-2 text-xs font-mono text-slate-500 dark:text-slate-400 break-words">
                Error attached: {context.errorDetail}
              </p>
            )}
            <label className="block text-sm">
              <span className="sr-only">Your message</span>
              <textarea
                ref={textareaRef}
                required
                maxLength={4000}
                rows={5}
                placeholder="What happened, or what would you like to see?"
                className="w-full p-2 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </label>
            <label className="block mt-2 text-sm">
              <span className="text-xs text-slate-500 dark:text-slate-400">Email (optional, only if you want a reply)</span>
              <input
                type="email"
                maxLength={254}
                className="mt-1 w-full px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            {/* Honeypot: hidden from people, filled by naive bots. */}
            <label className="hidden" aria-hidden="true">
              Website
              <input type="text" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
            </label>
            {status.kind === "error" && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400" role="alert">
                Could not send: {status.message}
              </p>
            )}
            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Stored without your IP address; see the README for what is kept.
              </p>
              <button type="submit" className="btn btn-primary" disabled={status.kind === "sending" || !message.trim()}>
                {status.kind === "sending" ? "Sending…" : "Send"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
