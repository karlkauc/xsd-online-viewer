// Apply the stored/preferred theme before React mounts to avoid a flash.
// Kept as an external file: the SPA's CSP is `script-src 'self'`, which
// forbids inline scripts.
(() => {
  let stored = null;
  try {
    stored = localStorage.getItem("xsdv-theme");
  } catch {
    // storage may be blocked; fall back to the OS preference
  }
  const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.classList.toggle("dark", (stored || preferred) === "dark");
})();
