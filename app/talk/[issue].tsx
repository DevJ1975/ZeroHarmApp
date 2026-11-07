import { router, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Field, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { getPrefs, hasBeenAsked, markAsked, setPrefs } from '@/lib/push';
import { startSession } from '@/lib/signins';
import { getTalk, issueNumber, Talk } from '@/lib/talks';

/** Labels on this screen in both languages. Talk text comes from the approved translation. */
const L = {
  en: { issue: 'Issue', ask: 'Ask your crew', pdf: 'Open the printable PDF', run: 'Run the talk', start: 'Start crew sign-in', pending: 'The full talk text will appear here. Until then, open the printable PDF below.' },
  es: { issue: 'Número', ask: 'Pregunte a su equipo', pdf: 'Abrir el PDF para imprimir', run: 'Dar la charla', start: 'Registrar asistencia', pending: 'El texto completo aparecerá aquí. Mientras tanto, abra el PDF para imprimir.' },
};

export default function TalkScreen() {
  const t = useTheme();
  const { issue } = useLocalSearchParams<{ issue: string }>();
  const [talk, setTalk] = useState<Talk | null | undefined>(undefined);
  const [supervisor, setSupervisor] = useState('');
  const [location, setLocation] = useState('');
  const [showReminder, setShowReminder] = useState(false);
  const [reminderNote, setReminderNote] = useState('');
  const [lang, setLang] = useState<'en' | 'es'>('en');

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

  const es = lang === 'es' && talk.es ? talk.es : null;
  const text = es ?? { title: talk.title, story_title: talk.story_title, crew_question: talk.crew_question, body_md: talk.body_md ?? '' };
  const l = L[es ? 'es' : 'en'];
  // Paragraphs split on blank lines; a paragraph starting with "## " is a section heading.
  const blocks = (text.body_md ?? '')
    .split(/\n\s*\n/)
    .map((p) => p.replace(/\*\*/g, '').trim())
    .filter(Boolean)
    .map((p) => ({ heading: p.startsWith('#'), text: p.replace(/^#+\s*/, '') }));

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
      {talk.hero_url && (
        <Image
          source={{ uri: talk.hero_url }}
          style={[styles.hero, { backgroundColor: t.surface }]}
          resizeMode="cover"
          accessibilityIgnoresInvertColors
          accessible={false}
        />
      )}
      <View style={styles.bandRow}>
        <View style={[styles.band, { backgroundColor: t.accent }]}>
          <Text style={[styles.bandText, { color: t.onAccent }]}>{l.issue} {issueNumber(talk)} · {talk.month_theme}</Text>
        </View>
        {talk.es && (
          <View style={[styles.toggle, { borderColor: t.text }]} accessibilityRole="radiogroup" accessibilityLabel="Language">
            {(['en', 'es'] as const).map((code) => (
              <Pressable
                key={code}
                accessibilityRole="radio"
                accessibilityState={{ selected: lang === code }}
                accessibilityLabel={code === 'en' ? 'English' : 'Español'}
                onPress={() => setLang(code)}
                style={[styles.toggleBtn, { backgroundColor: lang === code ? t.text : 'transparent' }]}>
                <Text style={[styles.toggleText, { color: lang === code ? t.background : t.text }]}>{code === 'en' ? 'English' : 'Español'}</Text>
              </Pressable>
            ))}
          </View>
        )}
      </View>
      <Text style={[styles.title, { color: t.text }]}>{text.title}</Text>
      <Text style={[styles.story, { color: t.muted }]}>{text.story_title}</Text>

      {blocks.length > 0 ? (
        blocks.map((b, i) =>
          b.heading ? (
            <Text key={i} style={[styles.h2, { color: t.text }]} accessibilityRole="header">{b.text}</Text>
          ) : (
            <Body key={i}>{b.text}</Body>
          ),
        )
      ) : (
        <Body muted>{l.pending}</Body>
      )}

      <View style={[styles.question, { borderColor: t.text }]}>
        <Text style={[styles.qLabel, { color: t.text }]}>{l.ask}</Text>
        <Body>{text.crew_question}</Body>
      </View>

      {talk.pdf_url && (
        <Button kind="secondary" label={l.pdf} onPress={() => WebBrowser.openBrowserAsync(talk.pdf_url!)} />
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

      <Text style={[styles.section, { color: t.text }]}>{l.run}</Text>
      <Field label="Supervisor" value={supervisor} onChangeText={setSupervisor} placeholder="Your name" autoCapitalize="words" />
      <Field label="Location" value={location} onChangeText={setLocation} placeholder="Line, dock or shop" />
      <Button label={l.start} onPress={begin} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { width: '100%', aspectRatio: 16 / 9, borderRadius: 6 },
  bandRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  toggle: { flexDirection: 'row', borderWidth: 2, borderRadius: 6, overflow: 'hidden' },
  toggleBtn: { paddingHorizontal: 12, minHeight: 44, justifyContent: 'center' },
  toggleText: { fontFamily: fonts.bodyBold, fontSize: 15 },
  h2: { fontFamily: fonts.displayMedium, fontSize: 22, marginTop: space.sm },
  band: { paddingHorizontal: space.md, paddingVertical: 8, borderRadius: 4, alignSelf: 'flex-start' },
  bandText: { fontFamily: fonts.displayMedium, fontSize: 16 },
  title: { fontFamily: fonts.display, fontSize: 34, lineHeight: 37 },
  story: { fontFamily: fonts.bodyMedium, fontSize: 18 },
  question: { borderLeftWidth: 5, paddingLeft: space.md, paddingVertical: space.xs, gap: space.xs },
  qLabel: { fontFamily: fonts.displayMedium, fontSize: 20 },
  reminder: { borderWidth: 1, borderRadius: 6, padding: space.md, gap: space.sm },
  section: { fontFamily: fonts.displayMedium, fontSize: 24, marginTop: space.md },
});
