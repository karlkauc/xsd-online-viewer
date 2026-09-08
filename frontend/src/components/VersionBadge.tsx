import type { VersionConstraints } from "../types/schema";

// XSD 1.1 ``vc:*`` conditional-inclusion chip — summarizes a declaration's
// version constraints (minVersion/maxVersion/typeAvailable/...) as a short
// mono badge, with the full breakdown in its title tooltip.
export function VersionBadge({ vc }: { vc: VersionConstraints }) {
  const summary = summarizeVersionConstraints(vc);
  if (!summary) return null;
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:border-amber-800/60"
      title={describeVersionConstraints(vc)}
    >
      <span className="text-[9px] uppercase tracking-wide font-semibold opacity-70">
        vc
      </span>
      {summary}
    </span>
  );
}

function summarizeVersionConstraints(vc: VersionConstraints): string | null {
  if (vc.min_version && vc.max_version) {
    return `${vc.min_version}–${vc.max_version}`;
  }
  if (vc.min_version) return `≥ ${vc.min_version}`;
  if (vc.max_version) return `< ${vc.max_version}`;
  if (vc.type_available) return `needs ${stripPrefix(vc.type_available)}`;
  if (vc.facet_available) return `needs ${stripPrefix(vc.facet_available)}`;
  if (vc.type_unavailable) return `not ${stripPrefix(vc.type_unavailable)}`;
  if (vc.facet_unavailable) return `not ${stripPrefix(vc.facet_unavailable)}`;
  return null;
}

function describeVersionConstraints(vc: VersionConstraints): string {
  const parts: string[] = [];
  if (vc.min_version) parts.push(`minVersion=${vc.min_version}`);
  if (vc.max_version) parts.push(`maxVersion=${vc.max_version}`);
  if (vc.type_available) parts.push(`typeAvailable=${vc.type_available}`);
  if (vc.type_unavailable) parts.push(`typeUnavailable=${vc.type_unavailable}`);
  if (vc.facet_available) parts.push(`facetAvailable=${vc.facet_available}`);
  if (vc.facet_unavailable)
    parts.push(`facetUnavailable=${vc.facet_unavailable}`);
  return parts.join(" · ");
}

function stripPrefix(qname: string): string {
  // Show first listed name without prefix for compactness in chips.
  const first = qname.split(/\s+/)[0];
  const colon = first.indexOf(":");
  return colon === -1 ? first : first.slice(colon + 1);
}
