import { useEffect, useState } from 'react';

import { api, detailText, type Audience, type BroadcastInput, type EpisodeAdmin, type FeedAdmin, type TalkAdmin } from '../api';
import { Button, ConfirmAction, Field, PageHeader, ResultLine, Section, Select, TextArea, TextField, useAction } from '../ui';

const AUDIENCES: { value: Audience; label: string; who: string; hint: string }[] = [
  { value: 'weekly_talk', label: 'Weekly talk', who: 'everyone with Weekly toolbox talk on', hint: 'Talk reminders and talk-related news.' },
  { value: 'alerts', label: 'Regulatory alerts', who: 'everyone with Regulatory alerts on', hint: 'Rule changes and safety notices only.' },
  { value: 'zero_hour', label: 'Zero Hour', who: 'everyone with Zero Hour episodes on', hint: 'Episode news.' },
  { value: 'offers', label: 'News and offers', who: 'everyone with News and offers on', hint: 'Courses, tools, Trainovate offers. People opt in to this one separately.' },
];

type RouteKind = 'none' | 'talk' | 'alert' | 'zero-hour' | 'learn' | 'otis' | 'archive';

const ROUTE_KINDS: { value: RouteKind; label: string }[] = [
  { value: 'none', label: 'Just open the app' },
  { value: 'talk', label: 'A talk' },
  { value: 'alert', label: 'An alert' },
  { value: 'zero-hour', label: 'A Zero Hour episode' },
  { value: 'learn', label: 'Learn tab' },
  { value: 'otis', label: 'OTIS' },
  { value: 'archive', label: 'Talk archive' },
];

const HEADING_MAX = 60;
const MESSAGE_MAX = 180;

function buildRoute(kind: RouteKind, id: string): string | undefined {
  if (kind === 'none') return undefined;
  if (kind === 'learn' || kind === 'otis' || kind === 'archive') return `/${kind}`;
  return id ? `/${kind}/${id}` : undefined;
}

/** How the notification lands on an iPhone lock screen and an Android shade. */
function NotificationPreview({ heading, message }: { heading: string; message: string }) {
  const h = heading || 'Heading';
  const m = message || 'Your message shows here.';
  return (
    <div className="notif-previews">
      <div>
        <p className="small muted">iPhone</p>
        <div className="notif-ios">
          <div className="notif-icon" aria-hidden="true">ZH</div>
          <div className="notif-text">
            <div className="notif-top"><strong>Zero Harm</strong><span>now</span></div>
            <div className="notif-heading">{h}</div>
            <div className="notif-msg notif-clamp-ios">{m}</div>
          </div>
        </div>
      </div>
      <div>
        <p className="small muted">Android</p>
        <div className="notif-android">
          <div className="notif-top"><span className="notif-dot" aria-hidden="true" />Zero Harm · now</div>
          <div className="notif-heading">{h}</div>
          <div className="notif-msg notif-clamp-android">{m}</div>
        </div>
      </div>
    </div>
  );
}

