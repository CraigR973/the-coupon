import type { Config } from 'tailwindcss';

// Tailwind replaces <alpha-value> for both solid and opacity-modified utilities.
// The paired RGB channels live beside the hex design tokens in index.css.
const alpha = (token: string) => `rgb(var(--${token}-rgb) / <alpha-value>)`;

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surface tiers
        background: alpha('bg'),
        bg: alpha('bg'),
        surface: alpha('surface'),
        'surface-elevated': alpha('surface-elevated'),
        'surface-overlay': alpha('surface-overlay'),
        border: alpha('border'),
        'border-strong': alpha('border-strong'),

        // Text
        'text-primary': alpha('text-primary'),
        'text-secondary': alpha('text-secondary'),
        'text-muted': alpha('text-muted'),
        'text-inverse': alpha('text-inverse'),
        // On-brand text (locked dark across themes — see index.css)
        'on-primary': alpha('on-primary'),
        'on-accent': alpha('on-accent'),

        // Brand
        primary: {
          DEFAULT: alpha('primary'),
          dark: alpha('primary-dark'),
        },
        accent: {
          DEFAULT: alpha('accent'),
          dark: alpha('accent-dark'),
        },
        metal: {
          DEFAULT: alpha('metal'),
          mid: alpha('metal-mid'),
          dark: alpha('metal-dark'),
        },

        // Semantic
        success: alpha('success'),
        warning: alpha('warning'),
        error: alpha('error'),
        locked: alpha('locked'),
        live: alpha('live'),

        // Rank medals
        gold: alpha('gold'),
        silver: alpha('silver'),
        bronze: alpha('bronze'),
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
        primary: alpha('primary-ink'),
        success: alpha('success-ink'),
        warning: alpha('warning-ink'),
        accent: alpha('accent-ink'),
        error: alpha('error-ink'),
        live: alpha('live-ink'),
        gold: alpha('gold-ink'),
        bronze: alpha('bronze-ink'),
      },
      fontFamily: {
        sans: ['Outfit', 'system-ui', 'sans-serif'],
        // `font-display` aliases to Outfit so legacy heading/numeric usages
        // remain readable. The Brand wordmark uses `font-mono` directly.
        display: ['Outfit', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      // Batch 151: no interface text sits below this named 12px / 16px
      // caption step. Components use it instead of arbitrary 9–11px values.
      fontSize: {
        caption: ['0.75rem', { lineHeight: '1rem' }],
        label: ['0.875rem', { lineHeight: '1.125rem' }],
        price: ['1.0625rem', { lineHeight: '1.25rem', fontWeight: '600' }],
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
        'glow-on-brand': 'var(--shadow-glow-on-brand)',
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
