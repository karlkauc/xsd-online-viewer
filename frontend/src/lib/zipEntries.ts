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
  const names: string[] = [];
  let offset = directoryOffset;
  for (let i = 0; i < entryCount; i += 1) {
    if (offset + 46 > bytes.byteLength || view.getUint32(offset, true) !== CENTRAL_SIGNATURE) break;
    const flags = view.getUint16(offset + 8, true);
    const nameLength = view.getUint16(offset + 28, true);
    const extraLength = view.getUint16(offset + 30, true);
    const commentLength = view.getUint16(offset + 32, true);
    const nameStart = offset + 46;
    const nameBytes = bytes.subarray(nameStart, nameStart + nameLength);
    const extra = bytes.subarray(nameStart + nameLength, nameStart + nameLength + extraLength);
    // Decoded the way the backend's zipfile (Python 3.12) does: the main
    // schema picked here is sent by name and has to match its spelling there.
    const name = flags & UTF8_FLAG ? utf8.decode(nameBytes) : (unicodePath(extra, nameBytes) ?? decodeCp437(nameBytes));
    if (!name.endsWith("/")) names.push(name);
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return names;
}

const UNICODE_PATH_FIELD = 0x7075;

/**
 * The UTF-8 name an Info-ZIP unicode path field carries for a name stored in
 * a legacy code page (Windows archivers: CP866 for Cyrillic). Only used while
 * its CRC still matches the stored name.
 */
function unicodePath(extra: Uint8Array, nameBytes: Uint8Array): string | null {
  const view = new DataView(extra.buffer, extra.byteOffset, extra.byteLength);
  for (let pos = 0; pos + 4 <= extra.byteLength; ) {
    const id = view.getUint16(pos, true);
    const size = view.getUint16(pos + 2, true);
    const data = extra.subarray(pos + 4, pos + 4 + size);
    if (id === UNICODE_PATH_FIELD && data.length === size && size >= 5 && data[0] === 1) {
      const storedCrc = new DataView(data.buffer, data.byteOffset + 1, 4).getUint32(0, true);
      if (storedCrc === crc32(nameBytes)) return new TextDecoder("utf-8").decode(data.subarray(5));
    }
    pos += 4 + size;
  }
  return null;
}

// Upper half of IBM code page 437, the ZIP default for names without the UTF-8 flag.
const CP437_HIGH =
  "ÇüéâäàåçêëèïîìÄÅ" +
  "ÉæÆôöòûùÿÖÜ¢£¥₧ƒ" +
  "áíóúñÑªº¿⌐¬½¼¡«»" +
  "░▒▓│┤╡╢╖╕╣║╗╝╜╛┐" +
  "└┴┬├─┼╞╟╚╔╩╦╠═╬╧" +
  "╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀" +
  "αßΓπΣσµτΦΘΩδ∞φε∩" +
  "≡±≥≤⌠⌡÷≈°∙·√ⁿ²■ ";

function decodeCp437(bytes: Uint8Array): string {
  let out = "";
  for (const byte of bytes) out += byte < 0x80 ? String.fromCharCode(byte) : CP437_HIGH[byte - 0x80];
  return out;
}

let crcTable: Uint32Array | null = null;

function crc32(bytes: Uint8Array): number {
  if (crcTable === null) {
    crcTable = new Uint32Array(256);
    for (let n = 0; n < 256; n += 1) {
      let c = n;
      for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crcTable[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (const byte of bytes) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
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
