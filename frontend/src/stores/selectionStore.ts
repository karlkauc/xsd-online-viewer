import { create } from "zustand";
import type {
  NodeIndexEntry,
  SchemaModel,
  SchemaNode,
  SchemaNodeKind,
} from "../types/schema";
import { buildIndex } from "../lib/indexSchema";

export type ViewTab = "tree" | "diagram" | "text";

interface SelectionState {
  schemaId: string | null;
  model: SchemaModel | null;
  index: NodeIndexEntry[];
  indexById: Map<string, NodeIndexEntry>;
  usagesByTarget: Map<string, NodeIndexEntry[]>;
  parentById: Map<string, string>;

  activeTab: ViewTab;
  selectedId: string | null;
  expandedIds: Set<string>;
  filterKinds: Set<SchemaNodeKind>;
  searchQuery: string;

  setSchema: (schemaId: string, model: SchemaModel) => void;
  clearSchema: () => void;
  setActiveTab: (tab: ViewTab) => void;
  setSelected: (id: string | null) => void;
  toggleExpanded: (id: string) => void;
  setExpanded: (id: string, expanded: boolean) => void;
  setExpandedIds: (ids: Set<string>) => void;
  setFilterKinds: (kinds: Set<SchemaNodeKind>) => void;
  setSearchQuery: (query: string) => void;
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
  index: [],
  indexById: new Map(),
  usagesByTarget: new Map(),
  parentById: new Map(),

  activeTab: "diagram",
  selectedId: null,
  expandedIds: new Set(),
  filterKinds: new Set(ALL_KINDS),
  searchQuery: "",

  setSchema: (schemaId, model) => {
    const { index, indexById, usagesByTarget, parentById } = buildIndex(model);
    set({
      schemaId,
      model,
      index,
      indexById,
      usagesByTarget,
      parentById,
      selectedId: null,
      expandedIds: new Set(),
      searchQuery: "",
    });
  },

  clearSchema: () =>
    set({
      schemaId: null,
      model: null,
      index: [],
      indexById: new Map(),
      usagesByTarget: new Map(),
      parentById: new Map(),
      selectedId: null,
      expandedIds: new Set(),
    }),

  setActiveTab: (tab) => set({ activeTab: tab }),

  setSelected: (id) => {
    set({ selectedId: id });
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
}));

export function lookupNode(
  id: string,
  indexById: Map<string, NodeIndexEntry>,
): SchemaNode | undefined {
  return indexById.get(id)?.node;
}
