import { router } from 'expo-router';
import { Image, Pressable, StyleSheet, Text, View, useColorScheme } from 'react-native';

import { Body } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { useHoliday } from '@/lib/season';
import { Minute, weekLabel } from '@/lib/monday';

/** Monday Minute orange for marks, borders and fills. Too light for small text on a light background. */
export const MM_ORANGE = '#FF6A13';

/** Orange that stays readable as text: darker on light backgrounds (5:1), brighter on dark ones. */
export function useMmTextColor() {
  const dark = useColorScheme() === 'dark';
  // Holiday look: evergreen (mint on dark) in place of orange for the small print and the numbers.
  if (useHoliday()) return dark ? '#7FD1A6' : '#1F6B4A';
  return dark ? '#FF8A45' : '#A84300';
}

/** The border around "Ask your crew" and the takeaway: orange all year, evergreen over the holidays. */
export function useMmBorderColor() {
  const dark = useColorScheme() === 'dark';
  return useHoliday() ? (dark ? '#7FD1A6' : '#1F6B4A') : MM_ORANGE;
}

/** The Monday Minute lockup, light or dark to match the theme. */
export function MondayMinuteLogo({ height = 44, onDark = false }: { height?: number; onDark?: boolean }) {
  const dark = useColorScheme() === 'dark' || onDark;
  return (
    <Image
      source={dark ? require('@/assets/images/monday-minute-lockup-dark.png') : require('@/assets/images/monday-minute-lockup.png')}
      style={{ height, width: height * 3.2 }}
      resizeMode="contain"
      accessibilityLabel="Monday Minute"
    />
  );
}

/** This week's Monday Minute on the Today screen. */
export function MondayMinuteCard({ minute }: { minute: Minute }) {
  const t = useTheme();
  const mmText = useMmTextColor();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Monday Minute: ${minute.title}`}
      onPress={() => router.push(`/monday/${minute.id}`)}
      style={[styles.card, { borderColor: MM_ORANGE, backgroundColor: t.surface }]}>
      <View style={styles.top}>
        <Image source={require('@/assets/images/monday-minute-mark.png')} style={styles.mark} accessibilityIgnoresInvertColors />
        <View style={{ flex: 1 }}>
          <Text style={[styles.kicker, { color: mmText }]}>MONDAY MINUTE · {weekLabel(minute).toUpperCase()}</Text>
          <Text style={[styles.title, { color: t.text }]}>{minute.title}</Text>
        </View>
      </View>
      <Body muted>{minute.crew_question}</Body>
      <Text style={[styles.meta, { color: t.muted }]}>
        👍 {minute.thumbs_up} · 👎 {minute.thumbs_down} · 💬 {minute.comment_count} {minute.comment_count === 1 ? 'comment' : 'comments'}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 3, borderRadius: 8, padding: space.md, gap: space.sm },
  top: { flexDirection: 'row', gap: space.md, alignItems: 'center' },
  mark: { width: 56, height: 56 },
  kicker: { fontFamily: fonts.displayMedium, fontSize: 14, letterSpacing: 0.5 },
  title: { fontFamily: fonts.display, fontSize: 26, lineHeight: 28 },
  meta: { fontFamily: fonts.bodyMedium, fontSize: 14 },
});
