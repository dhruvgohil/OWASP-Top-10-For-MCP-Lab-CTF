/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Blueprint / SOC console identity.
        ink: "#0B0F17", // page background (blue-tinted near-black)
        panel: "#131A26", // card surface
        panel2: "#0F1520", // inset surface
        line: "#233047", // hairline borders
        fg: "#C7D2E0", // primary text
        muted: "#7A8AA3", // secondary text
        // Trust tiers.
        public: "#3DD8C4", // public / frontend LLM (safe teal)
        classified: "#F2B94B", // internal engine / backend LLM (amber)
        breach: "#FF5C5C", // RCE / breach (signal red)
      },
      fontFamily: {
        display: ['"Space Grotesk"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
        body: ['"Inter"', "system-ui", "sans-serif"],
      },
      keyframes: {
        flow: {
          "0%": { transform: "translateY(-100%)", opacity: "0" },
          "40%": { opacity: "1" },
          "100%": { transform: "translateY(220%)", opacity: "0" },
        },
        pulseline: {
          "0%, 100%": { opacity: "0.25" },
          "50%": { opacity: "1" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
      },
      animation: {
        flow: "flow 1.1s linear infinite",
        pulseline: "pulseline 1.4s ease-in-out infinite",
        blink: "blink 1s step-end infinite",
      },
    },
  },
  plugins: [],
};
