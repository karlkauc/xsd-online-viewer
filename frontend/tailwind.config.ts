import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      screens: {
        // Coarse pointer = finger; used to enlarge tap targets regardless of width.
        touch: { raw: "(pointer: coarse)" },
        // Landscape phones: trade header chrome for content height.
        short: { raw: "(max-height: 500px)" },
      },
      fontFamily: {
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "SF Mono",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      colors: {
        accent: {
          DEFAULT: "#3b82f6",
          dark: "#60a5fa",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
