import type { Facet, SimpleType } from "../../types/schema";
import { FacetGroups } from "../FacetGroups";

interface SimpleTypeCardProps {
  /** The owning simple type, when one is available (may be inline or named). */
  simple?: SimpleType | null;
  /** Optional standalone facet list — used by complexType simple-content where
   *  there is no full SimpleType node (just facets + a base QName). */
  standaloneFacets?: Facet[];
  standaloneBase?: string | null;
  /** When facets come from a separate named type, label the source. */
  inheritedFrom?: string | null;
  /** Empty-state text when neither simple nor standaloneFacets are useful. */
  emptyText?: string;
}

export function SimpleTypeCard({
  simple,
  standaloneFacets,
  standaloneBase,
  inheritedFrom,
  emptyText = "No constraints — accepts any value of the base type.",
}: SimpleTypeCardProps) {
  if (simple) {
    const restriction = {
      base: simple.base,
      derivation: simple.derivation,
      item_type: simple.item_type,
      member_types: simple.member_types,
    };
    if (!simple.facets.length && !simple.base && !simple.item_type && !simple.member_types.length) {
      return (
        <section className="px-6 py-4 text-sm text-slate-500 dark:text-slate-400">
          {emptyText}
        </section>
      );
    }
    return (
      <section className="px-6 py-4">
        <FacetGroups
          facets={simple.facets}
          restriction={restriction}
          inheritedFrom={inheritedFrom ?? null}
        />
      </section>
    );
  }

  if (standaloneFacets && (standaloneFacets.length > 0 || standaloneBase)) {
    return (
      <section className="px-6 py-4">
        <FacetGroups
          facets={standaloneFacets}
          restriction={
            standaloneBase
              ? { base: standaloneBase, derivation: "restriction", item_type: null, member_types: [] }
              : null
          }
          inheritedFrom={inheritedFrom ?? null}
        />
      </section>
    );
  }

  return (
    <section className="px-6 py-4 text-sm text-slate-500 dark:text-slate-400">
      {emptyText}
    </section>
  );
}
