import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { flushReports, myReports, savedReports, type Report } from '@/lib/support/reports';

/** The status in plain words. Always shown as text, so nothing depends on a colour. */
const STATUS: Record<Report['status'], string> = {
  queued: 'Waiting to send',
  failed: 'Could not be sent',
  new: 'Received',
  in_progress: 'Being looked at',
  fixed: 'Fixed',
  closed: 'Closed',
};

const day = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });
};

/**
 * The problem reports made from this phone: where each one stands, and what Trainovate wrote back. The list saved on
 * the phone is drawn at once, so the screen is never blank in a dead spot; the server's list replaces it when it lands.
 */
export default function MyReportsScreen() {
  const t = useTheme();
  const [reports, setReports] = useState<Report[] | null>(null);

  const load = useCallback(async () => {
    setReports(await savedReports());
    await flushReports(); // a report made with no signal goes out now, so it shows with its number
    setReports(await myReports());
  }, []);
  useFocusEffect(useCallback(() => void load().catch(() => setReports((r) => r ?? [])), [load]));

  const waiting = reports?.some((r) => r.status === 'queued') ?? false;

  return (
    <Screen onRefresh={load}>
      <Body muted>Reports you sent from this phone. A reply from Trainovate shows up here.</Body>
      {reports === null && <ActivityIndicator />}
      {reports?.length === 0 && <Body muted>No reports yet. If something in the app goes wrong, tell us.</Body>}
      {waiting && (
        <View accessibilityRole="alert" style={[styles.note, { borderColor: t.rule, backgroundColor: t.surface }]}>
          <Text style={[styles.meta, { color: t.muted }]}>A report is saved on this phone. It will send when you have signal.</Text>
        </View>
      )}
      {reports?.map((r) => (
        <View key={r.ref} style={[styles.row, { borderColor: t.rule }]}>
          <Text style={[styles.meta, { color: t.muted }]}>{[r.number ?? (r.status === 'failed' ? 'Not sent' : 'Not sent yet'), day(r.created_at)].filter(Boolean).join(' · ')}</Text>
          <Text style={[styles.title, { color: t.text }]}>{r.title || 'Problem report'}</Text>
          <Text style={[styles.status, { color: t.text }]}>Status: {STATUS[r.status] ?? STATUS.new}</Text>
          {r.status === 'failed' && <Body muted>Trainovate did not get this report. If the problem is still there, report it again.</Body>}
          {!!r.reply && (
            <View style={[styles.reply, { borderColor: t.rule, backgroundColor: t.surface }]}>
              <Text style={[styles.meta, { color: t.muted }]}>Reply from Trainovate</Text>
              <Body>{r.reply}</Body>
            </View>
          )}
        </View>
      ))}
      <Button kind={reports?.length ? 'secondary' : 'primary'} label="Report a problem" onPress={() => router.push('/report')} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  note: { borderWidth: 1, borderRadius: 6, paddingVertical: 8, paddingHorizontal: 12 },
  row: { borderBottomWidth: 1, paddingBottom: space.md, gap: 4 },
  meta: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  title: { fontFamily: fonts.displayMedium, fontSize: 20, lineHeight: 24 },
  status: { fontFamily: fonts.bodyBold, fontSize: 16 },
  reply: { borderWidth: 1, borderRadius: 6, padding: space.sm, gap: 2, marginTop: space.xs },
});
