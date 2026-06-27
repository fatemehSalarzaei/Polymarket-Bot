import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#f7f7f2",
        ink: "#18181b",
        muted: "#71717a",
        accent: "#0f766e",
        danger: "#b91c1c",
      },
    },
  },
  plugins: [],
};

export default config;

