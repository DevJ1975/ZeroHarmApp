import { Link, router } from 'expo-router';
import Storage from 'expo-sqlite/kv-store';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { HolidayBanner, HolidayTagline } from '@/components/Holiday';
import { MM_ORANGE, MondayMinuteLogo, useMmBorderColor, useMmTextColor } from '@/components/MondayMinuteCard';
import { RegLinks } from '@/components/RegLinks';
import { Body, Button, Field, OfflineNote, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { isConfigured } from '@/lib/config';
import { printHandout, shareHandout } from '@/lib/handout';
import {
  acceptRules, blockAuthor, Comment, listComments, Minute, myVote, postComment, rate, Reason, REASONS,
  reportComment, rulesAccepted, savedDisplayName, weekLabel,
} from '@/lib/monday';
import { regLinks } from '@/lib/regs';
import { useHoliday } from '@/lib/season';
import { getProfile } from '@/lib/profile';
import { startSession } from '@/lib/signins';

const LAST_LOCATION = 'last_signin_location';
const INK_ON_ORANGE = '#17212B'; // white on this orange is too faint to read

/** One Monday Minute: the talk, print and email, crew sign-in, thumbs up/down and the crew conversation. */
/** The same five rules the server sends, kept in the app so the box is never empty on a weak signal. */
const FALLBACK_RULES = [
  'Talk about the topic and your own site. Share what works and what you’ve seen.',
  'No names or details that could identify an injured person, a coworker or a company.',
  'No insults, harassment, threats, hate, sexual content or profanity aimed at anyone.',
  'No ads, links, emails or phone numbers.',
  'Don’t tell others to skip a safety step. If you see something dangerous at work, stop and tell your supervisor.',
];

export function MondayMinuteView({
  minute: m,
  onChange,
  onRefresh,
  offline,
}: {
  minute: Minute;
  onChange: (m: Minute) => void;
  onRefresh?: () => Promise<unknown>;
  offline?: boolean;
}) {
  const t = useTheme();
  const mmText = useMmTextColor();
  const mmBorder = useMmBorderColor();
  const festive = useHoliday();
  const [supervisor, setSupervisor] = useState('');
  const [location, setLocation] = useState('');

  // Fewer taps in gloves: start from the name and location used last time.
  useEffect(() => {
    getProfile().then((p) => setSupervisor((cur) => cur || p.name));
    Storage.getItem(LAST_LOCATION).then((v) => setLocation((cur) => cur || v || ''));
  }, []);
  const [busy, setBusy] = useState<'print' | 'share' | null>(null);

  async function begin() {
    if (location.trim()) await Storage.setItem(LAST_LOCATION, location.trim());
    const session = await startSession(m.id, supervisor.trim(), location.trim(), 'mm');
    router.push(`/signin/${session}`);
  }

  async function handout(kind: 'print' | 'share') {
    setBusy(kind);
    try {
      await (kind === 'print' ? printHandout(m) : shareHandout(m));
    } catch {
      Alert.alert('Could not make the PDF', 'Try again in a moment.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <Screen onRefresh={onRefresh}>
      {festive ? (
        <HolidayBanner>
          <MondayMinuteLogo onDark />
          <HolidayTagline />
        </HolidayBanner>
      ) : (
        <MondayMinuteLogo />
      )}
      {offline && <OfflineNote />}
      <Text style={[styles.kicker, { color: mmText }]}>WEEK OF {weekLabel(m).toUpperCase()} · {m.category.toUpperCase()}</Text>
      <Text style={[styles.title, { color: t.text }]} accessibilityRole="header">{m.title}</Text>
      <Button label="Start crew sign-in" onPress={begin} />
      <View style={styles.actions}>
        <View style={{ flex: 1 }}><Button kind="secondary" label="Print" onPress={() => handout('print')} busy={busy === 'print'} /></View>
        <View style={{ flex: 1 }}><Button kind="secondary" label="Share PDF" onPress={() => handout('share')} busy={busy === 'share'} /></View>
      </View>
      <Text style={[styles.hint, { color: t.muted }]}>Print and Share include a paper sign-in sheet.</Text>
      <Body>{m.intro}</Body>
      <Text style={[styles.h2, { color: t.text }]} accessibilityRole="header">Talk it through</Text>
      {m.points.map((p, i) => (
        <View key={i} style={styles.point}>
          <Text style={[styles.num, { color: mmText }]}>{i + 1}</Text>
          <View style={{ flex: 1 }}><Body>{p}</Body></View>
        </View>
      ))}

      <Text style={[styles.h2, { color: t.text }]} accessibilityRole="header">Close call: {m.story_title}</Text>
      <Body>{m.story}</Body>

      <View style={[styles.question, { borderColor: mmBorder }]}>
        <Text style={[styles.qLabel, { color: t.text }]}>Ask your crew</Text>
        <Body>{m.crew_question}</Body>
      </View>
      <View style={[styles.takeawayBox, { borderColor: mmBorder }]}>
        <Text style={[styles.takeaway, { color: t.text }]}>{m.takeaway}</Text>
      </View>
      <RegLinks links={regLinks(...m.references)} />
      <Text style={[styles.hint, { color: t.muted }]}>
        Written by AI from a topic reviewed by a safety professional, and checked automatically before it’s published. It adds to your training and
        doesn’t replace it. Always follow your site’s written steps. Not sure it’s safe? Stop and ask.
      </Text>

      <Text style={[styles.h2, { color: t.text }]}>Run the talk</Text>
      <Body muted>Crew signs on this phone (or take one group photo). Then print the signed sheet, email it, or save it to your records. Paper crews: use the printed sign-in sheet instead.</Body>
      <Field label="Supervisor" value={supervisor} onChangeText={setSupervisor} placeholder="Your name" autoCapitalize="words" />
      <Field label="Location" value={location} onChangeText={setLocation} placeholder="Line, dock or shop" />
      <Button label="Start crew sign-in" onPress={begin} />

      {isConfigured() && <Rating minute={m} onCounts={(up, down) => onChange({ ...m, thumbs_up: up, thumbs_down: down })} />}
      {isConfigured() && <Conversation minute={m} />}
      <View style={styles.links}>
        <Link href="/monday" style={[styles.link, { color: t.text }]}>Past Monday Minutes →</Link>
        <Link href="/sheets" style={[styles.link, { color: t.text }]}>My sign-in sheets →</Link>
        <Link href="/settings" style={[styles.link, { color: t.text }]}>Settings →</Link>
      </View>
    </Screen>
  );
}

function Rating({ minute, onCounts }: { minute: Minute; onCounts: (up: number, down: number) => void }) {
  const t = useTheme();
  const [vote, setVote] = useState<boolean | null>(null);
  const [asking, setAsking] = useState(false);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [note, setNote] = useState('');
  const [msg, setMsg] = useState('');

  useEffect(() => {
    myVote(minute.id).then((v) => setVote(v ? v.helpful : null));
  }, [minute.id]);

  async function send(helpful: boolean, why: Reason[] = []) {
    const counts = await rate(minute.id, helpful, why, note);
    setVote(helpful);
    setAsking(false);
    if (counts) {
      onCounts(counts.thumbs_up, counts.thumbs_down);
      setMsg(why.includes('unsafe') ? 'Thanks. Reports like this pull a talk for review.' : 'Thanks for the feedback.');
    } else {
      setMsg('Saved on this phone. It will send when you have signal.');
    }
  }

  return (
    <View style={[styles.box, { borderColor: t.rule, backgroundColor: t.surface }]}>
      <Text style={[styles.qLabel, { color: t.text }]}>Was this a good talk?</Text>
      <View style={styles.thumbs}>
        {([true, false] as const).map((up) => (
          <Pressable
            key={String(up)}
            accessibilityRole="button"
            accessibilityState={{ selected: vote === up }}
            accessibilityLabel={up ? `Thumbs up, ${minute.thumbs_up}` : `Thumbs down, ${minute.thumbs_down}`}
            onPress={() => (up ? send(true) : setAsking(true))}
            style={[styles.thumb, { borderColor: vote === up ? MM_ORANGE : t.rule, backgroundColor: vote === up ? MM_ORANGE : 'transparent' }]}>
            <Text style={[styles.thumbText, { color: vote === up ? INK_ON_ORANGE : t.text }]}>
              {up ? '👍' : '👎'} {up ? minute.thumbs_up : minute.thumbs_down}
            </Text>
          </Pressable>
        ))}
      </View>
      {asking && (
        <View style={{ gap: space.sm }}>
          <Body muted>What was wrong? Pick any that fit.</Body>
          {REASONS.map((r) => {
            const on = reasons.includes(r.key);
            return (
              <Pressable
                key={r.key}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                onPress={() => setReasons(on ? reasons.filter((x) => x !== r.key) : [...reasons, r.key])}
                style={[styles.chip, { borderColor: on ? MM_ORANGE : t.rule, backgroundColor: on ? MM_ORANGE : 'transparent' }]}>
                <Text style={[styles.chipText, { color: on ? INK_ON_ORANGE : t.text }]}>{r.label}</Text>
              </Pressable>
            );
          })}
          <Field label="Anything else? (optional)" value={note} onChangeText={setNote} maxLength={300} placeholder="What should change?" />
          <Button label="Send thumbs down" onPress={() => send(false, reasons)} />
        </View>
      )}
      {msg !== '' && <Body muted>{msg}</Body>}
    </View>
  );
}

function Conversation({ minute }: { minute: Minute }) {
  const t = useTheme();
  const mmText = useMmTextColor();
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [rules, setRules] = useState<string[]>([]);
  const [agreed, setAgreed] = useState(false);
  const [showRules, setShowRules] = useState(false);
  const [name, setName] = useState('');
  const [body, setBody] = useState('');
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(
    () =>
      listComments(minute.id)
        .then((data) => {
          setComments(data.comments);
          setRules(data.rules);
        })
        .catch(() => setComments([])),
    [minute.id],
  );

  useEffect(() => {
    let live = true;
    listComments(minute.id)
      .then((data) => live && (setComments(data.comments), setRules(data.rules)))
      .catch(() => live && setComments([]));
    rulesAccepted().then((v) => live && setAgreed(v));
    savedDisplayName().then((v) => live && setName(v));
    return () => {
      live = false;
    };
  }, [minute.id]);

  async function submit() {
    if (!agreed) {
      setShowRules(true);
      return;
    }
    if (body.trim().length < 2) return;
    setBusy(true);
    setMsg('');
    try {
      const res = await postComment(minute.id, body.trim(), name.trim(), replyTo?.id);
      setMsg(res.message);
      if (res.status !== 'rejected') {
        setBody('');
        setReplyTo(null);
        load();
      }
    } catch {
      setMsg('Could not post. Check your signal and try again.');
    } finally {
      setBusy(false);
    }
  }

  function more(c: Comment) {
    Alert.alert('Comment options', undefined, [
      {
        text: 'Report comment',
        onPress: () => reportComment(c.id).then(() => setMsg('Reported. Thanks for keeping it respectful.')).catch(() => setMsg('Could not report. Try again.')),
      },
      {
        text: `Block ${c.display_name}`,
        style: 'destructive',
        onPress: async () => {
          await blockAuthor(c.author_key);
          // Blocking also tells us, so a person can look at the comment within a day.
          reportComment(c.id, 'blocked').catch(() => {});
          setMsg('You won’t see their comments on this phone.');
          load();
        },
      },
      { text: 'Cancel', style: 'cancel' },
    ]);
  }

  const row = (c: Comment, reply = false) => (
    <View key={c.id} style={[styles.comment, reply && styles.reply, { borderColor: t.rule }]}>
      <View style={styles.commentHead}>
        <Text style={[styles.author, { color: t.text }]}>{c.display_name}</Text>
        <Pressable accessibilityRole="button" accessibilityLabel={`Options for ${c.display_name}'s comment`} hitSlop={8} onPress={() => more(c)} style={styles.tap}>
          <Text style={[styles.link, { color: t.muted }]}>•••</Text>
        </Pressable>
      </View>
      <Body>{c.body}</Body>
      {!reply && (
        <Pressable accessibilityRole="button" accessibilityLabel={`Reply to ${c.display_name}`} onPress={() => setReplyTo(c)} style={styles.tap}>
          <Text style={[styles.link, { color: mmText }]}>Reply</Text>
        </Pressable>
      )}
    </View>
  );

  return (
    <View style={{ gap: space.sm }}>
      <Text style={[styles.h2, { color: t.text }]}>Crew talk</Text>
      <Body muted>How does this go at your site? Answer the crew question, share what works, or ask other crews.</Body>
      {comments === null && <ActivityIndicator />}
      {comments?.length === 0 && <Body muted>No comments yet. Start the conversation.</Body>}
      {comments?.map((c) => (
        <View key={c.id} style={{ gap: space.xs }}>
          {row(c)}
          {c.replies.map((r) => row(r, true))}
        </View>
      ))}

      {showRules && !agreed && (
        <View style={[styles.box, { borderColor: MM_ORANGE, backgroundColor: t.surface }]}>
          <Text style={[styles.qLabel, { color: t.text }]}>Community rules</Text>
          {(rules.length ? rules : FALLBACK_RULES).map((r, i) => <Body key={i}>• {r}</Body>)}
          <Body muted>Comments that break these rules are removed, and people who post them lose the ability to comment. Reports are looked at within 24 hours.</Body>
          <Body muted>Comments are public to Zero Harm app users and are checked before they show. Abusive comments are removed, and you can report or block anyone.</Body>
          <Button
            label="I agree"
            onPress={async () => {
              await acceptRules();
              setAgreed(true);
              setShowRules(false);
            }}
          />
        </View>
      )}

      {replyTo && (
        <Pressable accessibilityRole="button" onPress={() => setReplyTo(null)}>
          <Body muted>Replying to {replyTo.display_name} · tap to cancel</Body>
        </Pressable>
      )}
      <Field label="Name to show (optional)" value={name} onChangeText={setName} maxLength={40} placeholder="Crew member" autoCapitalize="words" />
      <TextInput
        value={body}
        onChangeText={setBody}
        placeholder={replyTo ? 'Write a reply' : 'Add to the conversation'}
        placeholderTextColor={t.muted}
        multiline
        maxLength={500}
        accessibilityLabel="Comment"
        style={[styles.input, { color: t.text, borderColor: t.rule, backgroundColor: t.surface }]}
      />
      <Body muted>Leave out names and anything that identifies an injured person.</Body>
      <Button label={replyTo ? 'Post reply' : 'Post comment'} onPress={submit} busy={busy} />
      {msg !== '' && <Body muted>{msg}</Body>}
    </View>
  );
}

const styles = StyleSheet.create({
  kicker: { fontFamily: fonts.displayMedium, fontSize: 15, letterSpacing: 0.5 },
  title: { fontFamily: fonts.display, fontSize: 34, lineHeight: 37 },
  h2: { fontFamily: fonts.displayMedium, fontSize: 22, marginTop: space.sm },
  point: { flexDirection: 'row', gap: space.sm },
  num: { fontFamily: fonts.display, fontSize: 24, width: 22 },
  question: { borderWidth: 3, borderRadius: 8, padding: space.md, gap: space.xs },
  qLabel: { fontFamily: fonts.displayMedium, fontSize: 20 },
  takeaway: { fontFamily: fonts.bodyBold, fontSize: 18, lineHeight: 25 },
  takeawayBox: { borderLeftWidth: 5, paddingLeft: space.md, paddingVertical: space.xs },
  hint: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  tap: { minHeight: 44, minWidth: 44, justifyContent: 'center' },
  actions: { flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' },
  links: { gap: space.md, marginTop: space.md },
  box: { borderWidth: 1, borderRadius: 8, padding: space.md, gap: space.sm, marginTop: space.sm },
  thumbs: { flexDirection: 'row', gap: space.md },
  thumb: { flex: 1, minHeight: 52, borderWidth: 2, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  thumbText: { fontFamily: fonts.bodyBold, fontSize: 20 },
  chip: { borderWidth: 1.5, borderRadius: 8, paddingHorizontal: 12, minHeight: 44, justifyContent: 'center' },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  comment: { borderWidth: 1, borderRadius: 8, padding: space.sm, gap: 4 },
  reply: { marginLeft: space.lg },
  commentHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  author: { fontFamily: fonts.bodyBold, fontSize: 15 },
  link: { fontFamily: fonts.bodyBold, fontSize: 15 },
  input: { borderWidth: 1, borderRadius: 6, minHeight: 88, padding: space.sm, fontFamily: fonts.body, fontSize: 17, textAlignVertical: 'top' },
});
