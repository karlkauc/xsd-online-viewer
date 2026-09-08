import { useState } from "react";
import type { AttributeDecl, ElementDecl, IdRole, NodeIndexEntry } from "../types/schema";
import { computeXPath } from "../lib/xpath";
import { KindBadge } from "./TreeView/KindBadge";
import { SourceLineLink } from "./SourceLineLink";
import { TapToReveal } from "./TapToReveal";
import { UsageRow } from "./UsageRow";

type SetSelected = (id: string) => void;

const ID_ROLE_LABEL: Record<IdRole, string> = {
  id: "ID",
  idref: "IDREF",
  idrefs: "IDREFS",
};

const ID_ROLE_TITLE: Record<IdRole, string> = {
  id: "xs:ID",
  idref: "xs:IDREF",
  idrefs: "xs:IDREFS",
};

// Indigo ID/IDREF/IDREFS chip — the ID/IDREF equivalent of the identity
// constraints' teal KindChip. Shared by DetailPanel's "ID role" DataRow and
// the IDREFS marker in ReferencedByIdrefSection below.
export function IdRoleChip({ role }: { role: IdRole }) {
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10.5px] font-medium border bg-indigo-50 text-indigo-800 border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-200 dark:border-indigo-800/60"
      title={ID_ROLE_TITLE[role]}
    >
      {ID_ROLE_LABEL[role]}
    </span>
  );
}

const CANDIDATE_CAP = 8;

function candidatePath(
  entry: NodeIndexEntry,
  indexById: Map<string, NodeIndexEntry>,
  parentById: Map<string, string>,
): string {
  const segments = computeXPath(entry.id, indexById, parentById);
  if (segments && segments.length) {
    return "/" + segments.map((s) => s.label).join("/");
  }
  return entry.qname ?? entry.label;
}

interface IdReferenceSectionProps {
  /** Every xs:ID-typed element/attribute in the schema — XSD binds an IDREF
   *  to *any* of them, not a specific declaration, so all are candidates. */
  idDeclarations: NodeIndexEntry[];
  indexById: Map<string, NodeIndexEntry>;
  parentById: Map<string, string>;
  setSelected: SetSelected;
}

// The IDREF/IDREFS side of the ID/IDREF UI: since XSD never binds an IDREF
// to one specific ID, this lists every xs:ID candidate declared anywhere in
// the schema instead of trying (and failing) to resolve a single target.
export function IdReferenceSection({
  idDeclarations,
  indexById,
  parentById,
  setSelected,
}: IdReferenceSectionProps) {
  const [showAll, setShowAll] = useState(false);
  const total = idDeclarations.length;
  const visible = showAll ? idDeclarations : idDeclarations.slice(0, CANDIDATE_CAP);
  return (
    <section className="mt-3">
      <h3 className="font-semibold mb-1.5 flex items-baseline gap-2">
        <span>ID reference</span>
        <span className="text-[10.5px] font-normal uppercase tracking-wider text-slate-400">
          {total} xs:ID candidate{total === 1 ? "" : "s"}
        </span>
      </h3>
      <p className="text-[11.5px] text-slate-500 dark:text-slate-400 leading-relaxed mb-2.5">
        XML Schema does not bind an IDREF to a specific ID: any element or
        attribute typed xs:ID in the document is a valid target. Declarations
        typed xs:ID in this schema:
      </p>
      {total === 0 ? (
        <p className="text-[11.5px] text-slate-500 dark:text-slate-400 italic">
          No xs:ID declarations in this schema.
        </p>
      ) : (
        <>
          <div className="space-y-2">
            {visible.map((entry) => (
              <IdCandidateCard
                key={entry.id}
                entry={entry}
                indexById={indexById}
                parentById={parentById}
                setSelected={setSelected}
              />
            ))}
          </div>
          {!showAll && total > CANDIDATE_CAP && (
            <button
              type="button"
              className="mt-2 text-[11.5px] font-medium text-indigo-700 dark:text-indigo-300 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
              onClick={() => setShowAll(true)}
            >
              Show all ({total})
            </button>
          )}
        </>
      )}
    </section>
  );
}

function IdCandidateCard({
  entry,
  indexById,
  parentById,
  setSelected,
}: {
  entry: NodeIndexEntry;
  indexById: Map<string, NodeIndexEntry>;
  parentById: Map<string, string>;
  setSelected: SetSelected;
}) {
  const node = entry.node as ElementDecl | AttributeDecl;
  const docs = node.annotation?.documentation ?? [];
  const docFull = docs[0]?.text ?? null;
  const docFirst = docFull ? docFull.split(/\r?\n/)[0] : "";
  const path = candidatePath(entry, indexById, parentById);
  return (
    <div className="rounded border border-slate-200 dark:border-slate-700 border-l-2 border-l-indigo-500 bg-slate-50 dark:bg-slate-900/60 px-3 py-2 space-y-1">
      <div className="flex items-center gap-2 flex-wrap">
        <KindBadge kind={entry.kind} />
        <button
          type="button"
          className="font-mono text-[12px] text-indigo-700 dark:text-indigo-300 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
          onClick={() => setSelected(entry.id)}
        >
          {entry.label}
        </button>
        {entry.source_ref && <SourceLineLink sourceRef={entry.source_ref} className="ml-auto" />}
      </div>
      <div className="font-mono text-[11.5px] text-slate-600 dark:text-slate-300 break-all">
        {path}
      </div>
      {docFull && (
        <div className="text-[11.5px] text-slate-600 dark:text-slate-300 italic leading-snug">
          <TapToReveal summary={docFirst} details={docFull} />
        </div>
      )}
    </div>
  );
}

interface ReferencedByIdrefSectionProps {
  /** Every IDREF/IDREFS-typed element/attribute in the schema — since XSD
   *  never pins an IDREF to one ID, all of them are potential referrers of
   *  the currently selected xs:ID declaration. */
  idrefDeclarations: NodeIndexEntry[];
  setSelected: SetSelected;
}

// The xs:ID side of the ID/IDREF UI: a flat usage list of every IDREF/IDREFS
// declaration in the schema, since none of them resolve to this ID
// specifically (see IdReferenceSection above).
export function ReferencedByIdrefSection({
  idrefDeclarations,
  setSelected,
}: ReferencedByIdrefSectionProps) {
  const total = idrefDeclarations.length;
  return (
    <section className="mt-3">
      <h3 className="font-semibold mb-2.5 flex items-baseline gap-2">
        <span>Referenced by IDREF</span>
        <span className="text-[10.5px] font-normal uppercase tracking-wider text-slate-400">
          {total} xs:IDREF/IDREFS declaration{total === 1 ? "" : "s"}
        </span>
      </h3>
      {total === 0 ? (
        <p className="text-[11.5px] text-slate-500 dark:text-slate-400 italic">
          No xs:IDREF/IDREFS declarations in this schema.
        </p>
      ) : (
        <ul className="space-y-0.5">
          {idrefDeclarations.map((entry) => {
            const role = (entry.node as ElementDecl | AttributeDecl).id_role;
            return (
              <li key={entry.id} className="flex items-center gap-1.5">
                <div className="flex-1 min-w-0">
                  <UsageRow entry={entry} onClick={() => setSelected(entry.id)} />
                </div>
                {role === "idrefs" && <IdRoleChip role="idrefs" />}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
