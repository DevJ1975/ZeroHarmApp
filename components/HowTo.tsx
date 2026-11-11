/**
 * How to use Zero Harm: four short steps, one per page. Shown once right after the welcome screen, and any time from
 * Settings. The icons are the same ones the tab bar uses, so people can match a step to a tab.
 */
import { StatusBar } from 'expo-status-bar';
import { SymbolView, SymbolViewProps } from 'expo-symbols';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Body, Button, Heading } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';

type Step = { icons: SymbolViewProps['name'][]; title: string; lines: string[] };

export const HOW_TO_STEPS: Step[] = [
  {
    icons: [{ ios: 'stopwatch', android: 'timer', web: 'timer' }],
    title: 'Monday',
    lines: ['A new 5-minute safety talk shows up every Monday.', 'Read it out loud to your crew.'],
  },
  {
    icons: [{ ios: 'signature', android: 'draw', web: 'draw' }],
    title: 'Sign-in',
    lines: ['Your crew signs on this phone or on the printed sheet.', 'Print the sheet or share it as a PDF for your records.'],
  },
  {
    icons: [
      { ios: 'sun.max', android: 'today', web: 'today' },
      { ios: 'wrench.and.screwdriver', android: 'build', web: 'build' },
      { ios: 'book', android: 'menu_book', web: 'menu_book' },
    ],
    title: 'Today, Tools and Learn',
    lines: [
      'Today has the weather for your site and this week’s Zero Harm Weekly talk. Tap Ask OTIS there to ask a safety question.',
      'Tools has calculators.',
      'Learn has short videos.',
    ],
  },
  {
    icons: [{ ios: 'wifi.slash', android: 'wifi_off', web: 'wifi_off' }],
    title: 'No signal, no problem',
    lines: [
      'Talks and sign-in sheets are saved on this phone. Sheets send when you are back in range.',
      'Notifications are off until you turn them on in Settings.',
    ],
  },
];

/**
 * `cover` lays it over the whole app (first run). Without it, it fills the screen it is placed in (from Settings).
 * `covered` is true while the holiday opening screen is still playing on top: nothing here can be tapped or read out.
 */
export function HowTo({ onDone, cover = false, covered = false }: { onDone: () => void; cover?: boolean; covered?: boolean }) {
  const t = useTheme();
  const [at, setAt] = useState(0);
  const step = HOW_TO_STEPS[at];
  const last = at === HOW_TO_STEPS.length - 1;

  return (
    <View
      style={[cover ? [StyleSheet.absoluteFill, styles.cover] : styles.fill, { backgroundColor: t.background }]}
      pointerEvents={covered ? 'none' : 'auto'}
      accessibilityElementsHidden={covered}
      importantForAccessibility={covered ? 'no-hide-descendants' : 'auto'}
      accessibilityViewIsModal={cover && !covered}>
      {cover && !covered && <StatusBar style="auto" />}
      <SafeAreaView edges={cover ? ['top', 'bottom'] : ['bottom']} style={styles.fill}>
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={[styles.count, { color: t.muted }]}>
            HOW TO USE ZERO HARM · STEP {at + 1} OF {HOW_TO_STEPS.length}
          </Text>
          <View style={styles.icons} accessible={false} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
            {step.icons.map((name, i) => (
              <View key={i} style={[styles.icon, { backgroundColor: t.surface, borderColor: t.rule }]}>
                <SymbolView name={name} tintColor={t.text} size={34} />
              </View>
            ))}
          </View>
          <View accessibilityRole="header">
            <Heading>{step.title}</Heading>
          </View>
          {step.lines.map((line) => (
            <Body key={line}>{line}</Body>
          ))}
        </ScrollView>
        <View style={[styles.footer, { borderColor: t.rule }]}>
          <View style={styles.dots} accessible={false} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
            {HOW_TO_STEPS.map((_, i) => (
              <View key={i} style={[styles.dot, { backgroundColor: i === at ? t.text : t.rule }]} />
            ))}
          </View>
          <Button label={last ? 'Done' : 'Next'} onPress={() => (last ? onDone() : setAt(at + 1))} />
          <View style={styles.row}>
            {at > 0 ? (
              <Pressable accessibilityRole="button" onPress={() => setAt(at - 1)} style={styles.link}>
                <Text style={[styles.linkText, { color: t.text }]}>Back</Text>
              </Pressable>
            ) : (
              <View />
            )}
            {!last && (
              <Pressable accessibilityRole="button" accessibilityHint="Closes the how-to" onPress={onDone} style={styles.link}>
                <Text style={[styles.linkText, { color: t.text }]}>Skip</Text>
              </Pressable>
            )}
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  cover: { zIndex: 5, elevation: 5 },
  fill: { flex: 1 },
  content: { padding: space.md, gap: space.md, paddingTop: space.lg, width: '100%', maxWidth: 520, alignSelf: 'center' },
  count: { fontFamily: fonts.bodyBold, fontSize: 13, letterSpacing: 1.2 },
  icons: { flexDirection: 'row', gap: space.sm },
  icon: { width: 64, height: 64, borderRadius: 8, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  footer: { padding: space.md, gap: space.sm, borderTopWidth: 1, width: '100%', maxWidth: 520, alignSelf: 'center' },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: space.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  row: { flexDirection: 'row', justifyContent: 'space-between' },
  link: { minHeight: 44, minWidth: 44, justifyContent: 'center', paddingHorizontal: space.sm },
  linkText: { fontFamily: fonts.bodyMedium, fontSize: 16, textDecorationLine: 'underline' },
});
