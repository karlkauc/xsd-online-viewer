// Image exports of a React Flow diagram. We use html-to-image (React Flow's
// own recommended path) because the diagram nodes are styled via external
// Tailwind classes — an in-house foreignObject approach cannot inline those
// computed styles and produces unstyled/blank output.

import { toPng, toSvg } from "html-to-image";
import { getNodesBounds, type Node } from "@xyflow/react";

// Chromium caps single-canvas sides around 8192 px. Clamp defensively so huge
// diagrams downscale instead of silently failing the PNG encode.
const MAX_SIDE = 8192;

export interface ExportOptions {
  filename: string;
  backgroundColor?: string;
  padding?: number;
  pixelRatio?: number;
}

interface RenderParams {
  width: number;
  height: number;
  transform: string;
  backgroundColor: string;
  filter: (node: HTMLElement) => boolean;
}

function computeRenderParams(
  nodes: Node[],
  opts: ExportOptions,
): RenderParams {
  const padding = opts.padding ?? 40;
  const bounds = getNodesBounds(nodes);

  let width = Math.ceil(bounds.width + padding * 2);
  let height = Math.ceil(bounds.height + padding * 2);

  // Fit the longest side to MAX_SIDE while preserving aspect ratio.
  let scale = 1;
  const longest = Math.max(width, height);
  if (longest > MAX_SIDE) {
    scale = MAX_SIDE / longest;
    width = Math.floor(width * scale);
    height = Math.floor(height * scale);
  }

  const tx = (-bounds.x + padding) * scale;
  const ty = (-bounds.y + padding) * scale;
  const transform = `translate(${tx}px, ${ty}px) scale(${scale})`;

  const backgroundColor =
    opts.backgroundColor ||
    getComputedStyle(document.body).backgroundColor ||
    "#ffffff";

  // Exclude overlay chrome that may sit inside .react-flow__viewport — if any.
  const filter = (node: HTMLElement) => {
    if (!(node instanceof Element)) return true;
    const cls = (node as Element).classList;
    if (!cls) return true;
    return !(
      cls.contains("react-flow__minimap") ||
      cls.contains("react-flow__controls") ||
      cls.contains("react-flow__attribution")
    );
  };

  return { width, height, transform, backgroundColor, filter };
}

function triggerDownload(dataUrl: string, filename: string) {
  const anchor = document.createElement("a");
  anchor.href = dataUrl;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

async function ensureNodesMeasured(): Promise<void> {
  // One rAF is usually enough for React Flow to settle node measurements.
  await new Promise<void>((resolve) =>
    requestAnimationFrame(() => resolve()),
  );
}

export async function exportFlowAsPng(
  viewportEl: HTMLElement,
  nodes: Node[],
  opts: ExportOptions,
): Promise<void> {
  if (nodes.length === 0) throw new Error("Nothing to export — the diagram is empty.");
  await ensureNodesMeasured();
  const { width, height, transform, backgroundColor, filter } =
    computeRenderParams(nodes, opts);
  const dataUrl = await toPng(viewportEl, {
    backgroundColor,
    width,
    height,
    pixelRatio: opts.pixelRatio ?? 2,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      transform,
    },
    filter,
    cacheBust: true,
  });
  triggerDownload(dataUrl, opts.filename);
}

export async function exportFlowAsSvg(
  viewportEl: HTMLElement,
  nodes: Node[],
  opts: ExportOptions,
): Promise<void> {
  if (nodes.length === 0) throw new Error("Nothing to export — the diagram is empty.");
  await ensureNodesMeasured();
  const { width, height, transform, backgroundColor, filter } =
    computeRenderParams(nodes, opts);
  const dataUrl = await toSvg(viewportEl, {
    backgroundColor,
    width,
    height,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      transform,
    },
    filter,
    cacheBust: true,
  });
  triggerDownload(dataUrl, opts.filename);
}
