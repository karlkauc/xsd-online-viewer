import { create } from "zustand";
import type {
  IdentityConstraint,
  NodeIndexEntry,
  OverrideDirective,
  OverrideReplacement,
  SchemaModel,
  SchemaNode,
  SchemaNodeKind,
  SourceRef,
  ValidationResponse,
} from "../types/schema";
import { buildIndex } from "../lib/indexSchema";
import { collectRevealIds } from "../lib/revealPath";
import type { SchemaSource } from "../lib/schemaSource";
import { MD_QUERY, matchesMediaQuery } from "../lib/useMediaQuery";

export type ViewTab = "tree" | "diagram" | "text" | "validation";

interface SelectionState {
  schemaId: string | null;
  model: SchemaModel | null;
  /** How the schema was loaded; drives share links and cache-expiry recovery. */
  source: SchemaSource | null;
  index: NodeIndexEntry[];
  indexById: Map<string, NodeIndexEntry>;
  usagesByTarget: Map<string, NodeIndexEntry[]>;
  parentById: Map<string, string>;
  overrideByReplacementId: Map<
    string,
    { directive: OverrideDirective; replacement: OverrideReplacement }
  >;
  overridesByOriginalKey: Map<string, OverrideReplacement[]>;
  constraintsById: Map<string, { constraint: IdentityConstraint; hostId: string }>;
  idDeclarations: NodeIndexEntry[];
  idrefDeclarations: NodeIndexEntry[];

  activeTab: ViewTab;
  selectedId: string | null;
  expandedIds: Set<string>;
  filterKinds: Set<SchemaNodeKind>;
  searchQuery: string;
  validationResult: ValidationResponse | null;
  diagnosticsVisible: boolean;
  minimapVisible: boolean;
  /** Set by jumpToSource — an arbitrary source location (e.g. a
   *  constraint's selector step, or an ID/IDREF candidate) to scroll the
   *  Text tab to, taking priority over the current selection's source_ref. */
  sourceJump: SourceRef | null;

  setSchema: (schemaId: string, model: SchemaModel, source?: SchemaSource | null) => void;
  /** Rebind to a renewed server-side id without touching the view state. */
  setSchemaId: (schemaId: string) => void;
  clearSchema: () => void;
  setActiveTab: (tab: ViewTab) => void;
  setSelected: (id: string | null) => void;
  /** Select `id` and expand every ancestor needed to make it visible in the
   *  tree and the diagram (see lib/revealPath.ts). Used by navigation links
   *  such as the XPath breadcrumb and constraint selector steps. */
  selectAndReveal: (id: string) => void;
  /** Switch to the Text tab and scroll/highlight an arbitrary source line,
   *  independent of the current selection. */
  jumpToSource: (ref: SourceRef) => void;
  toggleExpanded: (id: string) => void;
  setExpanded: (id: string, expanded: boolean) => void;
  setExpandedIds: (ids: Set<string>) => void;
  setFilterKinds: (kinds: Set<SchemaNodeKind>) => void;
  setSearchQuery: (query: string) => void;
  setValidationResult: (result: ValidationResponse | null) => void;
  setDiagnosticsVisible: (visible: boolean) => void;
  setMinimapVisible: (visible: boolean) => void;
}

/** Minimap is on by default on tablets/desktops and off on phones, where it
 *  would cover a quarter of the canvas. Environments without matchMedia (SSR,
 *  jsdom without the stub) count as wide. */
export function defaultMinimapVisible(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return matchesMediaQuery(MD_QUERY);
}

const ALL_KINDS: SchemaNodeKind[] = [
  "element",
  "attribute",
  "complexType",
  "simpleType",
  "group",
  "attributeGroup",
];

export const useSelection = create<SelectionState>((set, get) => ({
  schemaId: null,
  model: null,
  source: null,
  index: [],
  indexById: new Map(),
  usagesByTarget: new Map(),
  parentById: new Map(),
  overrideByReplacementId: new Map(),
  overridesByOriginalKey: new Map(),
  constraintsById: new Map(),
  idDeclarations: [],
  idrefDeclarations: [],

  activeTab: "diagram",
  selectedId: null,
  expandedIds: new Set(),
  filterKinds: new Set(ALL_KINDS),
  searchQuery: "",
  validationResult: null,
  diagnosticsVisible: true,
  minimapVisible: defaultMinimapVisible(),
  sourceJump: null,

  setSchema: (schemaId, model, source = null) => {
    const {
      index,
      indexById,
      usagesByTarget,
      parentById,
      overrideByReplacementId,
      overridesByOriginalKey,
      constraintsById,
      idDeclarations,
      idrefDeclarations,
    } = buildIndex(model);
    set({
      schemaId,
      model,
      source,
      index,
      indexById,
      usagesByTarget,
      parentById,
      overrideByReplacementId,
      overridesByOriginalKey,
      constraintsById,
      idDeclarations,
      idrefDeclarations,
      selectedId: null,
      expandedIds: new Set(),
      searchQuery: "",
      validationResult: null,
      diagnosticsVisible: true,
      minimapVisible: defaultMinimapVisible(),
      sourceJump: null,
    });
  },

  setSchemaId: (schemaId) => set({ schemaId }),

  clearSchema: () =>
    set({
      schemaId: null,
      model: null,
      source: null,
      index: [],
      indexById: new Map(),
      usagesByTarget: new Map(),
      parentById: new Map(),
      overrideByReplacementId: new Map(),
      overridesByOriginalKey: new Map(),
      constraintsById: new Map(),
      idDeclarations: [],
      idrefDeclarations: [],
      selectedId: null,
      expandedIds: new Set(),
      validationResult: null,
      sourceJump: null,
    }),

  setActiveTab: (tab) => set({ activeTab: tab }),

  setSelected: (id) => {
    set({ selectedId: id, sourceJump: null });
  },

  selectAndReveal: (id) => {
    const { indexById, parentById, expandedIds } = get();
    const toExpand = collectRevealIds(id, indexById, parentById);
    const next = toExpand.length ? new Set([...expandedIds, ...toExpand]) : expandedIds;
    set({ expandedIds: next, selectedId: id, sourceJump: null });
  },

  jumpToSource: (ref) => {
    set({ activeTab: "text", sourceJump: ref });
  },

  toggleExpanded: (id) => {
    const { expandedIds } = get();
    const next = new Set(expandedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    set({ expandedIds: next });
  },

  setExpanded: (id, expanded) => {
    const { expandedIds } = get();
    const next = new Set(expandedIds);
    if (expanded) next.add(id);
    else next.delete(id);
    set({ expandedIds: next });
  },

  setExpandedIds: (ids) => set({ expandedIds: new Set(ids) }),

  setFilterKinds: (kinds) => set({ filterKinds: kinds }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setValidationResult: (result) => set({ validationResult: result }),
  setDiagnosticsVisible: (visible) => set({ diagnosticsVisible: visible }),
  setMinimapVisible: (visible) => set({ minimapVisible: visible }),
}));

export function lookupNode(
  id: string,
  indexById: Map<string, NodeIndexEntry>,
): SchemaNode | undefined {
  return indexById.get(id)?.node;
}
