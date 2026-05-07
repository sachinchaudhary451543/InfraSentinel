module.exports = {
  content: [
    "./web/templates/**/*.html",
    "./web/templates/**/*.jinja",
    "./web/templates/**/**.html",
    "./admin_portal/templates/**/*.html",
    "./web/static/js/**/*.js",
  ],
  safelist: [
    {
      pattern:
        /^(bg|text|border|ring|hover|md:|lg:|sm:|p|m|w|h|col-span|row-span|gap|justify|items|rounded|shadow)-/,
    },
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ["Outfit", "sans-serif"],
        body: ["Inter", "sans-serif"],
      },
      colors: {
        dark: {
          900: "#0a0e1a",
          800: "#0f1529",
          700: "#151d35",
          600: "#1a2342",
          500: "#1f2b4f",
        },
        accent: {
          blue: "#3b82f6",
          indigo: "#6366f1",
          violet: "#8b5cf6",
          cyan: "#06b6d4",
          emerald: "#10b981",
          rose: "#f43f5e",
          amber: "#f59e0b",
        },
      },
    },
  },
  plugins: [],
};
