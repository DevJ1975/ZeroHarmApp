import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { MondayMinuteLogo } from '@/components/MondayMinuteCard';
import { MondayMinuteView } from '@/components/MondayMinuteView';
import { Body, OfflineNote, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { listMinutes, Minute } from '@/lib/monday';
import { markStale } from '@/lib/saved-first';

/** The first screen in the app: this week's Monday Minute, ready to read, print, sign in and talk over. */
export default function MondayHome() {
  const t = useTheme();
  const [m, setM] = useState<Minute | null | undefined>(undefined);
  const [offline, setOffline] = useState(false);
  const load = useCallback(() => {
    const show = (list: Minute[]) => {
      setM(list[0] ?? null);
      setOffline(false);
    };
    return listMinutes(show, () => setOffline(true)).then((list) => setM(list[0] ?? null));
  }, []);
  useFocusEffect(useCallback(() => void load(), [load]));
  const refresh = useCallback(() => {
    markStale('monday');
    return load();
  }, [load]);

  if (m === undefined)
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  if (m === null)
    return (
      <Screen onRefresh={refresh}>
        <MondayMinuteLogo />
        {offline && <OfflineNote text="No signal. The Monday Minute will show when you're back in range." />}
        <Body>A new 5-minute crew talk lands here every Monday morning. Read it to your crew, print it with a sign-in sheet, or have the crew sign on this phone.</Body>
        <Body muted>The first Monday Minute arrives Monday at 5 AM Pacific. Turn on Monday Minute in Settings to get a notification.</Body>
        <View style={styles.links}>
          <Link href="/today" style={[styles.link, { color: t.text }]}>Zero Harm Weekly and more →</Link>
          <Link href="/sheets" style={[styles.link, { color: t.text }]}>My sign-in sheets →</Link>
        </View>
      </Screen>
    );
  return (
    <View style={{ flex: 1 }}>
      <MondayMinuteView minute={m} onChange={setM} onRefresh={refresh} offline={offline} />
    </View>
  );
}

const styles = StyleSheet.create({
  links: { gap: space.md, marginTop: space.sm },
  link: { fontFamily: fonts.bodyBold, fontSize: 17 },
});
