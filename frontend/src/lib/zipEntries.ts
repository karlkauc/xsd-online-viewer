/**
 * List the entries of a ZIP archive in the browser and guess its main schema.
 *
 * Only the central directory is read — nothing is decompressed — so this is
 * cheap even for large bundles and needs no ZIP library. Anything we cannot
 * parse (ZIP64, a truncated archive) yields an empty list and the backend's
 * own heuristic takes over.
 */

const EOCD_SIGNATURE = 0x06054b50;
const CENTRAL_SIGNATURE = 0x02014b50;
const MAX_COMMENT = 0xffff;
const UTF8_FLAG = 1 << 11;

export async function listZipEntries(file: Blob): Promise<string[]> {
  const buffer = await file.arrayBuffer();
  return parseZipEntries(new Uint8Array(buffer));
}

export function parseZipEntries(bytes: Uint8Array): string[] {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const eocd = findEndOfCentralDirectory(view);
  if (eocd < 0) return [];
  const entryCount = view.getUint16(eocd + 10, true);
  const directorySize = view.getUint32(eocd + 12, true);
  const directoryOffset = view.getUint32(eocd + 16, true);
  if (entryCount === 0xffff || directoryOffset === 0xffffffff) return []; // ZIP64
  if (directoryOffset + directorySize > bytes.byteLength) return [];

  const utf8 = new TextDecoder("utf-8");
  const latin1 = new TextDecoder("latin1");
  const names: string[] = [];
  let offset = directoryOffset;
  for (let i = 0; i < entryCount; i += 1) {
    if (offset + 46 > bytes.byteLength || view.getUint32(offset, true) !== CENTRAL_SIGNATURE) break;
    const flags = view.getUint16(offset + 8, true);
    const nameLength = view.getUint16(offset + 28, true);
    const extraLength = view.getUint16(offset + 30, true);
    const commentLength = view.getUint16(offset + 32, true);
    const nameBytes = bytes.subarray(offset + 46, offset + 46 + nameLength);
    const name = (flags & UTF8_FLAG ? utf8 : latin1).decode(nameBytes);
    if (!name.endsWith("/")) names.push(name);
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return names;
}

function findEndOfCentralDirectory(view: DataView): number {
  const min = Math.max(0, view.byteLength - 22 - MAX_COMMENT);
  for (let pos = view.byteLength - 22; pos >= min; pos -= 1) {
    if (view.getUint32(pos, true) === EOCD_SIGNATURE) return pos;
  }
  return -1;
}

export function xsdEntries(names: string[]): string[] {
  return names.filter((n) => n.toLowerCase().endsWith(".xsd"));
}

const SCHEMA_LOCATION_RE = /schemaLocation\s*=\s*["']([^"']+)["']/g;

function dirname(path: string): string {
  const i = path.lastIndexOf("/");
  return i < 0 ? "" : path.slice(0, i);
}

function basename(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

function normalize(path: string): string {
  const out: string[] = [];
  for (const part of path.split("/")) {
    if (part === "" || part === ".") continue;
    if (part === "..") out.pop();
    else out.push(part);
  }
  return out.join("/");
}

/** Paths a schema includes/imports, resolved relative to its own location. */
export function referencedLocations(name: string, content: string): Set<string> {
  const base = dirname(name);
  const found = new Set<string>();
  for (const match of content.slice(0, 512_000).matchAll(SCHEMA_LOCATION_RE)) {
    const location = match[1].trim();
    if (!location || location.includes("://")) continue;
    found.add(normalize(base ? `${base}/${location}` : location));
    found.add(basename(location));
  }
  return found;
}

/**
 * Mirror of the backend's `pick_main_xsd`: with contents, prefer a schema no
 * other file references; otherwise (and to break ties) the shallowest, then
 * shortest path.
 */
export function pickMainXsd(names: string[], contents?: Map<string, string>): string | undefined {
  let candidates = xsdEntries(names);
  if (candidates.length === 0) return undefined;
  if (contents) {
    const referenced = new Set<string>();
    for (const name of candidates) {
      const text = contents.get(name);
      if (text) for (const r of referencedLocations(name, text)) referenced.add(r);
    }
    const roots = candidates.filter((n) => !referenced.has(n) && !referenced.has(basename(n)));
    if (roots.length > 0) candidates = roots;
  }
  const depth = (n: string) => n.split("/").length;
  return [...candidates].sort((a, b) => depth(a) - depth(b) || a.length - b.length || a.localeCompare(b))[0];
}
