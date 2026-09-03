import { useState } from "react";
import { classifyUploadError, XML_VIEWER_URL } from "../lib/uploadErrors";
import { openInXmlViewer } from "../lib/xmlViewerHandoff";

interface Props {
  message: string;
  /** Present when the error was raised before upload and the user may override. */
  onUploadAnyway?: () => void;
  schemaName?: string;
  /** The uploaded file, so an XML document can be handed to the XML viewer. */
  file?: File;
}

export function openFeedback(detail: { errorDetail?: string; schemaName?: string } = {}) {
  window.dispatchEvent(new CustomEvent("xsdv:open-feedback", { detail }));
}

export function UploadError({ message, onUploadAnyway, schemaName, file }: Props) {
  const { kind, title } = classifyUploadError(message);
  const [handoff, setHandoff] = useState<"idle" | "sending" | "sent" | "failed">("idle");

  const sendToXmlViewer = () => {
    if (!file) return;
    setHandoff("sending");
    void openInXmlViewer(file).then((ok) => setHandoff(ok ? "sent" : "failed"));
  };

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
            {file ? (
              <>
                <button
                  type="button"
                  className="btn btn-primary inline-block"
                  disabled={handoff === "sending"}
                  onClick={sendToXmlViewer}
                >
                  Open in XML Viewer ↗
                </button>
                {handoff === "sending" && (
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Opening XML Viewer and sending <code>{file.name}</code>…
                  </p>
                )}
                {handoff === "sent" && (
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    <code>{file.name}</code> was sent to the XML Viewer tab.
                  </p>
                )}
                {handoff === "failed" && (
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Could not send the file automatically (popup blocked?). Open{" "}
                    <a href={XML_VIEWER_URL} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                      the XML Viewer
                    </a>{" "}
                    and upload <code>{file.name}</code> there.
                  </p>
                )}
              </>
            ) : (
              <a
                href={XML_VIEWER_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-primary inline-block"
              >
                Open XML Viewer ↗
              </a>
            )}
            <p className="text-xs text-slate-500 dark:text-slate-400">
              If you have the schema this document follows, upload that <code>.xsd</code> here instead.
            </p>
          </>
        )}
        {kind === "schema-namespace" && (
          <>
            <p>
              The root element is a <code>schema</code>, so this is meant to be an XML Schema — but
              it is not in the XML Schema namespace. The prefix is irrelevant:{" "}
              <code>&lt;schema&gt;</code>, <code>&lt;xs:schema&gt;</code> and{" "}
              <code>&lt;xsd:schema&gt;</code> all work, as long as that prefix (or the default
              namespace) is bound to <code>http://www.w3.org/2001/XMLSchema</code>.
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Fix the root element, for example{" "}
              <code>&lt;schema xmlns="http://www.w3.org/2001/XMLSchema"&gt;</code>, and upload again.
              Schemas written against the 1999 or 2000 drafts need the same namespace change.
            </p>
          </>
        )}
        {kind === "binary-file" && (
          <>
            <p>
              An <code>.xsd</code> schema is plain text starting with <code>&lt;?xml</code> or{" "}
              <code>&lt;xs:schema</code>. This file contains binary data, so it is not a schema —
              opening it in a text editor will show unreadable characters.
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Note: <code>.xsd</code> is also the file extension of cross-stitch patterns from
              Pattern Maker (HobbyWare). Those patterns have nothing to do with XML Schema and can
              only be opened in that program — this viewer cannot display them.
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
        {kind === "html-page" && (
          <p>
            That address serves an HTML page around the file. Paste the direct link to the file's
            raw content instead — on GitHub, GitLab and Bitbucket that is the <strong>Raw</strong>{" "}
            button. Links to <code>github.com/…/blob/…</code> are rewritten automatically, so the page
            you pasted probably has no raw counterpart at that path.
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
