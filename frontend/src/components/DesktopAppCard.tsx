import { FREEXMLTOOLKIT_DOWNLOAD_GO, FREEXMLTOOLKIT_GO } from "../lib/links";

const LOGO = "/freexmltoolkit.png";
const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const;

interface CardProps {
  variant?: "card";
  /** Three short benefits, tailored to the page the card sits on. */
  bullets: string[];
  className?: string;
}

interface InlineProps {
  variant: "inline";
  /** One sentence describing what the desktop app adds in this context. */
  children: React.ReactNode;
  className?: string;
}

/**
 * Cross-promotion of FreeXmlToolkit, the author's free desktop XML
 * workstation. `card` is the landing-page version with logo, bullets and a
 * download button; `inline` is a one-line tip for places where the web
 * viewer reaches its limits.
 */
export function DesktopAppCard(props: CardProps | InlineProps) {
  if (props.variant === "inline") {
    return (
      <p
        className={
          "flex items-start gap-2 text-xs text-slate-500 dark:text-slate-400 " + (props.className ?? "")
        }
      >
        <img src={LOGO} alt="" width={16} height={16} className="mt-px w-4 h-4 shrink-0 self-start" aria-hidden="true" />
        <span>
          {props.children}{" "}
          <a className="text-accent hover:underline whitespace-nowrap" href={FREEXMLTOOLKIT_GO} {...EXTERNAL}>
            FreeXmlToolkit ↗
          </a>
        </span>
      </p>
    );
  }

  return (
    <aside
      aria-labelledby="desktop-app-title"
      className={
        "rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 p-4 flex gap-4 " +
        (props.className ?? "")
      }
    >
      <img src={LOGO} alt="" width={48} height={48} className="w-12 h-12 shrink-0 self-start mt-0.5" aria-hidden="true" />
      <div className="min-w-0 text-left">
        <h3 id="desktop-app-title" className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Need more than a viewer? Try FreeXmlToolkit
        </h3>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          The free desktop XML workstation by the same author — everything the web viewers leave out.
        </p>
        <ul className="mt-2 text-sm text-slate-700 dark:text-slate-300 space-y-1">
          {props.bullets.map((text) => (
            <li key={text} className="flex gap-2">
              <span aria-hidden="true" className="text-emerald-600 dark:text-emerald-400">✓</span>
              <span>{text}</span>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <a className="btn btn-primary text-xs" href={FREEXMLTOOLKIT_DOWNLOAD_GO} {...EXTERNAL}>
            Download
          </a>
          <a className="btn text-xs" href={FREEXMLTOOLKIT_GO} {...EXTERNAL}>
            Learn more ↗
          </a>
          <span className="text-[11px] text-slate-500 dark:text-slate-400">
            Free &amp; open source (Apache 2.0) · Windows · macOS · Linux
          </span>
        </div>
      </div>
    </aside>
  );
}
