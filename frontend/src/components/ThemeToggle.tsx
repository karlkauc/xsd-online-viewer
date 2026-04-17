import { useCallback, useEffect, useState } from "react";

type Theme = "light" | "dark";

function readInitialTheme(): Theme {
  const stored = localStorage.getItem("xsdv-theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readInitialTheme);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("xsdv-theme", theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  return (
    <button
      type="button"
      className="btn"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Theme: ${theme}`}
    >
      {theme === "dark" ? "☾" : "☀"}
    </button>
  );
}
