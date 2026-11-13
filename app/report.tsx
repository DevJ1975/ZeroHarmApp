import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, Switch, Text, View } from 'react-native';

import { Body, Button, Field, Heading, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { getAccount } from '@/lib/account';
import { looksSpanish } from '@/lib/otis/prompt';
import { getProfile, tidyEmail, validEmail } from '@/lib/profile';
import { deviceInfo } from '@/lib/support/device';
import { flowSent, whatIsSent } from '@/lib/support/flow';
import { BEFORE_SENDING, fileReport, longEnough, REPORT_MAX, whyNotSent } from '@/lib/support/reports';

/**
 * Report a problem with the app. A plain form that never needs OTIS, so it works when OTIS is off, still downloading
 * or broken. The report is saved on the phone first and sent when there is a signal, so it also works in a dead spot.
 * Only what is on this screen is sent, plus the phone model, system version, app version and random id named in the
 * line under the button.
 */
export default function ReportScreen() {
  const t = useTheme();
  const [text, setText] = useState('');
  const [email, setEmail] = useState('');
  const [reply, setReply] = useState(false);
  const [errors, setErrors] = useState<{ text?: string; email?: string }>({});
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState('');
  const [done, setDone] = useState('');

  // An email already on this phone saves typing. It is only sent if the person turns on "OK to reply to me".
  useEffect(() => {
    Promise.all([getAccount(), getProfile()])
      .then(([a, p]) => setEmail((typed) => typed || (a.state === 'in' ? a.email : p.email)))
      .catch(() => {});
  }, []);

  async function send() {
    const next: typeof errors = {};
    if (!longEnough(text)) next.text = 'Tell us what happened in a few words.';
    if (reply && !validEmail(email)) next.email = 'Check the email address, or turn off OK to reply to me.';
    setErrors(next);
    if (next.text || next.email) return;
    setFailed('');
    setSending(true);
    try {
      const filed = await fileReport({
        text,
        source: 'form',
        lang: looksSpanish(text) ? 'es' : 'en',
        ...(reply ? { email: tidyEmail(email), may_contact: true } : {}),
      });
      // Turned down for good: keep what they typed on screen so it is not lost.
      if (filed.failed) setFailed(whyNotSent('en', filed) ?? flowSent('en', filed));
      else setDone(flowSent('en', filed));
    } catch {
      setFailed('That report could not be sent. Try again later.');
    } finally {
      setSending(false);
    }
  }

  if (done !== '')
    return (
      <Screen>
        <Heading>Thank you</Heading>
        <View accessibilityRole="alert">
          <Body>{done}</Body>
        </View>
        <Body muted>A person at Trainovate reads every report. Look under My reports for a reply.</Body>
        {/* replace, not push: the report is sent, so Back should not land on the form again */}
        <Button label="My reports" onPress={() => router.replace('/my-reports')} />
        <Button
          kind="secondary"
          label="Report another problem"
          onPress={() => {
            setText('');
            setDone('');
          }}
        />
      </Screen>
    );

  return (
    <Screen>
      <Body>Tell us what went wrong with the app. A person at Trainovate reads every report.</Body>
      <Body muted>{BEFORE_SENDING.en}</Body>
      <Field
        label="What happened?"
        value={text}
        onChangeText={setText}
        error={errors.text}
        multiline
        maxLength={REPORT_MAX}
        style={{ minHeight: 130, textAlignVertical: 'top' }}
        placeholder="Example: the app closed when I opened a talk. Leave out names."
      />
      <Field
        label="Email (optional)"
        value={email}
        onChangeText={(v) => {
          setEmail(v);
          setReply(v.trim() !== ''); // typing an address here means they want a reply; the switch below shows it and can undo it
        }}
        error={errors.email}
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
      />
      <View style={[styles.row, { borderColor: t.rule, opacity: email.trim() ? 1 : 0.5 }]}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={[styles.rowLabel, { color: t.text }]}>OK to reply to me</Text>
          <Body muted>{reply ? 'On: your email is sent with the report.' : 'Off: your email is not sent.'}</Body>
        </View>
        <Switch accessibilityLabel="OK to reply to me" value={reply} onValueChange={setReply} disabled={!email.trim()} trackColor={{ true: t.accent }} />
      </View>
      {failed !== '' && (
        <View accessibilityRole="alert">
          <Body>{failed}</Body>
        </View>
      )}
      <Button label="Send report" onPress={send} busy={sending} />
      <Body muted>{whatIsSent('en', deviceInfo())}</Body>
      <Button kind="secondary" label="My reports" onPress={() => router.push('/my-reports')} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.sm, borderBottomWidth: 1 },
  rowLabel: { fontFamily: fonts.bodyBold, fontSize: 17 },
});
