import { Link, router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { Body, Button, ComingSoon, Heading, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { AlertCard } from '@/components/feed';
import { EpisodeCard } from '@/components/EpisodeCard';
import { WeatherBar } from '@/components/WeatherBar';
import { Episode, listEpisodes } from '@/lib/episodes';
import { FeedItem, listFeed } from '@/lib/feed';
import { arrangeTalks, issueNumber, listTalks, sendDay, Talk } from '@/lib/talks';

/** Today: this week's talk as a safety placard, talks ready early, then past talks. */
export default function TodayScreen() {
  const t = useTheme();
  const [talks, setTalks] = useState<Talk[] | null>(null);
  const [offline, setOffline] = useState(false);
  const [alerts, setAlerts] = useState<FeedItem[]>([]);
  const [episodes, setEpisodes] = useState<Episode[]>([]);

  useFocusEffect(
    useCallback(() => {
      const show = (r: { talks: Talk[]; offline: boolean }) => {
        setTalks(r.talks);
        setOffline(r.offline);
      };
      listTalks(show).then(show);
      listFeed(['alert'], setAlerts).then(setAlerts);
      listEpisodes(setEpisodes).then(setEpisodes);
    }, []),
  );

  const { current, past, early } = arrangeTalks(talks ?? []);

  return (
    <Screen>
      <View style={styles.topRow}>
        <Heading>Today</Heading>
        <Link href="/settings" style={[styles.link, { color: t.muted }]}>Settings</Link>
      </View>
      <WeatherBar />

      {talks === null && <ActivityIndicator />}

      {talks !== null && !current && (
        <ComingSoon
          title="The first talk lands Sunday, January 3"
          detail="Zero Harm Weekly starts in January. Turn on reminders in Settings and we'll let you know when it's ready for Monday's meeting."
        />
      )}

      {current && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Open this week's talk: ${current.title}`}
          onPress={() => router.push(`/talk/${current.issue}`)}
          style={[styles.placard, { borderColor: t.text, backgroundColor: t.surface }]}>
          <View style={[styles.band, { backgroundColor: t.accent }]}>
            <Text style={[styles.bandText, { color: t.onAccent }]}>{current.early ? 'Ready early' : 'This week’s talk'}</Text>
            <Text style={[styles.bandText, { color: t.onAccent }]}>Issue {issueNumber(current)}</Text>
          </View>
          <View style={styles.placardBody}>
            <Text style={[styles.title, { color: t.text }]}>{current.title}</Text>
            <Body muted>{current.month_theme}</Body>
            {current.early && <Body muted>The newsletter goes out {sendDay(current)}. You can run it with your crew now.</Body>}
            <Body>{current.crew_question}</Body>
            <Button label="Open the talk" onPress={() => router.push(`/talk/${current.issue}`)} />
          </View>
        </Pressable>
      )}

      {alerts.length > 0 && (
        <View style={{ gap: space.sm }}>
          <View style={styles.topRow}>
            <Text style={[styles.section, { color: t.text }]}>Latest alert</Text>
            <Link href="/alerts" style={[styles.link, { color: t.muted }]}>All alerts</Link>
          </View>
          <AlertCard item={alerts[0]} />
        </View>
      )}

      {episodes.length > 0 && (
        <View style={{ gap: space.sm }}>
          <View style={styles.topRow}>
            <Text style={[styles.section, { color: t.text }]}>Zero Hour</Text>
            <Link href="/zero-hour" style={[styles.link, { color: t.muted }]}>All episodes</Link>
          </View>
          <EpisodeCard ep={episodes[0]} compact />
        </View>
      )}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Ask OTIS, the Zero Harm safety assistant"
        onPress={() => router.push('/otis')}
        style={[styles.otis, { backgroundColor: t.surface, borderColor: t.rule }]}>
        <Text style={[styles.otisTitle, { color: t.text }]}>Ask OTIS</Text>
        <Body muted>Safety questions answered from Zero Harm talks and OSHA General Industry rules. Works with no signal.</Body>
      </Pressable>

      {offline && talks !== null && <Body muted>No signal. Showing the talks saved on this phone.</Body>}

      {early.length > 0 && (
        <View style={{ gap: space.sm }}>
          <View style={styles.topRow}>
            <Text style={[styles.section, { color: t.text }]}>Ready early</Text>
            <Link href="/archive" style={[styles.link, { color: t.muted }]}>All talks</Link>
          </View>
          <Body muted>Upcoming talks you can run with crew sign-in before the newsletter sends.</Body>
          {early.slice(0, 3).map((p) => (
            <Pressable
              key={p.issue}
              accessibilityRole="button"
              accessibilityLabel={`Issue ${issueNumber(p)}: ${p.title}`}
              onPress={() => router.push(`/talk/${p.issue}`)}
              style={[styles.row, { borderColor: t.rule }]}>
              <Text style={[styles.rowNum, { color: t.muted }]}>{issueNumber(p)}</Text>
              <Text style={[styles.rowTitle, { color: t.text }]}>{p.title}</Text>
            </Pressable>
          ))}
        </View>
      )}

      {past.length > 0 && (
        <View style={{ gap: space.sm }}>
          <Text style={[styles.section, { color: t.text }]}>Past talks</Text>
          {past.slice(0, 3).map((p) => (
            <Pressable
              key={p.issue}
              accessibilityRole="button"
              onPress={() => router.push(`/talk/${p.issue}`)}
              style={[styles.row, { borderColor: t.rule }]}>
              <Text style={[styles.rowNum, { color: t.muted }]}>{issueNumber(p)}</Text>
              <Text style={[styles.rowTitle, { color: t.text }]}>{p.title}</Text>
            </Pressable>
          ))}
        </View>
      )}
      <View style={styles.links}>
        <Link href="/archive" style={[styles.link, { color: t.text }]}>Open the archive →</Link>
        <Link href="/suggest" style={[styles.link, { color: t.text }]}>Suggest a talk →</Link>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  link: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  placard: { borderWidth: 3, borderRadius: 8, overflow: 'hidden' },
  band: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: space.md, paddingVertical: 10 },
  bandText: { fontFamily: fonts.display, fontSize: 18 },
  placardBody: { padding: space.md, gap: space.sm },
  title: { fontFamily: fonts.display, fontSize: 34, lineHeight: 36 },
  section: { fontFamily: fonts.displayMedium, fontSize: 22, marginTop: space.sm },
  row: { flexDirection: 'row', gap: space.md, paddingVertical: 12, borderBottomWidth: 1 },
  rowNum: { fontFamily: fonts.displayMedium, fontSize: 18, width: 28 },
  otis: { borderWidth: 1, borderRadius: 6, padding: space.md, gap: 2 },
  otisTitle: { fontFamily: fonts.displayMedium, fontSize: 22 },
  links: { flexDirection: 'row', flexWrap: 'wrap', gap: space.lg, paddingVertical: space.sm },
  rowTitle: { fontFamily: fonts.bodyMedium, fontSize: 17, flex: 1 },
});
