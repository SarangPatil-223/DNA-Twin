// Visual language taken from the reference demo (dna_recovery.html):
// warm paper, black outlines, green accent, amber and red for warnings and failures.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#FAF9F5",
        ink: "#14171C",
        soft: "#565C66",
        line: "#DEDBD2",
        brand: { DEFAULT: "#2E9E5B", deep: "#237A46", tint: "#E7F4EB" },
        amber: { DEFAULT: "#B8802F", tint: "#F6EEDF" },
        baseA: "#2E9E5B",
        baseT: "#B8802F",
        baseG: "#7A5CC9",
        baseC: "#C43D3D",
        ok: "#2E9E5B",
        okTint: "#E7F4EB",
        bad: "#C43D3D",
        badTint: "#FBEAEA",
        warn: "#946622",
        warnTint: "#F6EEDF",
      },
      fontFamily: {
        display: ['"Archivo Black"', '"Arial Black"', "sans-serif"],
        body: ['"Inter"', "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", '"JetBrains Mono"', "Menlo", "monospace"],
      },
      boxShadow: { lift: "none" },
    },
  },
  plugins: [],
};
