/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-primary':    'var(--bg-primary)',
        'bg-secondary':  'var(--bg-secondary)',
        'bg-card':       'var(--bg-card)',
        'bg-card-hover': 'var(--bg-card-hover)',
        'border-clr':    'var(--border)',
        'txt-primary':   'var(--text-primary)',
        'txt-secondary': 'var(--text-secondary)',
        'txt-muted':     'var(--text-muted)',
        'acc-blue':      'var(--accent-blue)',
        'acc-teal':      'var(--accent-teal)',
        'acc-green':     'var(--accent-green)',
        'acc-orange':    'var(--accent-orange)',
        'acc-purple':    'var(--accent-purple)',
        'acc-pink':      'var(--accent-pink)',
        'acc-red':       'var(--accent-red)',
        'acc-indigo':    'var(--accent-indigo)',
      },
      fontFamily: {
        body:    ['Inter', 'system-ui', 'sans-serif'],
        heading: ['"Space Grotesk"', 'Inter', 'system-ui', 'sans-serif'],
      },
      height: {
        header: 'var(--header-height)',
      },
    },
  },
  plugins: [],
}
