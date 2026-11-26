/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        app: '#0b1220',
        panel: { DEFAULT: '#101a2e', soft: '#152238' },
        edge: '#1e2a44',
        ink: '#e2e8f0',
        dim: '#94a3b8',
        acc: { DEFAULT: '#22d3ee', fort: '#0e7490' },
        ok: '#10b981',
        warn: '#f59e0b',
        danger: '#ef4444',
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
