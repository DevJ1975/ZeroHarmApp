import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { printPdf, sharePdf, stillOnPhone } from '@/lib/pdf';
import { listKeptSheets, SigninSession } from '@/lib/signins';

type Kept = SigninSession & { signed: number };

/** Every sign-in sheet kept on this phone: print it again or email it any time, even with no signal. */
export default function SheetsScreen() {
  const t = useTheme();
  const [sheets, setSheets] = useState<Kept[] | null>(null);
  useFocusEffect(useCallback(() => void listKeptSheets().then((s) => setSheets(s.filter((x) => stillOnPhone(x.pdf_path)))), []));

  return (
    <Screen>
      <Body muted>Sheets stay in the app on this phone. Deleting the app deletes them, so save important ones to your records or email them.</Body>
      {sheets === null && <ActivityIndicator />}
      {sheets?.length === 0 && <Body muted>No sheets yet. Print, share or save a sign-in sheet and it shows up here.</Body>}
      {sheets?.map((s) => (
        <View key={s.id} style={[styles.row, { borderColor: t.rule }]}>
          <Text style={[styles.meta, { color: t.muted }]}>
            {s.program === 'mm' ? 'Monday Minute' : 'Zero Harm Weekly'} · {new Date(`${s.created_at.replace(' ', 'T')}Z`).toLocaleDateString()}
          </Text>
          <Text style={[styles.title, { color: t.text }]}>{s.title ?? 'Toolbox talk'}</Text>
          <Text style={[styles.meta, { color: t.muted }]}>
            {Math.max(s.signed, s.photo_count ?? 0)} attended{s.group_photo ? ' · group photo' : ''}{s.location ? ` · ${s.location}` : ''}
          </Text>
          <View style={styles.actions}>
            <View style={{ flex: 1 }}><Button kind="secondary" label="Print" onPress={() => printPdf(s.pdf_path!)} /></View>
            <View style={{ flex: 1 }}><Button kind="secondary" label="Email or share" onPress={() => sharePdf(s.pdf_path!, 'Email or share the sign-in sheet')} /></View>
          </View>
        </View>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { borderBottomWidth: 1, paddingVertical: space.md, gap: 4 },
  meta: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  title: { fontFamily: fonts.displayMedium, fontSize: 20, lineHeight: 24 },
  actions: { flexDirection: 'row', gap: space.sm, marginTop: space.xs },
});
