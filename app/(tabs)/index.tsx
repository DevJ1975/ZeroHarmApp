import { Link, router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { AnimatedOtis } from '@/components/AnimatedOtis';
import { HolidayBanner, HolidayTagline } from '@/components/Holiday';
import { MondayMinuteLogo } from '@/components/MondayMinuteCard';
import { MondayMinuteView } from '@/components/MondayMinuteView';
import { Body, OfflineNote, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { useContentRefresh } from '@/lib/live';
import { listMinutes, Minute } from '@/lib/monday';
import { markStale } from '@/lib/saved-first';
import { useHoliday } from '@/lib/season';

/** The first screen in the app: this week's Monday Minute, ready to read, print, sign in and talk over. */
export default function MondayHome() {
  const t = useTheme();
  const festive = useHoliday();
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
  useContentRefresh(refresh); // a Minute published or pulled while this screen is open

  if (m === undefined)
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  if (m === null)
    return (
      <View style={{ flex: 1 }}>
      <Screen onRefresh={refresh}>
        {festive ? (
          <HolidayBanner>
            <MondayMinuteLogo onDark />
            <HolidayTagline />
          </HolidayBanner>
        ) : (
          <MondayMinuteLogo />
        )}
        {offline && <OfflineNote text="No signal. The Monday Minute will show when you're back in range." />}
        <Body>A new 5-minute crew talk lands here every Monday morning. Read it to your crew, print it with a sign-in sheet, or have the crew sign on this phone.</Body>
        <Body muted>The first Monday Minute arrives Monday at 5 AM Pacific. Turn on Monday Minute in Settings to get a notification.</Body>
        <View style={styles.links}>
          <Link href="/today" style={[styles.link, { color: t.text }]}>Zero Harm Weekly and more →</Link>
          <Link href="/sheets" style={[styles.link, { color: t.text }]}>My sign-in sheets →</Link>
          <Link href="/settings" style={[styles.link, { color: t.text }]}>Settings →</Link>
        </View>
      </Screen>
      <AskOtis />
      </View>
    );
  return (
    <View style={{ flex: 1 }}>
      <MondayMinuteView minute={m} onChange={setM} onRefresh={refresh} offline={offline} />
      <AskOtis />
    </View>
  );
}

/** OTIS floats in the corner of the Monday screen, smiling. A tap opens the safety assistant. */
function AskOtis() {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Ask OTIS, the Zero Harm safety assistant"
      onPress={() => router.push('/otis')}
      hitSlop={8}
      style={styles.otis}>
      <AnimatedOtis size={68} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  links: { gap: space.md, marginTop: space.sm },
  link: { fontFamily: fonts.bodyBold, fontSize: 17 },
  otis: { position: 'absolute', right: space.md, bottom: space.md, borderRadius: 34, shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 6 },
});
