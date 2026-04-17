// Image exports of a React Flow diagram, produced entirely in the browser:
// SVG is rebuilt from the existing viewport DOM; PNG is rendered via a
// foreignObject-wrapped SVG painted onto a canvas. We purposely avoid heavy
// third-party dependencies like html-to-image.

async function serializeViewport(root: HTMLElement): Promise<{
  svg: string;
  width: number;
  height: number;
}> {
  const viewport = root.querySelector<SVGSVGElement | HTMLElement>(".react-flow__viewport");
  if (!viewport) throw new Error("react-flow viewport not found");
  const bbox = root.getBoundingClientRect();
  const width = Math.max(1, Math.round(bbox.width));
  const height = Math.max(1, Math.round(bbox.height));
  const clone = viewport.cloneNode(true) as HTMLElement;
  const xmlns = "http://www.w3.org/2000/svg";
  const svg = `
<svg xmlns="${xmlns}" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <foreignObject x="0" y="0" width="${width}" height="${height}">
    <div xmlns="http://www.w3.org/1999/xhtml" style="width:${width}px;height:${height}px">
      ${clone.outerHTML}
    </div>
  </foreignObject>
</svg>`.trim();
  return { svg, width, height };
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function exportFlowAsSvg(root: HTMLElement, filename: string): Promise<void> {
  const { svg } = await serializeViewport(root);
  triggerDownload(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }), filename);
}

export async function exportFlowAsPng(root: HTMLElement, filename: string): Promise<void> {
  const { svg, width, height } = await serializeViewport(root);
  const image = new Image();
  const svgBlob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const svgUrl = URL.createObjectURL(svgBlob);
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("image load failed"));
      image.src = svgUrl;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
    ctx.fillStyle = getComputedStyle(document.body).backgroundColor || "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(image, 0, 0);
    const blob: Blob = await new Promise((resolve, reject) =>
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("toBlob failed"))),
        "image/png",
      ),
    );
    triggerDownload(blob, filename);
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}
