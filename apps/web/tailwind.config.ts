import type { Config } from 'tailwindcss';

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surface tiers
        background: 'var(--bg)',
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-elevated': 'var(--surface-elevated)',
        'surface-overlay': 'var(--surface-overlay)',
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',

        // Text
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted': 'var(--text-muted)',
        'text-inverse': 'var(--text-inverse)',
        // On-brand text (locked dark across themes — see index.css)
        'on-primary': 'var(--on-primary)',
        'on-accent': 'var(--on-accent)',

        // Brand
        primary: {
          DEFAULT: 'var(--primary)',
          dark: 'var(--primary-dark)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          dark: 'var(--accent-dark)',
        },
        metal: {
          DEFAULT: 'var(--metal)',
          mid: 'var(--metal-mid)',
          dark: 'var(--metal-dark)',
        },

        // Semantic
        success: 'var(--success)',
        warning: 'var(--warning)',
        error: 'var(--error)',
        locked: 'var(--locked)',
        live: 'var(--live)',

        // Rank medals
        gold: 'var(--gold)',
        silver: 'var(--silver)',
        bronze: 'var(--bronze)',
      },

      // `text-*` resolves through here instead of `colors` for the brand and
      // semantic names. A colour used as a fill sits under near-black
      // `--on-primary` and must be light enough; the same name used as text sits
      // on `--surface` and must be dark enough. One value cannot be both — see
      // the note in index.css for the arithmetic — so the fill keeps the plain
      // token and the text takes the `-ink` one.
      //
      // Done here rather than by renaming call sites because there are 179 uses
      // of `text-primary` and 37 of `bg-primary`: editing either set by hand is
      // a large diff that would say nothing, while this says exactly the thing
      // that is true. `bg-*`, `border-*` and `ring-*` are untouched and still
      // read `colors`, so no fill, chip, badge or medal changes.
      textColor: {
        primary: 'var(--primary-ink)',
        success: 'var(--success-ink)',
        warning: 'var(--warning-ink)',
        accent: 'var(--accent-ink)',
        error: 'var(--error-ink)',
        live: 'var(--live-ink)',
        gold: 'var(--gold-ink)',
        bronze: 'var(--bronze-ink)',
      },
      fontFamily: {
        sans: ['Outfit', 'system-ui', 'sans-serif'],
        // `font-display` aliases to Outfit so legacy heading/numeric usages
        // remain readable. The Brand wordmark uses `font-mono` directly.
        display: ['Outfit', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        xs: 'var(--radius-xs)',
        sm: 'var(--radius-sm)',
        DEFAULT: 'var(--radius-md)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
        '2xl': 'var(--radius-2xl)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-md)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        sheet: 'var(--shadow-sheet)',
        glow: 'var(--shadow-glow)',
        'glow-accent': 'var(--shadow-glow-accent)',
      },
      borderColor: {
        DEFAULT: 'var(--border)',
      },
      backgroundColor: {
        DEFAULT: 'var(--bg)',
      },
      transitionTimingFunction: {
        'out-quart': 'cubic-bezier(0.2, 0, 0, 1)',
      },
      transitionDuration: {
        fast: '150ms',
        base: '220ms',
        page: '280ms',
        sheet: '320ms',
      },
      zIndex: {
        tabbar: '40',
        header: '50',
        banner: '55',
        sheet: '60',
        modal: '70',
        toast: '80',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config;
