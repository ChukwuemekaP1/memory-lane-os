/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: "var(--ml-accent)",
        canvas: "var(--ml-background)",
        linen: "var(--background)",
        ink: "var(--foreground)",
        woodland: "var(--primary)",
        cream: "var(--primary-foreground)",
        paper: "var(--paper)",
        gold: "var(--gold)",
        bronze: "var(--bronze)",
        sage: "var(--sage)",
        rose: "var(--rose)",
        marigold: "var(--marigold)",
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        editorial: "var(--radius)",
      },
    },
  },
  plugins: [],
};
