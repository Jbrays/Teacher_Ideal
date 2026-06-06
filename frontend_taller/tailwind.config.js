/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: '#f7f9fb',
        'surface-dim': '#d8dadc',
        'surface-container': '#eceef0',
        primary: '#3525cd',
        'primary-container': '#4f46e5',
        secondary: '#712ae2',
        'on-primary': '#ffffff',
        'on-surface': '#191c1e',
        'outline': '#777587',
      },
      fontFamily: {
        sans: ['Hanken Grotesk', 'sans-serif'],
      },
      borderRadius: {
        '28px': '28px',
      }
    },
  },
  plugins: [],
}
