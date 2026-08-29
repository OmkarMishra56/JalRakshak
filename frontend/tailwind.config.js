/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B1520",       // page background, deep tidal navy
        panel: "#101E2E",     // card/panel surface
        panel2: "#16283B",    // raised surface
        line: "#223247",      // hairline borders
        mist: "#7C93A8",      // secondary text
        foam: "#E7EFF5",      // primary text
        tide: "#2DD4BF",      // signature accent (teal, "current data")
        safe: "#22C55E",
        moderate: "#F5B93D",
        severe: "#EF4444",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
        mono: ["var(--font-mono)"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,0.03), 0 8px 24px -12px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [],
};
