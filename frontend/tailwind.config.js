/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        availability: {
          blank: '#FFFFFF',
          until12pm: '#90EE90',
          until3pm: '#87CEEB',
          after330pm: '#FFB6C1',
          '12-3': '#ADD8E6',
          after12eod: '#FFDAB9',
          before12after330: '#DDA0DD',
          off: '#333333',
        }
      }
    },
  },
  plugins: [],
}
