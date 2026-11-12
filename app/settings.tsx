import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useEffect, useState } from 'react';
import { Alert, Linking, StyleSheet, Switch, Text, View } from 'react-native';

import { Body, Button, Field, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import {
  type AccountNotice,
  checkSignIn,
  CONSENT_LINE,
  flushAccount,
  getAccount,
  notChangedLine,
  REMOVAL_PENDING_LINE,
  removalLine,
  REMOVE_CONFIRM_TEXT,
  removeMyInfo,
  type RemoveOutcome,
  signedInAs,
  signIn,
  SignInErrors,
} from '@/lib/account';
import { config } from '@/lib/config';
import { FeedbackPrefs, getFeedbackPrefs, saveFeedbackPrefs } from '@/lib/otis/feedback';
import { getProfile } from '@/lib/profile';
import { getPrefs, PushPrefs, setPrefs } from '@/lib/push';
import { CRASH_REPORT_HOLDS, crashReportsOn, setCrashReportsOn } from '@/lib/support/crash';
import { getUsageOn, setUsageOn } from '@/lib/usage';

export default function SettingsScreen() {
  const t = useTheme();
  const [prefs, setLocal] = useState<PushPrefs>({ mondayMinute: false, weeklyTalk: false, alerts: false, zeroHour: false, offers: false });
  const [denied, setDenied] = useState(false);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [company, setCompany] = useState('');
  const [account, setAccount] = useState<'loading' | 'in' | 'out' | 'fix'>('loading');
  const [errors, setErrors] = useState<SignInErrors>({});
  const [busy, setBusy] = useState(false);
  // What the server said about the sign-up that the person has to be told: see AccountNotice in lib/account.ts.
  const [notice, setNotice] = useState<AccountNotice | undefined>(undefined);
  // What "Remove my info" did just now. null until it is tapped.
  const [removal, setRemoval] = useState<RemoveOutcome | null>(null);
  const [removing, setRemoving] = useState(false);
  const [removeFailed, setRemoveFailed] = useState(false);
  const [otis, setOtis] = useState<FeedbackPrefs>({ helpImprove: false, shareQuestion: false });
  const [usage, setUsage] = useState(true);
  const [crash, setCrash] = useState(crashReportsOn);

  useEffect(() => {
    getPrefs().then(setLocal);
    getFeedbackPrefs().then(setOtis);
    getUsageOn().then(setUsage);
    // The sign-in sheet profile only fills in the form. "Signed in as" shows what this phone signed up with.
    Promise.all([getProfile(), getAccount()]).then(([p, a]) => {
      setName(a.state === 'out' ? p.name : a.name);
      setEmail(a.state === 'out' ? p.email : a.email);
      setCompany(p.company);
      setNotice(a.notice);
      setAccount(a.state);
    });
  }, []);

  async function toggle(key: keyof PushPrefs, value: boolean) {
    const result = await setPrefs({ ...prefs, [key]: value });
    setLocal(result.prefs);
    setDenied(result.permissionDenied);
  }

  async function toggleOtis(next: FeedbackPrefs) {
    const clean = { helpImprove: next.helpImprove, shareQuestion: next.helpImprove && next.shareQuestion };
    setOtis(clean);
    await saveFeedbackPrefs(clean);
  }

  const otisRow = (label: string, detail: string, value: boolean, onChange: (v: boolean) => void, disabled = false) => (
    <View style={[styles.row, { borderColor: t.rule, opacity: disabled ? 0.5 : 1 }]}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[styles.rowLabel, { color: t.text }]}>{label}</Text>
        <Body muted>{detail}</Body>
      </View>
      <Switch accessibilityLabel={label} value={value} disabled={disabled} onValueChange={onChange} trackColor={{ true: t.accent }} />
    </View>
  );

  // Signing in never waits on the network: it is saved on the phone and sent when there is a signal.
  async function signInHere() {
    const checked = checkSignIn({ name, email });
    setErrors(checked.errors);
    if (!checked.ok) return;
    setBusy(true);
    try {
      await signIn({ name: checked.name, email: checked.email, company, source: 'settings', wantsOffers: prefs.offers });
      setName(checked.name);
      setEmail(checked.email);
      setRemoval(null);
      setRemoveFailed(false);
      setNotice(undefined);
      setAccount('in');
      // Not waited on. When the server answers it may say this email was signed up from another phone, so the name
      // typed here was not saved. Show what the phone holds then, never what was typed.
      flushAccount()
        .then(getAccount)
        .then((a) => {
          if (a.state !== 'in') return;
          setName(a.name);
          setEmail(a.email);
          setNotice(a.notice);
        })
        .catch(() => {});
    } catch {
      setErrors({ email: 'That could not be saved on this phone. Tap Sign in again.' });
    } finally {
      setBusy(false);
    }
  }

  function confirmRemove() {
    Alert.alert('Remove my info?', REMOVE_CONFIRM_TEXT, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          // This waits for the server (up to about ten seconds on a weak signal), because what the screen says next
          // depends on the answer: removed, a person was asked to remove it, or saved to send later.
          setRemoving(true);
          setRemoveFailed(false);
          try {
            const outcome = await removeMyInfo();
            setName('');
            setEmail('');
            setCompany('');
            setErrors({});
            setNotice(undefined);
            setRemoval(outcome);
            setAccount('out');
          } catch {
            setRemoveFailed(true);
          } finally {
            setRemoving(false);
          }
        },
      },
    ]);
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
      <Text style={[styles.section, { color: t.text, marginTop: 0 }]}>Your account</Text>
      {account === 'in' && (
        <>
          <Body>{signedInAs({ name, email })}</Body>
          {notice === 'not_changed' && (
            <View accessibilityRole="alert" style={{ gap: space.sm }}>
              <Body>{notChangedLine(config.supportEmail)}</Body>
              {config.supportEmail.trim() !== '' && (
                <Button kind="secondary" label="Contact support about my sign-up" onPress={() => Linking.openURL(`mailto:${config.supportEmail}?subject=Change%20my%20Zero%20Harm%20sign-up`)} />
              )}
            </View>
          )}
          <Body muted>Zero Harm is free. You get Zero Harm Weekly by email each week.</Body>
          {removeFailed && (
            <View accessibilityRole="alert">
              <Body>That did not work on this phone. Tap Remove my info again.</Body>
            </View>
          )}
          <Button kind="secondary" label="Remove my info" onPress={confirmRemove} busy={removing} />
        </>
      )}
      {(account === 'out' || account === 'fix') && (
        <>
          {account === 'fix' && (
            <View accessibilityRole="alert">
              <Body>Check the email address and sign in again.</Body>
            </View>
          )}
          {/* Says what really happened: removed, a person was asked to remove it, or waiting for a signal. */}
          {removal !== null ? (
            <View accessibilityRole="alert">
              <Body>{removalLine(removal)}</Body>
            </View>
          ) : (
            notice === 'removal_pending' && (
              <View accessibilityRole="alert">
                <Body>{REMOVAL_PENDING_LINE}</Body>
              </View>
            )
          )}
          <Body muted>Zero Harm is free. Signing in is optional, and everything in the app works without it.</Body>
          <Field label="Your name" value={name} onChangeText={setName} error={errors.name} autoComplete="name" autoCapitalize="words" maxLength={120} />
          <Field
            label="Email"
            value={email}
            onChangeText={setEmail}
            error={errors.email}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
          />
          <Field label="Company (optional)" value={company} onChangeText={setCompany} maxLength={120} />
          <Button label="Sign in" onPress={signInHere} busy={busy} />
          <Body muted>{CONSENT_LINE}</Body>
        </>
      )}

      <Text style={[styles.section, { color: t.text }]}>Notifications</Text>
      {row('Monday Minute', 'Monday at 5 AM Pacific: a new 5-minute crew talk with sign-in.', 'mondayMinute')}
      {row('Weekly toolbox talk', 'Sunday around noon Pacific, ready for Monday.', 'weeklyTalk')}
      {row('Regulatory alerts', 'New federal, Nevada and Las Vegas rules that could affect your site.', 'alerts')}
      {row('Zero Hour episodes', 'A new 5-minute episode and huddle card, Thursdays.', 'zeroHour')}
      {row('News and offers', 'New tools, free courses and Trainovate offers. Off unless you turn it on.', 'offers')}
      {denied && (
        <View style={{ gap: space.sm }}>
          <Body>Notifications are blocked for Zero Harm on this phone.</Body>
          <Button kind="secondary" label="Open phone settings" onPress={() => Linking.openSettings()} />
        </View>
      )}

      <Text style={[styles.section, { color: t.text }]}>Sign-in sheets</Text>
      <Button kind="secondary" label="My sign-in sheets" onPress={() => router.push('/sheets')} />

      <Text style={[styles.section, { color: t.text }]}>OTIS</Text>
      <Body muted>OTIS runs on this phone. What you ask stays on it unless you turn this on, or you choose to report a problem or an answer.</Body>
      {otisRow(
        'Help improve OTIS',
        'Shows “Was this helpful?” under answers. A tap sends yes or no and which sources OTIS used. No name, email or phone id.',
        otis.helpImprove,
        (v) => toggleOtis({ ...otis, helpImprove: v }),
      )}
      {otisRow(
        'Include my question',
        'Also send the question you asked with your rating. Leave out names and anything that identifies an injured person.',
        otis.shareQuestion,
        (v) => toggleOtis({ ...otis, shareQuestion: v }),
        !otis.helpImprove,
      )}

      <Text style={[styles.section, { color: t.text }]}>Problems with the app</Text>
      <Body muted>Something not working? Tell us. A person at Trainovate reads every report.</Body>
      <Button kind="secondary" label="Report a problem" onPress={() => router.push('/report')} />
      <Button kind="secondary" label="My reports" onPress={() => router.push('/my-reports')} />

      <Text style={[styles.section, { color: t.text }]}>About and privacy</Text>
      <Body>Zero Harm is free.</Body>
      <Button kind="secondary" label="How to use Zero Harm" onPress={() => router.push('/how-to')} />
      <Body muted>
        Zero Harm gives general safety awareness. It adds to your site training and doesn’t replace it, and it isn’t legal or medical advice.
        Monday Minute talks are written by AI and checked before they publish. OTIS is an AI assistant that runs on this phone. Trainovate
        Technologies is not part of OSHA or any government agency.
      </Body>
      {otisRow(
        'Anonymous usage count',
        'Once a day the app tells Trainovate it was opened, with the app version and an approximate city. No name, email or exact location. Turning it off stops it.',
        usage,
        (v) => {
          setUsage(v);
          setUsageOn(v);
        },
      )}
      {otisRow(
        'Crash reports',
        `When the app hits an error, it sends ${CRASH_REPORT_HOLDS}. It is built to leave out what you typed, your name and your email. Turning it off also deletes any reports waiting on this phone.`,
        crash,
        (v) => {
          setCrashReportsOn(v);
          setCrash(crashReportsOn()); // read back, so the switch shows what the phone really kept
        },
      )}
      {config.privacyUrl !== '' && <Button kind="secondary" label="Privacy policy" onPress={() => WebBrowser.openBrowserAsync(config.privacyUrl)} />}
      {config.termsUrl !== '' && <Button kind="secondary" label="Terms of use" onPress={() => WebBrowser.openBrowserAsync(config.termsUrl)} />}
      {config.supportEmail !== '' && (
        <>
          <Button kind="secondary" label="Contact support" onPress={() => Linking.openURL(`mailto:${config.supportEmail}?subject=Zero%20Harm%20app`)} />
          <Button
            kind="secondary"
            label="Delete my data"
            onPress={() => Linking.openURL(`mailto:${config.supportEmail}?subject=Delete%20my%20Zero%20Harm%20data&body=Please%20delete%20the%20data%20tied%20to%20this%20email%20address%3A%20sign-ups%2C%20saved%20sign-in%20sheets%2C%20suggestions%2C%20comments%20and%20problem%20reports.`)}
          />
          <Body muted>Remove my info, at the top, clears your details from this phone and removes your sign-up. From a phone that did not make the sign-up, it asks us to remove it. Delete my data opens an email to us for everything else. Send it from the address you signed up with and we’ll remove your sign-ups, saved sheets, suggestions, comments and problem reports.</Body>
        </>
      )}
      <Text style={[styles.credit, { color: t.muted }]}>Made with love ❤️ from Las Vegas, Trainovate</Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { fontFamily: fonts.displayMedium, fontSize: 24, marginTop: space.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.sm, borderBottomWidth: 1 },
  rowLabel: { fontFamily: fonts.bodyBold, fontSize: 17 },
  credit: { fontFamily: fonts.body, fontSize: 14, textAlign: 'center', marginTop: space.lg, marginBottom: space.md },
});
