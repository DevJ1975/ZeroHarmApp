/**
 * Zero Harm design tokens.
 * Palette is taken from ANSI Z535 safety signage: safety yellow is the one bold color,
 * used only for the weekly talk placard and primary actions. Everything else stays quiet.
 */
import { useColorScheme } from 'react-native';

export const palette = {
  safetyYellow: '#F5C400', // ANSI caution yellow, the signature element
  ink: '#17212B',          // deep steel, text on yellow and light surfaces
  concrete: '#ECEEEF',     // light background
  steel: '#5B6773',        // secondary text
  rule: '#CDD2D6',         // dividers, field borders
  signalGreen: '#16804A',  // saved, signed, done
  stopRed: '#C1272D',      // errors and stop-work states
  white: '#FFFFFF',
};

const light = {
  background: palette.concrete,
  surface: palette.white,
  text: palette.ink,
  muted: palette.steel,
  rule: palette.rule,
  accent: palette.safetyYellow,
  onAccent: palette.ink,
  ok: palette.signalGreen,
  danger: palette.stopRed,
};

const dark: typeof light = {
  background: '#141B22',
  surface: '#1E2730',
  text: '#EEF1F3',
  muted: '#9AA6B1',
  rule: '#33404C',
  accent: palette.safetyYellow,
  onAccent: palette.ink,
  ok: '#3DB57A',
  danger: '#E5585D',
};

export type Theme = typeof light;

export const themes = { light, dark };

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? dark : light;
}

/** Barlow Condensed for signage-style headings, Barlow for reading. */
export const fonts = {
  display: 'BarlowCondensed_700Bold',
  displayMedium: 'BarlowCondensed_600SemiBold',
  body: 'Barlow_400Regular',
  bodyMedium: 'Barlow_500Medium',
  bodyBold: 'Barlow_600SemiBold',
};

export const space = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 };
