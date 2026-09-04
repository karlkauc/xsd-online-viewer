/**
 * Hand an uploaded XML document over to the sibling XML viewer.
 *
 * We open `XML_VIEWER_URL?from=xsd-viewer` in a new tab and keep the File in
 * memory. The new tab posts `{type: "xml-viewer:ready"}` back to us once it
 * has mounted; we answer with `{type: "xml-viewer:file", name, content}` and
 * transfer the ArrayBuffer. This only works while we send no
 * `Cross-Origin-Opener-Policy: same-origin` header (a popup opened under that
 * policy loses its opener); `same-origin-allow-popups` would be fine.
 */
import { XML_VIEWER_URL } from "./uploadErrors";

export const XML_VIEWER_ORIGINS = ["https://www.xml-viewer.online", "https://xml-viewer.online"];
export const HANDOFF_TIMEOUT_MS = 15_000;

/**
 * Origins the XML viewer accepts a hand-off from (its `SENDER_ORIGINS` in
 * lib/handoff.ts). It posts its ready message only to these, so from any
 * other host the hand-off can never complete — better to say so up front.
 */
export const HANDOFF_SENDER_ORIGINS = [
  "https://www.xsd-viewer.online",
  "https://xsd-viewer.online",
  "https://viewer.status20.net",
];

export function handoffSupported(origin: string = window.location.origin): boolean {
  if (HANDOFF_SENDER_ORIGINS.includes(origin)) return true;
  return import.meta.env.DEV && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
}

export const HANDOFF_UNSUPPORTED_HINT =
  "Automatic hand-off only works from www.xsd-viewer.online and viewer.status20.net. " +
  "Download the file and upload it in the XML Viewer instead.";

export function handoffUrl(base: string = XML_VIEWER_URL): string {
  const url = new URL(base);
  url.searchParams.set("from", "xsd-viewer");
  return url.toString();
}

function isAllowedOrigin(origin: string): boolean {
  if (XML_VIEWER_ORIGINS.includes(origin)) return true;
  return import.meta.env.DEV && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
}

export interface HandoffOptions {
  target?: string;
  timeoutMs?: number;
}

/**
 * Open the XML viewer and hand `file` over once it reports ready.
 * Resolves `true` when the file was posted, `false` when the popup was blocked
 * or never answered (the tab stays open; the user can upload manually).
 */
export async function openInXmlViewer(file: File, opts: HandoffOptions = {}): Promise<boolean> {
  const target = opts.target ?? handoffUrl();
  const timeoutMs = opts.timeoutMs ?? HANDOFF_TIMEOUT_MS;
  // Read before opening so a slow disk cannot delay the reply.
  const content = await file.arrayBuffer();

  const popup = window.open(target, "_blank");
  if (!popup) return false;
  const targetOrigin = new URL(target).origin;

  return new Promise<boolean>((resolve) => {
    let timer = 0;
    const finish = (ok: boolean) => {
      window.removeEventListener("message", onMessage);
      window.clearTimeout(timer);
      resolve(ok);
    };
    const onMessage = (event: MessageEvent) => {
      if (event.source !== popup || !isAllowedOrigin(event.origin)) return;
      const data = event.data as { type?: unknown } | null;
      if (!data || data.type !== "xml-viewer:ready") return;
      popup.postMessage({ type: "xml-viewer:file", name: file.name, content }, targetOrigin, [content]);
      finish(true);
    };
    window.addEventListener("message", onMessage);
    timer = window.setTimeout(() => finish(false), timeoutMs);
  });
}
