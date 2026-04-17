// Reads and writes the current selection into the URL hash so links are
// shareable, e.g. #/id/element%3A%7Bhttp%3A%2F%2Fexample.com%7DPerson

const PREFIX = "#/id/";

export function readHashSelection(): string | null {
  const hash = window.location.hash;
  if (!hash.startsWith(PREFIX)) return null;
  try {
    return decodeURIComponent(hash.slice(PREFIX.length));
  } catch {
    return null;
  }
}

export function writeHashSelection(id: string | null): void {
  const next = id ? `${PREFIX}${encodeURIComponent(id)}` : "";
  if (next === window.location.hash) return;
  history.replaceState(null, "", `${window.location.pathname}${window.location.search}${next}`);
}
