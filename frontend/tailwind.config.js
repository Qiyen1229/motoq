/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Noto Serif TC"', '"Songti TC"', '"PMingLiU"', "Georgia", "serif"],
      },
      // 暖調灰黑：全站的中性色
      colors: {
        slate: {
          50: "#f7f6f3", 100: "#eeece7", 200: "#dedbd3", 300: "#c4c0b5", 400: "#9c988d",
          500: "#78746b", 600: "#58554e", 700: "#3b3935", 800: "#262523", 900: "#171716", 950: "#0c0c0b",
        },
        // 金：強調色（深色底用 400/500，淺色底文字用 700）
        brand: {
          50: "#fbf7e8", 100: "#f5ebc3", 200: "#ecd993", 300: "#e2c46c", 400: "#d6b252",
          500: "#c9a24a", 600: "#b08a32", 700: "#876a1f", 800: "#5f4a14", 900: "#3b2d0c",
        },
      },
    },
  },
  plugins: [],
};
