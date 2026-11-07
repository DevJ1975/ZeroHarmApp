import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';

import { Body, Button, Field, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { api, isConfigured } from '@/lib/config';
import { getProfile, validEmail } from '@/lib/profile';

const THEMES = ['Hazardous Energy', 'Chemicals', 'Machine Guarding', 'Respiratory & Eye', 'Falls', 'Heat', 'Forklifts', 'Electrical',
  'Emergency Action', 'Fire Prevention', 'Lifting & Driving', 'Winter Safety', 'Something else'];

/** Crews and supervisors suggest toolbox talk topics; ideas go to the Zero Harm Weekly team in GoHighLevel. */
export default function SuggestScreen() {
  const t = useTheme();
  const [topic, setTopic] = useState('');
  const [details, setDetails] = useState('');
  const [theme, setTheme] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [contact, setContact] = useState(false);
  const [status, setStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [error, setError] = useState('');

  useFocusEffect(
    useCallback(() => {
      getProfile().then((p) => {
        setName((n) => n || p.name);
        setEmail((e) => e || p.email);
        setCompany((c) => c || p.company);
      });
    }, []),
  );

  async function send() {
    if (topic.trim().length < 3) return setError('Tell us the topic in a few words.');
    if (email.trim() && !validEmail(email)) return setError('Check the email address, or leave it blank.');
    if (!isConfigured()) return setError('No connection right now. Try again when you have signal.');
    setError('');
    setStatus('sending');
    try {
      await api('/suggestions/', {
        method: 'POST',
        body: JSON.stringify({ topic, details, month_theme: theme, name, email: email.trim().toLowerCase(), company, may_contact: contact }),
      });
      setStatus('sent');
    } catch {
      setStatus('error');
    }
  }

  if (status === 'sent')
    return (
      <Screen>
        <Text style={[styles.h1, { color: t.text }]}>Thank you</Text>
        <Body>Your idea is with the Zero Harm Weekly team. The best talks come from what crews see on the floor.</Body>
        <Button kind="secondary" label="Suggest another" onPress={() => { setTopic(''); setDetails(''); setStatus('idle'); }} />
      </Screen>
    );

  return (
    <Screen>
      <Body>What should crews talk about? Real situations from your site make the best toolbox talks.</Body>
      <Field label="Topic" value={topic} onChangeText={setTopic} placeholder="Battery charging stations" />
      <Field
        label="What happened, or why it matters (optional)"
        value={details}
        onChangeText={setDetails}
        multiline
        style={{ minHeight: 110, textAlignVertical: 'top' }}
        placeholder="Leave out names and anything that identifies an injured person."
      />
      <Text style={[styles.label, { color: t.muted }]}>Month theme (optional)</Text>
      <View style={styles.chips}>
        {THEMES.map((th) => {
          const on = theme === th;
          return (
            <Pressable key={th} accessibilityRole="button" accessibilityState={{ selected: on }} onPress={() => setTheme(on ? '' : th)}
              style={[styles.chip, { borderColor: t.text, backgroundColor: on ? t.text : 'transparent' }]}>
              <Text style={[styles.chipText, { color: on ? t.background : t.text }]}>{th}</Text>
            </Pressable>
          );
        })}
      </View>
      <Field label="Your name (optional)" value={name} onChangeText={setName} autoCapitalize="words" />
      <Field label="Email (optional)" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
      <Field label="Company (optional)" value={company} onChangeText={setCompany} />
      <View style={[styles.row, { borderColor: t.rule }]}>
        <Text style={[styles.rowText, { color: t.text }]}>OK to contact me about this idea</Text>
        <Switch value={contact} onValueChange={setContact} disabled={!email.trim()} trackColor={{ true: t.accent }}
          accessibilityLabel="OK to contact me about this idea" />
      </View>
      {error !== '' && <Body>{error}</Body>}
      {status === 'error' && <Body>Could not send. Check your connection and tap Send again.</Body>}
      <Button label="Send my idea" onPress={send} busy={status === 'sending'} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  h1: { fontFamily: fonts.display, fontSize: 32 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: { borderWidth: 1.5, borderRadius: 999, paddingHorizontal: 12, minHeight: 40, justifyContent: 'center' },
  chipText: { fontFamily: fonts.bodyBold, fontSize: 14 },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.sm, borderBottomWidth: 1 },
  rowText: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 16 },
});
