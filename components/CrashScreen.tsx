/**
 * What a person sees when the app's own code throws while drawing a screen. It takes the place of the stock
 * "Something went wrong" page: it saves a crash report (unless crash reports are off in Settings), lets the person
 * try again, and lets them tell us what happened without leaving the screen.
 *
 * It has to stand on its own. When the whole app has fallen over it is drawn above the navigator, so there is nothing
 * to navigate to, and the fonts may be the very thing that failed to load. So: no Link, no router, none of the shared
 * components, the phone's own font, and the report form is right here instead of on the Report a problem screen.
 * The same screen is used when just one screen fails; then the header and its back button are still above it.
 */
import type { ErrorBoundaryProps } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, AppState, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { space, useTheme } from '@/constants/theme';
import { tidyEmail, validEmail } from '@/lib/profile';
import { CRASH_REPORT_HOLDS, crashReportsOn, flushCrashes, recordError } from '@/lib/support/crash';
import { deviceInfo } from '@/lib/support/device';
import { flowSent, whatIsSent } from '@/lib/support/flow';
import { BEFORE_SENDING, fileReport, flushReports, longEnough, REPORT_MAX, whyNotSent } from '@/lib/support/reports';

export function CrashScreen({ error, retry }: ErrorBoundaryProps) {
  const t = useTheme();
  // Read once: the line below must say what really happened to this error, not what the switch says later.
  const [saved] = useState(() => Platform.OS !== 'web' && crashReportsOn());
  const [view, setView] = useState<'error' | 'form' | 'sent'>('error');
  const [text, setText] = useState('');
  const [email, setEmail] = useState('');
  const [problem, setProblem] = useState('');
  const [sending, setSending] = useState(false);
  const [sentLine, setSentLine] = useState('');

  // The same error again (Try again that fails the same way) is dropped by recordError itself. Sent from here, not
  // only from the layout: when the whole app has fallen over, the layout is not there to send anything.
  useEffect(() => {
    recordError(error, { fatal: true });
    void flushCrashes();
  }, [error]);

  // While this screen is up, reports saved with no signal still go out when the app comes back to the front, as
  // "It will send when you have signal" promises.
  useEffect(() => {
    void flushReports();
    const sub = AppState.addEventListener('change', (state) => {
      if (state !== 'active') return;
      void flushCrashes();
      void flushReports();
    });
    return () => sub.remove();
  }, []);

  async function send() {
    if (sending) return;
    if (!longEnough(text)) return setProblem('Tell us what happened in a few words.');
    if (email.trim() && !validEmail(email)) return setProblem('Check the email address, or leave it blank.');
    setProblem('');
    setSending(true);
    try {
      // Typing an email here is the answer to "if you want a reply", so it is fine to write back to it.
      const filed = await fileReport({ text, source: 'form', ...(email.trim() ? { email: tidyEmail(email), may_contact: true } : {}) });
      if (filed.failed) return setProblem(whyNotSent('en', filed) ?? flowSent('en', filed));
      setSentLine(flowSent('en', filed));
      setView('sent');
    } catch {
      setProblem('That report could not be sent. Try again later.');
    } finally {
      setSending(false);
    }
  }

  const button = (label: string, onPress: () => void, primary = false, busy = false) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: busy, busy }}
      disabled={busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: primary ? t.accent : 'transparent', borderColor: primary ? t.accent : t.text, opacity: pressed ? 0.75 : 1 },
      ]}>
      {busy ? <ActivityIndicator color={primary ? t.onAccent : t.text} /> : <Text style={[styles.buttonText, { color: primary ? t.onAccent : t.text }]}>{label}</Text>}
    </Pressable>
  );

  const field = { color: t.text, borderColor: t.rule, backgroundColor: t.surface };

  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: t.background }]}>
      <ScrollView keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets contentContainerStyle={styles.content}>
        <Text accessibilityRole="header" style={[styles.title, { color: t.text }]}>
          Something went wrong
        </Text>

        {view === 'error' && (
          <>
            <Text style={[styles.body, { color: t.text }]}>
              {saved
                ? `The app hit an error. It saved a short report for Trainovate with ${CRASH_REPORT_HOLDS}. It is built to leave out what you typed, your name and your email.`
                : 'The app hit an error. Crash reports are off, so no report was saved.'}
            </Text>
            <Text style={[styles.body, { color: t.muted }]}>If it keeps happening, close the app and open it again.</Text>
            {button('Try again', () => void retry(), true)}
            {button('Report this problem', () => setView('form'))}
          </>
        )}

        {view === 'form' && (
          <>
            <Text style={[styles.label, { color: t.muted }]}>What were you doing when this happened?</Text>
            <TextInput
              accessibilityLabel="What were you doing when this happened?"
              value={text}
              onChangeText={setText}
              multiline
              maxLength={REPORT_MAX}
              placeholder="Leave out names."
              placeholderTextColor={t.muted}
              style={[styles.input, styles.tall, field]}
            />
            <Text style={[styles.label, { color: t.muted }]}>Email, if you want a reply (optional)</Text>
            <TextInput
              accessibilityLabel="Email, if you want a reply (optional)"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              placeholderTextColor={t.muted}
              style={[styles.input, field]}
            />
            {problem !== '' && (
              <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.body, { color: t.danger }]}>
                {problem}
              </Text>
            )}
            <Text style={[styles.note, { color: t.muted }]}>{BEFORE_SENDING.en}</Text>
            {button('Send report', send, true, sending)}
            {button('Cancel', () => setView('error'))}
            <Text style={[styles.note, { color: t.muted }]}>{whatIsSent('en', deviceInfo())}</Text>
          </>
        )}

        {view === 'sent' && (
          <>
            <View accessibilityRole="alert">
              <Text style={[styles.body, { color: t.text }]}>{sentLine}</Text>
            </View>
            {button('Try again', () => void retry(), true)}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

// No custom font names here: this screen also shows when the fonts did not load.
const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { padding: space.md, gap: space.md },
  title: { fontSize: 28, lineHeight: 34, fontWeight: '700' },
  body: { fontSize: 17, lineHeight: 25 },
  label: { fontSize: 14, fontWeight: '500' },
  note: { fontSize: 14, lineHeight: 20 },
  input: { fontSize: 17, borderWidth: 1, borderRadius: 6, padding: 12 },
  tall: { minHeight: 110, textAlignVertical: 'top' },
  button: { borderWidth: 2, borderRadius: 6, paddingVertical: 14, paddingHorizontal: 18, alignItems: 'center' },
  buttonText: { fontSize: 17, fontWeight: '600' },
});
