import { useEffect, useState } from 'react';

import { api, detailText, type EpisodeAdmin, type EpisodePatch } from '../api';
import { formatPacific, fromLocalInput, toLocalInput } from '../time';
import {
  Button, ConfirmAction, ListEditor, Loading, PageHeader, Pill, ResultLine, Section, StaleNote, TextArea, TextField, Toggle, useAction, useDraft, useLoad,
} from '../ui';

interface Draft {
  title: string;
  hazard: string;
  story: string;
  zero_hour: string;
  chain: string[];
  checks_label: string;
  checks: string[];
  stop_when: string;
  emergency_label: string;
  emergency: string;
  questions: string[];
  references: string[];
  video_url: string;
  thumbnail_url: string;
  card_pdf_url: string;
  release_at: string;
  published: boolean;
  needs_details: boolean;
  send_push: boolean;
}

const URL_FIELDS = ['video_url', 'thumbnail_url', 'card_pdf_url'] as const;
const LIST_FIELDS = ['chain', 'checks', 'questions', 'references'] as const;

function toDraft(e: EpisodeAdmin): Draft {
  return {
    title: e.title, hazard: e.hazard, story: e.story, zero_hour: e.zero_hour,
    chain: [...(e.chain ?? [])], checks_label: e.checks_label, checks: [...(e.checks ?? [])], stop_when: e.stop_when,
    emergency_label: e.emergency_label, emergency: e.emergency, questions: [...(e.questions ?? [])], references: [...(e.references ?? [])],
    video_url: e.video_url ?? '', thumbnail_url: e.thumbnail_url ?? '', card_pdf_url: e.card_pdf_url ?? '',
    release_at: toLocalInput(e.release_at ?? e.released_at), published: e.published ?? true, needs_details: e.needs_details ?? false,
    send_push: e.send_push ?? true,
  };
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** Only changed fields are sent. Blank lines in lists are dropped. */
function changes(before: Draft, after: Draft): EpisodePatch {
  const out: Record<string, unknown> = {};
  (Object.keys(after) as (keyof Draft)[]).forEach((k) => {
    let v: unknown = after[k];
    if ((LIST_FIELDS as readonly string[]).includes(k)) v = (v as string[]).map((x) => x.trim()).filter(Boolean);
    if (same(v, before[k])) return;
    out[k] = k === 'release_at' ? fromLocalInput(after.release_at) : v;
  });
  return out as EpisodePatch;
}

const isDirty = (before: Draft, after: Draft) => Object.keys(changes(before, after)).length > 0;

function EpisodePills({ e }: { e: EpisodeAdmin }) {
  return (
    <span className="pills">
      {e.released ? <Pill tone="green">Released</Pill> : e.published === false ? <Pill tone="outline">Hidden</Pill> : <Pill>Scheduled</Pill>}
      {e.needs_details && <Pill tone="red">Needs details</Pill>}
      {e.push_sent_at && <Pill>Pushed</Pill>}
    </span>
  );
}

function EpisodeEditor({ ep, onSaved }: { ep: EpisodeAdmin; onSaved: (e: EpisodeAdmin) => void }) {
  const { base, d, setD, dirty, stale, load } = useDraft(ep, toDraft, isDirty);
  const [force, setForce] = useState(false);
  const save = useAction();
  const push = useAction();

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const patch = changes(base, d);

  async function submit() {
    const bad = URL_FIELDS.find((k) => d[k] && !d[k].startsWith('https://'));
    if (bad) return save.setResult({ kind: 'error', text: 'Video, thumbnail and card links must start with https://' });
    if (!dirty) return save.setResult({ kind: 'info', text: 'Nothing to save.' });
    const saved = await save.run(() => api.updateEpisode(ep.number, patch), 'Saved. Phones pick it up the next time the app opens.');
    if (saved) {
      load(saved);
      onSaved(saved);
    }
  }

  async function sendPush() {
    await push.run(() => api.pushEpisode(ep.number, force), (r) => (r.ok ? `Push sent. ${detailText(r.detail)}` : `OneSignal did not send it: ${detailText(r.detail)}`));
    const fresh = await api.episode(ep.number).catch(() => null);
    if (fresh) onSaved(fresh);
  }

  return (
    <div className="editor">
      <div className="editor-head">
        <h2>EP {String(ep.number).padStart(2, '0')} · {ep.title}</h2>
        <p className="muted small">Releases {formatPacific(ep.release_at ?? ep.released_at)}</p>
        <EpisodePills e={ep} />
      </div>

      <div className="form">
        <TextField label="Title" value={d.title} onChange={(v) => set('title', v)} max={120} />
        <div className="form-row">
          <TextField label="Hazard" value={d.hazard} onChange={(v) => set('hazard', v)} max={120} placeholder="Lockout / Tagout · Stored Energy" />
          <TextField label="Zero hour (clock time)" value={d.zero_hour} onChange={(v) => set('zero_hour', v)} max={20} placeholder="3:38 P.M." />
        </div>
        <TextArea label="The story in 30 seconds" rows={4} value={d.story} onChange={(v) => set('story', v)} />

        <h3 className="form-heading">Huddle card</h3>
        <ListEditor label="Where the chain could have broken" items={d.chain} onChange={(v) => set('chain', v)} />
        <TextField label="Checks heading" value={d.checks_label} onChange={(v) => set('checks_label', v)} max={80} />
        <ListEditor label="Checks" items={d.checks} onChange={(v) => set('checks', v)} addLabel="+ Add a check" />
        <TextArea label="Stop work when" rows={3} value={d.stop_when} onChange={(v) => set('stop_when', v)} />
        <TextField label="Emergency heading" value={d.emergency_label} onChange={(v) => set('emergency_label', v)} max={80} />
        <TextArea label="Emergency steps" rows={3} value={d.emergency} onChange={(v) => set('emergency', v)} />
        <ListEditor label="Questions for the crew" items={d.questions} onChange={(v) => set('questions', v)} addLabel="+ Add a question" />
        <ListEditor label="References" items={d.references} onChange={(v) => set('references', v)} addLabel="+ Add a reference"
          hint="Standards and sources, e.g. OSHA 1910.147." />

        <h3 className="form-heading">Media and schedule</h3>
        <TextField label="Video link (720p streaming copy)" type="url" value={d.video_url} onChange={(v) => set('video_url', v)} placeholder="https://" />
        <TextField label="Thumbnail link" type="url" value={d.thumbnail_url} onChange={(v) => set('thumbnail_url', v)} placeholder="https://" />
        <TextField label="Printable huddle card PDF" type="url" value={d.card_pdf_url} onChange={(v) => set('card_pdf_url', v)} placeholder="https://" />
        <TextField label="Release (Pacific time)" type="datetime-local" value={d.release_at} onChange={(v) => set('release_at', v)} hint="Zero Hour normally posts Thursdays at 5:00 AM." />
        <Toggle label="Published" checked={d.published} onChange={(v) => set('published', v)} />
        <Toggle label="Needs details" checked={d.needs_details} onChange={(v) => set('needs_details', v)} hint="On holds it out of the app until the huddle card is filled in." />
        <Toggle label="Send a push on release" checked={d.send_push} onChange={(v) => set('send_push', v)} hint="Goes to everyone with Zero Hour episodes on." />
      </div>

      <div className="save-bar">
        <Button kind="primary" onClick={submit} busy={save.busy} disabled={!dirty}>Save changes</Button>
        <Button kind="quiet" onClick={() => load(ep)} disabled={!dirty}>Discard</Button>
        {dirty && <span className="muted small">Unsaved changes</span>}
        <ResultLine result={save.result} />
      </div>
      {stale && <StaleNote what="episode" />}

      <Section title="Send push now">
        {ep.push_sent_at && <p className="muted">A push already went out {formatPacific(ep.push_sent_at)}.</p>}
        {ep.released === false && (
          <Toggle label="Send even though it isn’t out yet" checked={force} onChange={setForce}
            hint="Phones that tap it won’t find the episode yet. The Thursday release push still goes out, if that’s switched on." />
        )}
        <ConfirmAction label="Send push now" confirmLabel="Yes, send it"
          message={<p>This sends a notification to <strong>everyone with Zero Hour episodes on</strong>. It can’t be taken back.</p>}
          onConfirm={sendPush} busy={push.busy} disabled={dirty || (ep.released === false && !force)} />
        {dirty && <p className="hint">Save your changes first.</p>}
        <ResultLine result={push.result} />
      </Section>
    </div>
  );
}

export default function Episodes() {
  const { data: episodes, setData, error, loading, reload } = useLoad(api.episodes);
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => { reload(); }, [reload]);
  const current = episodes?.find((e) => e.number === selected) ?? null;

  return (
    <>
      <PageHeader title="Zero Hour" intro="Episodes and their huddle cards." actions={<Button onClick={reload} busy={loading}>Refresh</Button>} />
      {error && !episodes && <p className="result result-error" role="alert">{error}</p>}
      {!episodes && !error && <Loading what="episodes" />}
      {episodes && (
        <div className="master-detail">
          <div className="master">
            <ul className="plain picker">
              {episodes.map((e) => (
                <li key={e.number}>
                  <button type="button" className="pick" aria-current={selected === e.number || undefined} onClick={() => setSelected(e.number)}>
                    <span className="row-title">EP {String(e.number).padStart(2, '0')} · {e.title}</span>
                    <span className="muted small">{e.hazard} · {formatPacific(e.release_at ?? e.released_at)}</span>
                    <EpisodePills e={e} />
                  </button>
                </li>
              ))}
              {episodes.length === 0 && <li className="muted">No episodes yet.</li>}
            </ul>
          </div>
          <div className="detail">
            {current ? (
              <EpisodeEditor key={current.number} ep={current} onSaved={(e) => setData((list) => list?.map((x) => (x.number === e.number ? e : x)))} />
            ) : (
              <p className="muted">Pick an episode to edit it.</p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
