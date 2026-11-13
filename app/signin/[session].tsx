import * as ImagePicker from 'expo-image-picker';
import { useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, Image, StyleSheet, Text, View } from 'react-native';
import SignatureScreen, { SignatureViewRef } from 'react-native-signature-canvas';

import { Body, Button, Field, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { attendeeCount, buildSigninSheet, keepOnPhone, printPdf, sharePdf } from '@/lib/pdf';
import { getProfile, Profile, saveProfile, tidyEmail, validEmail } from '@/lib/profile';
import { saveSheetToRecords } from '@/lib/sheets';
import { addSignin, getSession, listSignins, setGroupPhoto, setKeptPdf, Signin, SigninSession } from '@/lib/signins';
import { getSubject, SheetSubject } from '@/lib/subject';

/**
 * Crew sign-in two ways, use either or both:
 *  - pass the phone around: each person types their name and signs with a finger
 *  - the person running the talk takes one group photo and enters the head count
 * Then save the sheet to their records in GoHighLevel, or share the PDF.
 */
export default function SigninScreen() {
  const t = useTheme();
  const { session: sessionParam } = useLocalSearchParams<{ session: string }>();
  const sessionId = Number(sessionParam);
  const sigRef = useRef<SignatureViewRef>(null);
  const [session, setSession] = useState<SigninSession | null>(null);
  const [signins, setSignins] = useState<Signin[]>([]);
  const [name, setName] = useState('');
  const [count, setCount] = useState('');
  const [profile, setProfile] = useState<Profile>({ name: '', email: '', company: '' });
  const [busy, setBusy] = useState<'save' | 'share' | 'print' | 'photo' | null>(null);
  const [result, setResult] = useState('');
  const [drawing, setDrawing] = useState(false); // stop the page scrolling while someone signs

  const refresh = useCallback(async () => {
    const s = await getSession(sessionId);
    setSession(s);
    if (s?.photo_count) setCount(String(s.photo_count));
    setSignins(await listSignins(sessionId));
  }, [sessionId]);

  useFocusEffect(
    useCallback(() => {
      refresh();
      getProfile().then(setProfile);
    }, [refresh]),
  );

  async function onSignature(signature: string) {
    if (!name.trim()) {
      Alert.alert('Add your name', 'Type your name above the signature box, then tap Save signature.');
      return;
    }
    await addSignin(sessionId, name.trim(), signature);
    setName('');
    sigRef.current?.clearSignature();
    refresh();
  }

  async function takePhoto() {
    setBusy('photo');
    try {
      const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.5, base64: true, exif: false };
      const cam = await ImagePicker.requestCameraPermissionsAsync();
      let picked: ImagePicker.ImagePickerResult | null = null;
      if (cam.granted) {
        try {
          picked = await ImagePicker.launchCameraAsync(options);
        } catch {
          picked = null; // no camera (the simulator): fall through to the photo library
        }
      }
      if (!picked) picked = await ImagePicker.launchImageLibraryAsync(options);
      const asset = picked.canceled ? null : picked.assets[0];
      if (asset?.base64) {
        await setGroupPhoto(sessionId, `data:image/jpeg;base64,${asset.base64}`, Number(count) || null);
        refresh();
      }
    } finally {
      setBusy(null);
    }
  }

  async function removePhoto() {
    await setGroupPhoto(sessionId, null, null);
    setCount('');
    refresh();
  }

  async function saveCount(v: string) {
    const digits = v.replace(/\D/g, '').slice(0, 3);
    setCount(digits);
    if (session?.group_photo) await setGroupPhoto(sessionId, session.group_photo, Number(digits) || null);
  }

  async function save() {
    if (!session) return;
    if (!validEmail(profile.email) || !profile.name.trim()) {
      Alert.alert('Add your name and email', 'They tell us whose records this sheet belongs to.');
      return;
    }
    const subject = await getSubject(session);
    if (!subject) return;
    const email = tidyEmail(profile.email);
    if (email !== profile.email) setProfile({ ...profile, email });
    setBusy('save');
    setResult('');
    try {
      await saveProfile(profile);
      const fresh = (await getSession(sessionId)) ?? session;
      const { sent, uri } = await saveSheetToRecords(subject, fresh, signins);
      await keep(subject, fresh, uri);
      setResult(
        sent
          ? `Saved to your Zero Harm records for ${email}.`
          : 'Saved on this phone. It will go to your records the next time you have signal.',
      );
      refresh();
    } catch {
      setResult('Could not build the sheet. Try again, or share the PDF instead.');
    } finally {
      setBusy(null);
    }
  }

  /** Keeps the finished sheet in the app's Documents folder, so it's on the phone with or without signal. */
  async function keep(subject: SheetSubject, s: SigninSession, uri: string) {
    const kept = await keepOnPhone(uri, `${s.created_at.slice(0, 10)}-${subject.title}-${s.id}`);
    await setKeptPdf(s.id, kept, subject.title);
    return kept;
  }

  /** Builds the signed sheet (signatures and group photo), keeps it on the phone, then prints or shares it. */
  async function output(kind: 'share' | 'print') {
    if (!session) return;
    const subject = await getSubject(session);
    if (!subject) return;
    setBusy(kind);
    try {
      const fresh = (await getSession(sessionId)) ?? session;
      const kept = await keep(subject, fresh, await buildSigninSheet(subject, fresh, signins));
      if (kind === 'print') await printPdf(kept);
      else await sharePdf(kept, 'Email or share the sign-in sheet');
      setResult('Kept on this phone under My sign-in sheets.');
    } catch {
      setResult('Could not build the sheet. Try again.');
    } finally {
      setBusy(null);
    }
  }

  const padStyle = `.m-signature-pad{box-shadow:none;border:1px solid ${t.rule}}
    .m-signature-pad--footer{display:none} body,html{height:100%}`;
  const total = session ? attendeeCount(session, signins) : 0;
  const hasSomething = signins.length > 0 || Boolean(session?.group_photo);

  return (
    <Screen scrollEnabled={!drawing}>
      <Text style={[styles.count, { color: t.text }]}>
        {total} {total === 1 ? 'person' : 'people'} signed in
      </Text>

      <Text style={[styles.section, { color: t.text }]}>Group photo</Text>
      <Body muted>Ask the crew first. The photo goes on the sign-in sheet saved to your records.</Body>
      {session?.group_photo ? (
        <View style={{ gap: space.sm }}>
          <Image
            source={{ uri: session.group_photo }}
            style={[styles.photo, { borderColor: t.rule }]}
            accessibilityLabel="Group photo of the crew"
          />
          <Field label="How many people are in the photo?" value={count} onChangeText={saveCount} keyboardType="number-pad" />
          <View style={styles.actions}>
            <View style={{ flex: 1 }}>
              <Button kind="secondary" label="Retake" onPress={takePhoto} busy={busy === 'photo'} />
            </View>
            <View style={{ flex: 1 }}>
              <Button kind="secondary" label="Remove" onPress={removePhoto} />
            </View>
          </View>
        </View>
      ) : (
        <Button kind="secondary" label="Take a group photo" onPress={takePhoto} busy={busy === 'photo'} />
      )}

      <Text style={[styles.section, { color: t.text }]}>Signatures</Text>
      <Field label="Crew member name" value={name} onChangeText={setName} placeholder="First and last name" autoCapitalize="words" />
      <View style={[styles.pad, { borderColor: t.rule }]}>
        <SignatureScreen
          ref={sigRef}
          onOK={onSignature}
          webStyle={padStyle}
          autoClear={false}
          descriptionText=""
          onBegin={() => setDrawing(true)}
          onEnd={() => setDrawing(false)}
        />
      </View>
      <View style={styles.actions}>
        <View style={{ flex: 1 }}>
          <Button kind="secondary" label="Clear" onPress={() => sigRef.current?.clearSignature()} />
        </View>
        <View style={{ flex: 2 }}>
          <Button label="Save signature" onPress={() => sigRef.current?.readSignature()} />
        </View>
      </View>
      {signins.map((s) => (
        <Body key={s.id}>✓ {s.crew_name}</Body>
      ))}

      <Text style={[styles.section, { color: t.text }]}>Save the sheet</Text>
      <Field label="Your name" value={profile.name} onChangeText={(v) => setProfile({ ...profile, name: v })} autoCapitalize="words" autoComplete="name" />
      <Field
        label="Your email"
        value={profile.email}
        onChangeText={(v) => setProfile({ ...profile, email: v })}
        keyboardType="email-address"
        autoCapitalize="none"
        autoComplete="email"
      />
      <Field label="Company" value={profile.company} onChangeText={(v) => setProfile({ ...profile, company: v })} />
      <Button label="Save sheet to my records" onPress={save} busy={busy === 'save'} disabled={!hasSomething} />
      <Button kind="secondary" label="Print the sheet" onPress={() => output('print')} busy={busy === 'print'} disabled={!hasSomething} />
      <Button kind="secondary" label="Email or share the PDF" onPress={() => output('share')} busy={busy === 'share'} disabled={!hasSomething} />
      {result !== '' && <Body>{result}</Body>}
      {session?.saved_at && result === '' && <Body muted>This sheet was saved to your records.</Body>}
      <Body muted>
        Every sheet you print, share or save is also kept on this phone (Settings → My sign-in sheets). Saving to your records also sends it,
        with its signatures and photo, to Trainovate Technologies so you can download it later.
      </Body>
    </Screen>
  );
}

const styles = StyleSheet.create({
  count: { fontFamily: fonts.display, fontSize: 28 },
  section: { fontFamily: fonts.displayMedium, fontSize: 22, marginTop: space.sm },
  pad: { height: 220, borderWidth: 1, borderRadius: 6, overflow: 'hidden' },
  photo: { width: '100%', aspectRatio: 4 / 3, borderWidth: 1, borderRadius: 6 },
  actions: { flexDirection: 'row', gap: space.sm },
});
