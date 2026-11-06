import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Body, ComingSoon, Field, Heading, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';

const num = (s: string) => Number(s.replace(/,/g, ''));

/** TRIR and DART rates use OSHA's 200,000-hour base (100 full-time workers for a year). */
export default function ToolsScreen() {
  const t = useTheme();
  const [hours, setHours] = useState('');
  const [recordables, setRecordables] = useState('');
  const [dart, setDart] = useState('');

  const h = num(hours);
  const ready = h > 0;
  const rate = (cases: string) => (ready && cases !== '' ? ((num(cases) * 200000) / h).toFixed(2) : '–');

  return (
    <Screen>
      <Heading>Tools</Heading>

      <View style={[styles.card, { backgroundColor: t.surface, borderColor: t.rule }]}>
        <Text style={[styles.cardTitle, { color: t.text }]}>Injury rate calculator</Text>
        <Field label="Total hours worked this year" value={hours} onChangeText={setHours} keyboardType="number-pad" placeholder="e.g. 410,000" />
        <Field label="Recordable cases (OSHA 300 log)" value={recordables} onChangeText={setRecordables} keyboardType="number-pad" />
        <Field label="Days away, restricted or transferred cases" value={dart} onChangeText={setDart} keyboardType="number-pad" />
        <View style={styles.results}>
          <View style={styles.result}>
            <Text style={[styles.value, { color: t.text }]}>{rate(recordables)}</Text>
            <Body muted>TRIR</Body>
          </View>
          <View style={styles.result}>
            <Text style={[styles.value, { color: t.text }]}>{rate(dart)}</Text>
            <Body muted>DART rate</Body>
          </View>
        </View>
        <Body muted>Cases per 100 full-time workers per year. This is guidance, not a substitute for your recordkeeping professional.</Body>
      </View>

      <ComingSoon title="Is it recordable?" detail="A step-by-step check against OSHA's recordkeeping rule. Arrives in the first update." />
      <ComingSoon title="Heat stress planner" detail="Live heat index with water, rest and shade guidance. Planned for May." />
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: 6, padding: space.md, gap: space.md },
  cardTitle: { fontFamily: fonts.displayMedium, fontSize: 22 },
  results: { flexDirection: 'row', gap: space.lg },
  result: { flex: 1 },
  value: { fontFamily: fonts.display, fontSize: 40 },
});
