import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Editorial light — page backgrounds
        base: {
          DEFAULT: "#FAFAF8",
          surface: "#F4F3EF",
          hover: "#EEECEA",
          card: "#FFFFFF",
        },
        // Indigo brand
        brand: {
          DEFAULT: "#4F46E5",
          secondary: "#6366F1",
        },
        // Text
        ink: {
          primary: "#18181B",
          secondary: "#3F3F46",
          muted: "#71717A",
        },
        // Border
        border: {
          DEFAULT: "#E4E1DC",
          hover: "#C7C3BC",
        },
        // Tier colors (light-mode values — readable on white/warm-gray bg)
        tier: {
          s: "#D97706",
          a: "#059669",
          b: "#7C3AED",
          c: "#6B7280",
          f: "#DC2626",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ["Lora", "Georgia", "Times New Roman", "serif"],
        mono: ["JetBrains Mono", "SF Mono", "Menlo", "monospace"],
      },
      borderRadius: {
        sm: "5px",
        md: "10px",
        lg: "16px",
      },
      boxShadow: {
        sm: "0 1px 4px rgba(0,0,0,0.06)",
        md: "0 4px 16px rgba(0,0,0,0.08)",
        lg: "0 8px 32px rgba(0,0,0,0.12)",
        inset: "inset 0 1px 2px rgba(0,0,0,0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
