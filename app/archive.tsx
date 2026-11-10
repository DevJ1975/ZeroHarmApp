import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Field, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { arrangeTalks, issueNumber, listTalks, Talk, isEarly } from '@/lib/talks';

const fmt = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });

/** Every toolbox talk in the app, past and ready early: search by words, filter by month theme. */
export default function ArchiveScreen() {
  const t = useTheme();
  const params = useLocalSearchParams<{ theme?: string }>();
  const [talks, setTalks] = useState<Talk[] | null>(null);
  const [q, setQ] = useState('');
  const [theme, setTheme] = useState<string | null>(params.theme ?? null);

  useFocusEffect(useCallback(() => void listTalks((r) => setTalks(r.talks)).then((r) => setTalks(r.talks)), []));

  const themes = useMemo(() => [...new Set((talks ?? []).map((x) => x.month_theme).filter(Boolean))], [talks]);
  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return (talks ?? []).filter((x) => {
      if (theme && x.month_theme.toLowerCase() !== theme.toLowerCase()) return false;
      const hay = `${x.title} ${x.story_title} ${x.crew_question} ${x.month_theme} ${x.body_md ?? ''}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    });
  }, [talks, q, theme]);
  const groups = useMemo(() => {
    const { current, past, early } = arrangeTalks(shown);
    const sent = current && !isEarly(current) ? [current, ...past] : past;
    const ahead = current && isEarly(current) ? [current, ...early] : early;
    return [
      { label: 'Ready early', talks: ahead },
      { label: 'Past talks', talks: sent },
    ].filter((g) => g.talks.length > 0);
  }, [shown]);

  return (
    <Screen>
      <Field label="Search toolbox talks" value={q} onChangeText={setQ} placeholder="Ladder, lockout, heat…" returnKeyType="search" />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
        {[null, ...themes].map((th) => {
          const on = theme === th;
          return (
            <Pressable
              key={th ?? 'all'}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              onPress={() => setTheme(th)}
              style={[styles.chip, { borderColor: t.text, backgroundColor: on ? t.text : 'transparent' }]}>
              <Text style={[styles.chipText, { color: on ? t.background : t.text }]}>{th ?? 'All'}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
      {talks === null && <ActivityIndicator />}
      {talks !== null && shown.length === 0 && (
        <Body muted>{talks.length ? 'No talks match. Try a different word or theme.' : 'Toolbox talks appear here as soon as they are ready.'}</Body>
      )}
      {groups.map((g) => (
        <View key={g.label} style={{ gap: 0 }}>
          {groups.length > 1 && <Text style={[styles.section, { color: t.text }]} accessibilityRole="header">{g.label}</Text>}
          {g.talks.map((x) => (
            <Pressable
              key={x.issue}
              accessibilityRole="button"
              onPress={() => router.push(`/talk/${x.issue}`)}
              style={[styles.row, { borderColor: t.rule }]}>
              <Text style={[styles.meta, { color: t.muted }]}>
                Issue {issueNumber(x)} · {fmt(x.issue_date)} · {x.month_theme}
              </Text>
              <Text style={[styles.title, { color: t.text }]}>{x.title}</Text>
            </Pressable>
          ))}
        </View>
      ))}
      <View style={{ marginTop: space.md }}>
        <Button kind="secondary" label="Suggest a toolbox talk" onPress={() => router.push('/suggest')} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  chip: { borderWidth: 1.5, borderRadius: 999, paddingHorizontal: 14, minHeight: 40, justifyContent: 'center' },
  chipText: { fontFamily: fonts.bodyBold, fontSize: 15 },
  row: { borderBottomWidth: 1, paddingVertical: 12, gap: 2 },
  meta: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  title: { fontFamily: fonts.displayMedium, fontSize: 20, lineHeight: 24 },
  section: { fontFamily: fonts.displayMedium, fontSize: 22, marginTop: space.sm },
});
