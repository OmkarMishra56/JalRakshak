/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B1520",       
        panel: "#101E2E",     
        panel2: "#16283B",    
        line: "#223247",      
        mist: "#7C93A8",      
        foam: "#E7EFF5",      
        tide: "#2DD4BF",      
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
