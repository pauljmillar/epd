import type { Config } from "tailwindcss";

// BRD §12: strict B/W/gray + #CC0000 only. No other colors anywhere in the app.
const palette = {
  page: "#F9F9F9",
  card: "#FFFFFF",
  border: "#E5E5E5",
  borderSubtle: "#F0F0F0",
  text: "#111111",
  textSecondary: "#666666",
  textTertiary: "#999999",
  chartSecondary: "#AAAAAA",
  chartFill: "#F5F5F5",
  active: "#F0F0F0",
  alert: "#CC0000",
};

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // Wipe Tailwind's default color palette. Only the EPD palette below is available.
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: "#FFFFFF",
      black: "#000000",
      page: palette.page,
      card: palette.card,
      border: palette.border,
      "border-subtle": palette.borderSubtle,
      text: palette.text,
      "text-secondary": palette.textSecondary,
      "text-tertiary": palette.textTertiary,
      "chart-secondary": palette.chartSecondary,
      "chart-fill": palette.chartFill,
      active: palette.active,
      alert: palette.alert,
    },
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
