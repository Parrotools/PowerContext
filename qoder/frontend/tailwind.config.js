/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f4ff',
          100: '#dbe4ff',
          500: '#4263eb',
          600: '#3b5bdb',
          700: '#364fc7',
        },
      },
    },
  },
  plugins: [],
}