export default function Broadcast() {
  const [audience, setAudience] = useState<Audience | null>(null);
  const [heading, setHeading] = useState('');
  const [message, setMessage] = useState('');
  const [routeKind, setRouteKind] = useState<RouteKind>('none');
  const [routeId, setRouteId] = useState('');
  const [talks, setTalks] = useState<TalkAdmin[]>([]);
  const [alerts, setAlerts] = useState<FeedAdmin[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeAdmin[]>([]);
  const [previewed, setPreviewed] = useState<string>('');
  const preview = useAction();
  const send = useAction();

  // Choices for the "opens to" picker. Only content phones can actually open is listed.
  useEffect(() => {
    api.talks().then((l) => setTalks(l.filter((t) => t.released))).catch(() => undefined);
    api.feed().then((l) => setAlerts(l.filter((f) => f.live && f.kind === 'alert'))).catch(() => undefined);
    api.episodes().then((l) => setEpisodes(l.filter((e) => e.released !== false))).catch(() => undefined);
  }, []);

  const route = buildRoute(routeKind, routeId);
  const input: BroadcastInput | null = audience ? { audience, heading: heading.trim(), message: message.trim(), route, dry_run: true } : null;
  const fingerprint = JSON.stringify(input);
  const who = AUDIENCES.find((a) => a.value === audience)?.who ?? '';

  function problem(): string {
    if (!audience) return 'Choose who gets it.';
    if (!heading.trim() || !message.trim()) return 'Write a heading and a message.';
    if (heading.length > HEADING_MAX) return `Heading is over ${HEADING_MAX} characters.`;
    if (message.length > MESSAGE_MAX) return `Message is over ${MESSAGE_MAX} characters.`;
    if (routeKind !== 'none' && !route) return 'Pick what the notification opens, or choose “Just open the app”.';
    return '';
  }

  async function runPreview() {
    const p = problem();
    if (p) return preview.setResult({ kind: 'error', text: p });
    const r = await preview.run(() => api.broadcast(input!), (r) =>
      r.ok ? `Dry run OK, nothing was sent. ${detailText(r.detail)}` : `The dry run failed: ${detailText(r.detail)}`);
    if (r?.ok) setPreviewed(fingerprint);
  }

  async function runSend() {
    const p = problem();
    if (p) return send.setResult({ kind: 'error', text: p });
    // Never send anything other than exactly what the last dry run checked.
    if (previewed === '' || previewed !== fingerprint) {
      return send.setResult({ kind: 'error', text: 'The message changed after the dry run. Run the preview again, then send.' });
    }
    const r = await send.run(() => api.broadcast({ ...input!, dry_run: false }), (r) =>
      r.ok ? `Sent to ${who}. ${detailText(r.detail)}` : `OneSignal did not send it: ${detailText(r.detail)}`);
    if (r?.ok) setPreviewed('');
  }

  const ready = previewed !== '' && previewed === fingerprint;

  return (
    <>
      <PageHeader title="Send a notification" intro="A one-off push to one opt-in group. Phones that get it also refresh their content." />
      <div className="editor-grid">
        <div className="editor">
          <Section title="1. Who gets it">
            <fieldset className="radio-group">
              <legend className="sr-only">Audience</legend>
              {AUDIENCES.map((a) => (
                <label key={a.value} className={`radio-card${audience === a.value ? ' radio-card-on' : ''}`}>
                  <input type="radio" name="audience" value={a.value} checked={audience === a.value} onChange={() => setAudience(a.value)} />
                  <span>
                    <span className="row-title">{a.label}</span>
                    <span className="hint">{a.hint}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            <p className="note note-warn"><strong>Anything promotional goes to News and offers only.</strong> Apple rejects apps that send marketing to people who didn’t opt in to it.</p>
          </Section>

          <Section title="2. What it says">
            <div className="form">
              <TextField label="Heading" value={heading} onChange={setHeading} max={HEADING_MAX} />
              <TextArea label="Message" rows={3} value={message} onChange={setMessage} max={MESSAGE_MAX} />
            </div>
          </Section>

          <Section title="3. What it opens">
            <div className="form-row">
              <Select<RouteKind> label="Opens to" value={routeKind} options={ROUTE_KINDS} onChange={(v) => { setRouteKind(v); setRouteId(''); }} />
              {routeKind === 'talk' && (
                <Field label="Talk">
                  {(id) => (
                    <select id={id} value={routeId} onChange={(e) => setRouteId(e.target.value)}>
                      <option value="">Choose a live talk</option>
                      {talks.map((t) => <option key={t.issue} value={t.issue}>#{String(t.number).padStart(2, '0')} {t.title}</option>)}
                    </select>
                  )}
                </Field>
              )}
              {routeKind === 'alert' && (
                <Field label="Alert">
                  {(id) => (
                    <select id={id} value={routeId} onChange={(e) => setRouteId(e.target.value)}>
                      <option value="">Choose a live alert</option>
                      {alerts.map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
                    </select>
                  )}
                </Field>
              )}
              {routeKind === 'zero-hour' && (
                <Field label="Episode">
                  {(id) => (
                    <select id={id} value={routeId} onChange={(e) => setRouteId(e.target.value)}>
                      <option value="">Choose a released episode</option>
                      {episodes.map((e) => <option key={e.number} value={e.number}>EP {String(e.number).padStart(2, '0')} · {e.title}</option>)}
                    </select>
                  )}
                </Field>
              )}
            </div>
            {route && <p className="muted small">Opens <code>{route}</code> in the app.</p>}
          </Section>

          <Section title="4. Check, then send">
            <div className="row">
              <Button onClick={runPreview} busy={preview.busy}>Preview (dry run)</Button>
            </div>
            <ResultLine result={preview.result} />
            <ConfirmAction label="Send notification" confirmLabel="Yes, send it now"
              message={<p>This sends “{heading.trim()}” to <strong>{who}</strong> right now. It can’t be taken back.</p>}
              onConfirm={runSend} busy={send.busy} disabled={!ready} />
            {!ready && <p className="hint">Run a dry-run preview of exactly this message first. Any edit needs a new preview.</p>}
            <ResultLine result={send.result} />
          </Section>
        </div>
        <aside className="preview-col" aria-label="Notification preview">
          <NotificationPreview heading={heading} message={message} />
        </aside>
      </div>
    </>
  );
}
