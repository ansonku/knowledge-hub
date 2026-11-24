import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'

// PrimeVue's preset is global, so the light scheme keeps the existing primary
// (blue.700 = --ui-accent #1d4ed8) and legacy pages render unchanged.
// The dark scheme applies only under `.hub-dark`, which legacy pages never set.
export const hubTheme = definePreset(Aura, {
  semantic: {
    primary: {
      50: '{blue.50}', 100: '{blue.100}', 200: '{blue.200}', 300: '{blue.300}',
      400: '{blue.400}', 500: '{blue.500}', 600: '{blue.600}', 700: '{blue.700}',
      800: '{blue.800}', 900: '{blue.900}', 950: '{blue.950}',
    },
    colorScheme: {
      light: { primary: { color: '{blue.700}', hoverColor: '{blue.800}', activeColor: '{blue.900}' } },
      dark: { primary: { color: '{blue.400}', hoverColor: '{blue.300}', activeColor: '{blue.200}' } },
    },
  },
})

export const themeOptions = {
  preset: hubTheme,
  options: { darkModeSelector: '.hub-dark' },
}
