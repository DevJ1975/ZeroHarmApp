import { router, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Field, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { getPrefs, hasBeenAsked, markAsked, setPrefs } from '@/lib/push';
import { startSession } from '@/lib/signins';
import { getTalk, Talk } from '@/lib/talks';

export default function TalkScreen() {
  const t = useTheme();
  const { issue } = useLocalSearchParams<{ issue: string }>();
  const [talk, setTalk] = useState<Talk | null | undefined>(undefined);
  const [supervisor, setSupervisor] = useState('');
  const [location, setLocation] = useState('');
  const [showReminder, setShowReminder] = useState(false);
  const [reminderNote, setReminderNote] = useState('');

  useEffect(() => {
    getTalk(Number(issue)).then(setTalk);
    // Ask for push at a good moment: right after someone opens their first talk.
    hasBeenAsked().then((asked) => setShowReminder(!asked));
  }, [issue]);

  if (talk === undefined) return <Screen><ActivityIndicator /></Screen>;
  if (talk === null)
    return (
      <Screen>
        <Body>This talk isn’t available yet. Talks open on the Sunday before their Monday date.</Body>
      </Screen>
    );

  const paragraphs = (talk.body_md ?? '').split(/\n\s*\n/).map((p) => p.replace(/^#+\s*|\*\*/g, '').trim()).filter(Boolean);

  async function begin() {
    const id = await startSession(talk!.issue, supervisor.trim(), location.trim());
    router.push(`/signin/${id}`);
  }

  async function turnOnReminders() {
    const prefs = await getPrefs();
    const { permissionDenied } = await setPrefs({ ...prefs, weeklyTalk: true });
    setReminderNote(
      permissionDenied
        ? 'Notifications are off for Zero Harm. You can turn them on in your phone settings.'
        : "You're set. Next week's talk arrives Sunday around noon Pacific.",
    );
    setShowReminder(false);
  }

  return (
    <Screen>
      <View style={[styles.band, { backgroundColor: t.accent }]}>
        <Text style={[styles.bandText, { color: t.onAccent }]}>Issue {talk.issue} · {talk.month_theme}</Text>
      </View>
      <Text style={[styles.title, { color: t.text }]}>{talk.title}</Text>
      <Text style={[styles.story, { color: t.muted }]}>{talk.story_title}</Text>

      {paragraphs.length > 0 ? (
        paragraphs.map((p, i) => <Body key={i}>{p}</Body>)
      ) : (
        <Body muted>The full talk text will appear here. Until then, open the printable PDF below.</Body>
      )}

      <View style={[styles.question, { borderColor: t.text }]}>
        <Text style={[styles.qLabel, { color: t.text }]}>Ask your crew</Text>
        <Body>{talk.crew_question}</Body>
      </View>

      {talk.pdf_url && (
        <Button kind="secondary" label="Open the printable PDF" onPress={() => WebBrowser.openBrowserAsync(talk.pdf_url!)} />
      )}

      {showReminder && (
        <View style={[styles.reminder, { backgroundColor: t.surface, borderColor: t.rule }]}>
          <Text style={[styles.qLabel, { color: t.text }]}>Get next week’s talk on Sunday?</Text>
          <Body muted>One notification a week, timed for Monday’s meeting. Turn it off anytime in Settings.</Body>
          <Button label="Turn on weekly reminders" onPress={turnOnReminders} />
          <Button kind="secondary" label="Not now" onPress={() => { markAsked(); setShowReminder(false); }} />
        </View>
      )}
      {reminderNote !== '' && <Body muted>{reminderNote}</Body>}

      <Text style={[styles.section, { color: t.text }]}>Run the talk</Text>
      <Field label="Supervisor" value={supervisor} onChangeText={setSupervisor} placeholder="Your name" autoCapitalize="words" />
      <Field label="Location" value={location} onChangeText={setLocation} placeholder="Line, dock or shop" />
      <Button label="Start crew sign-in" onPress={begin} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  band: { paddingHorizontal: space.md, paddingVertical: 8, borderRadius: 4, alignSelf: 'flex-start' },
  bandText: { fontFamily: fonts.displayMedium, fontSize: 16 },
  title: { fontFamily: fonts.display, fontSize: 34, lineHeight: 37 },
  story: { fontFamily: fonts.bodyMedium, fontSize: 18 },
  question: { borderLeftWidth: 5, paddingLeft: space.md, paddingVertical: space.xs, gap: space.xs },
  qLabel: { fontFamily: fonts.displayMedium, fontSize: 20 },
  reminder: { borderWidth: 1, borderRadius: 6, padding: space.md, gap: space.sm },
  section: { fontFamily: fonts.displayMedium, fontSize: 24, marginTop: space.md },
});
