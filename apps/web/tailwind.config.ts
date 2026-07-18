import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      boxShadow: { panel: "0 18px 60px rgba(2, 6, 23, 0.10)" },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui"] }
    }
  },
  plugins: []
} satisfies Config;
