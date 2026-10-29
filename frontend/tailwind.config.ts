/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Theme-reactive tokens (dark default, overridden by html.light)
        'hc-bg':          'var(--color-bg)',
        'hc-surface':     'var(--color-surface)',
        'hc-surface-2':   'var(--color-surface-2)',
        'hc-border':      'var(--color-border)',
        'hc-border-2':    'var(--color-border-2)',
        'hc-text':        'var(--color-text)',
        'hc-text-2':      'var(--color-text-2)',
        'hc-text-3':      'var(--color-text-3)',
        'hc-accent':      'var(--color-accent)',
        'hc-accent-dim':  'var(--color-accent-dim)',
        'hc-success':     'var(--color-success)',
        'hc-error':       'var(--color-error)',
        'hc-warning':     'var(--color-warning)',
        // Edge type colors (theme-independent)
        'edge-teammate':  '#22c55e',
        'edge-college':   '#3b82f6',
        'edge-draft':     '#eab308',
        'edge-coach':     '#7c4daa',
        'edge-allstar':   '#ef4444',
      },
      fontFamily: {
        display:    ['Bebas Neue', 'sans-serif'],
        condensed:  ['Barlow Condensed', 'sans-serif'],
        sans:       ['Barlow', 'system-ui', 'sans-serif'],
        mono:       ['Barlow Condensed', 'monospace'],
      },
      borderRadius: {
        'hc':    '4px',
        'hc-sm': '2px',
        'hc-lg': '6px',
        'hc-xl': '6px',
      },
      animation: {
        'shake':       'shake 0.4s ease-in-out',
        'flash-error': 'flashError 0.4s ease-in-out',
        'fade-in':     'fadeIn 0.3s ease-out',
        'slide-up':    'slideUp 0.4s ease-out',
        'flash-bg':    'flashBg 1s ease-out',
      },
      keyframes: {
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '10%, 30%, 50%, 70%, 90%': { transform: 'translateX(-6px)' },
          '20%, 40%, 60%, 80%': { transform: 'translateX(6px)' },
        },
        flashError: {
          '0%, 100%': { backgroundColor: 'transparent' },
          '50%': { backgroundColor: 'rgba(239, 68, 68, 0.15)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        flashBg: {
          '0%': { backgroundColor: 'var(--color-accent)' },
          '100%': { backgroundColor: 'var(--color-surface)' },
        },
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
        '88': '22rem',
      },
      zIndex: {
        '60': '60',
        '70': '70',
        '80': '80',
        '90': '90',
        '100': '100',
      },
    },
  },
  plugins: [],
}
