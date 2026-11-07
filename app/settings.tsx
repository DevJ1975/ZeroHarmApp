import { useEffect, useState } from 'react';
import { Linking, StyleSheet, Switch, Text, View } from 'react-native';

import { Body, Button, Field, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { api, isConfigured } from '@/lib/config';
import { getProfile, saveProfile } from '@/lib/profile';
import { getPrefs, PushPrefs, setPrefs } from '@/lib/push';

export default function SettingsScreen() {
  const t = useTheme();
  const [prefs, setLocal] = useState<PushPrefs>({ weeklyTalk: false, alerts: false, offers: false });
  const [denied, setDenied] = useState(false);
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [company, setCompany] = useState('');
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  useEffect(() => {
    getPrefs().then(setLocal);
    getProfile().then((p) => {
      setEmail(p.email);
      setFirstName(p.name.split(' ')[0] ?? '');
      setCompany(p.company);
    });
  }, []);

  async function toggle(key: keyof PushPrefs, value: boolean) {
    const result = await setPrefs({ ...prefs, [key]: value });
    setLocal(result.prefs);
    setDenied(result.permissionDenied);
  }

  async function signUp() {
    if (!/^\S+@\S+\.\S+$/.test(email.trim()) || !isConfigured()) {
      setStatus('error');
      return;
    }
    setStatus('saving');
    try {
      await api('/signups/', {
        method: 'POST',
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          first_name: firstName.trim(),
          company: company.trim(),
          wants_offers: prefs.offers,
        }),
      });
      const prev = await getProfile();
      await saveProfile({ name: prev.name || firstName, email, company });
      setStatus('saved');
    } catch {
      setStatus('error');
    }
  }

  const row = (label: string, detail: string, key: keyof PushPrefs) => (
    <View style={[styles.row, { borderColor: t.rule }]}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[styles.rowLabel, { color: t.text }]}>{label}</Text>
        <Body muted>{detail}</Body>
      </View>
      <Switch
        accessibilityLabel={label}
        value={prefs[key]}
        onValueChange={(v) => toggle(key, v)}
        trackColor={{ true: t.accent }}
      />
    </View>
  );

  return (
    <Screen>
      <Text style={[styles.section, { color: t.text }]}>Notifications</Text>
      {row('Weekly toolbox talk', 'Sunday around noon Pacific, ready for Monday.', 'weeklyTalk')}
      {row('Regulatory alerts', 'New federal, Nevada and Las Vegas rules that could affect your site.', 'alerts')}
      {row('News and offers', 'New tools, free courses and Trainovate offers. Off unless you turn it on.', 'offers')}
      {denied && (
        <View style={{ gap: space.sm }}>
          <Body>Notifications are blocked for Zero Harm on this phone.</Body>
          <Button kind="secondary" label="Open phone settings" onPress={() => Linking.openSettings()} />
        </View>
      )}

      <Text style={[styles.section, { color: t.text }]}>Get the talk by email too</Text>
      <Body muted>Optional. Everything in the app works without signing up.</Body>
      <Field label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" autoComplete="email" />
      <Field label="First name" value={firstName} onChangeText={setFirstName} autoComplete="given-name" />
      <Field label="Company" value={company} onChangeText={setCompany} />
      <Button label="Sign up" onPress={signUp} busy={status === 'saving'} />
      {status === 'saved' && <Body>Signed up. Your first issue arrives Sunday.</Body>}
      {status === 'error' && <Body>Check the email address and your connection, then tap Sign up again.</Body>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { fontFamily: fonts.displayMedium, fontSize: 24, marginTop: space.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.sm, borderBottomWidth: 1 },
  rowLabel: { fontFamily: fonts.bodyBold, fontSize: 17 },
});
