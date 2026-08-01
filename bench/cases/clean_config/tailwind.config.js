/*
  The whole point of this case: the ramp below is *this project's*, and it
  reuses the names Tailwind ships. Every `text-lg` on the page is a step in a
  ratio someone picked, not the framework's 1.125rem — but the class looks
  identical either way, so a decoder that never reads this file calls the most
  careful project in the corpus "no typography decisions".

  Deliberately narrow: spacing, sizing and layout are left on Tailwind's own
  scales, so typography is the only axis this file can rescue. Anything else the
  case scores, it scored without help.
*/
module.exports = {
  content: ['./index.html'],
  theme: {
    // A full override, not an extend: Tailwind's type ramp is gone.
    fontSize: {
      xs: ['0.7rem', { lineHeight: '1.5' }],
      sm: ['0.82rem', { lineHeight: '1.55' }],
      base: ['1rem', { lineHeight: '1.62' }],
      lg: ['1.29rem', { lineHeight: '1.45' }],
      xl: ['1.66rem', { lineHeight: '1.3' }],
      '2xl': ['2.14rem', { lineHeight: '1.18' }],
      '3xl': ['2.76rem', { lineHeight: '1.06' }],
      display: ['4.1rem', { lineHeight: '0.94', letterSpacing: '-0.03em' }],
    },
    extend: {
      fontFamily: {
        serif: ['Arnhem', 'Georgia', 'serif'],
        sans: ['Untitled Sans', 'system-ui', 'sans-serif'],
      },
      colors: {
        paper: '#f6f4ef',
        ink: '#1b1a17',
        'ink-soft': '#4c4941',
        rule: '#ddd8cb',
        madder: '#8c3a2b',
      },
      letterSpacing: {
        plate: '0.18em',
      },
      borderRadius: {
        panel: '3px',
      },
    },
  },
}
