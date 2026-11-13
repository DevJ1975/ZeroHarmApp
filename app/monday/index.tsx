import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { MondayMinuteLogo } from '@/components/MondayMinuteCard';
import { Body, Screen } from '@/components/ui';
import { fonts, useTheme } from '@/constants/theme';
import { listMinutes, Minute, weekLabel } from '@/lib/monday';

/** Every published Monday Minute, newest first. */
export default function MondayList() {
  const t = useTheme();
  const [list, setList] = useState<Minute[] | null>(null);
  useFocusEffect(useCallback(() => void listMinutes(setList).then(setList), []));
  return (
    <Screen>
      <MondayMinuteLogo />
      <Body muted>A new 5-minute crew talk every Monday morning, with sign-in. Rate it and talk it over with other crews.</Body>
      {list === null && <ActivityIndicator />}
      {list?.length === 0 && <Body muted>The first Monday Minute arrives Monday morning.</Body>}
      {list?.map((m) => (
        <Pressable key={m.id} accessibilityRole="button" onPress={() => router.push(`/monday/${m.id}`)} style={[styles.row, { borderColor: t.rule }]}>
          <Text style={[styles.meta, { color: t.muted }]}>Week of {weekLabel(m)} · {m.category}</Text>
          <Text style={[styles.title, { color: t.text }]}>{m.title}</Text>
          <Text style={[styles.meta, { color: t.muted }]}>👍 {m.thumbs_up} · 👎 {m.thumbs_down} · 💬 {m.comment_count}</Text>
        </Pressable>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { borderBottomWidth: 1, paddingVertical: 12, gap: 2 },
  meta: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  title: { fontFamily: fonts.displayMedium, fontSize: 20, lineHeight: 24 },
});
