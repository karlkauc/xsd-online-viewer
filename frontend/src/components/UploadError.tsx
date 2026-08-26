import { classifyUploadError, XML_VIEWER_URL } from "../lib/uploadErrors";

interface Props {
  message: string;
  /** Present when the error was raised before upload and the user may override. */
  onUploadAnyway?: () => void;
  schemaName?: string;
}

export function openFeedback(detail: { errorDetail?: string; schemaName?: string } = {}) {
  window.dispatchEvent(new CustomEvent("xsdv:open-feedback", { detail }));
}

export function UploadError({ message, onUploadAnyway, schemaName }: Props) {
  const { kind, title } = classifyUploadError(message);

  return (
    <div
      role="alert"
      className="mt-4 rounded-lg border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/30 p-4 text-sm"
    >
      <p className="font-semibold text-red-700 dark:text-red-300">{title}</p>
      <p className="mt-1 font-mono text-xs text-red-700/80 dark:text-red-300/80 break-words">{message}</p>

      <div className="mt-3 text-slate-700 dark:text-slate-300 space-y-2">
        {kind === "xml-document" && (
          <>
            <p>
              This viewer reads XML <em>Schema</em> files (<code>.xsd</code>). To inspect or validate an
              XML <em>document</em>, use our sister tool:
            </p>
            <a
              href={XML_VIEWER_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary inline-block"
            >
              Open XML Viewer ↗
            </a>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              If you have the schema this document follows, upload that <code>.xsd</code> here instead.
            </p>
          </>
        )}
        {kind === "not-xml" && (
          <p>
            An <code>.xsd</code> file is plain text starting with <code>&lt;?xml</code> or{" "}
            <code>&lt;xs:schema</code>. Check that the file opens in a text editor — a ZIP, PDF or
            binary renamed to <code>.xsd</code> cannot be read.
          </p>
        )}
        {kind === "zip-no-xsd" && (
          <p>
            A ZIP upload must contain the main <code>.xsd</code> plus the files it imports or
            includes. If there are several schemas, name the main one in the field below.
          </p>
        )}
        {kind === "dtd" && (
          <p>
            Only a simple internal DOCTYPE with literal <code>&lt;!ENTITY&gt;</code> values is accepted.
            Remove the DOCTYPE block and write the entity values inline, then upload again.
          </p>
        )}
        {kind === "too-large" && <p>Split the schema into a ZIP of smaller files, or load it from a URL.</p>}
        {kind === "rate-limit" && <p>Please wait a minute and try again.</p>}
        {kind === "unknown" && (
          <p>Make sure the file is a well-formed XML Schema. Multi-file schemas go in a ZIP.</p>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
        {onUploadAnyway && (
          <button type="button" className="btn" onClick={onUploadAnyway}>
            Upload anyway
          </button>
        )}
        <button
          type="button"
          className="text-accent hover:underline"
          onClick={() => openFeedback({ errorDetail: message, schemaName })}
        >
          Still stuck? Send feedback
        </button>
      </div>
    </div>
  );
}
