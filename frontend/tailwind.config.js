/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Brand palette placeholder for FinSight AI. Refined once the
        // Dashboard UI is implemented in a later phase.
        brand: {
          50: '#eef4ff',
          100: '#d9e6ff',
          500: '#3b6bf5',
          600: '#2f56c9',
          700: '#25429c',
        },
      },
    },
  },
  plugins: [],
}
