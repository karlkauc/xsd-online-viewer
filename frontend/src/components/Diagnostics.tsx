import { useSelection } from "../stores/selectionStore";
import { SourceLineLink } from "./SourceLineLink";

// The amber bar under the header: what the parser noted while loading the
// schema, and what the backend's second reading of the schema itself found
// (GET /api/schema/{id}/check). The second list arrives a moment after the
// schema; it is advisory and never blocks anything.
export function Diagnostics() {
  const model = useSelection((s) => s.model);
  const schemaCheck = useSelection((s) => s.schemaCheck);
  const visible = useSelection((s) => s.diagnosticsVisible);
  const setVisible = useSelection((s) => s.setDiagnosticsVisible);
  const diagnostics = model?.diagnostics ?? [];
  const findings = schemaCheck?.findings ?? [];
  const more = schemaCheck?.more ?? 0;
  const count = diagnostics.length + findings.length + more;
  if (count === 0 || !visible) return null;
  return (
    <aside className="border-b border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-200 text-sm">
      <div className="flex items-start justify-between gap-2 px-4 py-1.5">
        <span className="font-medium">
          {count} diagnostic{count === 1 ? "" : "s"}
        </span>
        <button
          type="button"
          className="shrink-0 inline-flex items-center justify-center w-6 h-6 rounded hover:bg-amber-100 dark:hover:bg-amber-900/40 text-amber-900 dark:text-amber-200"
          onClick={() => setVisible(false)}
          title="Hide diagnostics"
          aria-label="Hide diagnostics"
        >
          <span aria-hidden="true" className="text-base leading-none">×</span>
        </button>
      </div>
      {diagnostics.length > 0 && (
        <ul className="px-4 pb-2 space-y-0.5 text-xs">
          {diagnostics.map((d, i) => (
            <li key={i}>
              <strong className="uppercase">{d.severity}:</strong> {d.message}
            </li>
          ))}
        </ul>
      )}
      {findings.length > 0 && (
        <div className="px-4 pb-2 text-xs" data-testid="schema-check">
          <p className="mb-0.5">
            <strong>The schema itself breaks rules of XSD {schemaCheck?.version}.</strong> It stays
            loaded, but validators differ in what they make of it.
          </p>
          <ul className="space-y-0.5 max-h-40 overflow-y-auto">
            {findings.map((d, i) => (
              <li key={i} className="flex items-baseline gap-2">
                <span className="break-words min-w-0">{d.message}</span>
                {d.file_id && (
                  <SourceLineLink
                    sourceRef={{ file_id: d.file_id, line: d.line }}
                    className="shrink-0"
                  />
                )}
              </li>
            ))}
            {more > 0 && <li>… and {more} more</li>}
          </ul>
        </div>
      )}
    </aside>
  );
}
