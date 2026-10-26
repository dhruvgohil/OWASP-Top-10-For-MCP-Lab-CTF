/** @type {import('tailwindcss').Config} */
// Theme mirrored from combined-chain-lab/frontend so the scoreboard reads as
// part of the same SOC-console / blueprint system.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B0F17", // page background (blue-tinted near-black)
        panel: "#131A26", // card surface
        panel2: "#0F1520", // inset surface
        line: "#233047", // hairline borders
        fg: "#C7D2E0", // primary text
        muted: "#7A8AA3", // secondary text
        // Trust tiers.
        public: "#3DD8C4", // safe teal
        classified: "#F2B94B", // amber
        breach: "#FF5C5C", // signal red
      },
      fontFamily: {
        display: ['"Space Grotesk"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
        body: ['"Inter"', "system-ui", "sans-serif"],
      },
      keyframes: {
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        pulseline: {
          "0%, 100%": { opacity: "0.25" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        blink: "blink 1s step-end infinite",
        pulseline: "pulseline 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
