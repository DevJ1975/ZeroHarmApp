import { useEffect, useState } from 'react';

import { api, detailText, type SpanishStatus, type TalkAdmin, type TalkPatch } from '../api';
import { formatPacific, fromLocalInput, toLocalInput } from '../time';
import {
  Button, ConfirmAction, Loading, PageHeader, Pill, ResultLine, Section, Select, StaleNote, TextArea, TextField, Toggle, useAction, useDraft, useLoad,
} from '../ui';
import TalkPreview from './TalkPreview';

/** Everything the editor can change, as plain strings and booleans. */
interface Draft {
  title: string;
  story_title: string;
  crew_question: string;
  body_md: string;
  month_theme: string;
  hero_url: string;
  pdf_url: string;
  send_at: string; // datetime-local value, Pacific
  published: boolean;
  needs_review: boolean;
  title_es: string;
  story_title_es: string;
  crew_question_es: string;
  body_md_es: string;
  spanish_status: SpanishStatus;
}

function toDraft(t: TalkAdmin): Draft {
  return {
    title: t.title, story_title: t.story_title, crew_question: t.crew_question, body_md: t.body_md ?? '',
    month_theme: t.month_theme, hero_url: t.hero_url ?? '', pdf_url: t.pdf_url ?? '', send_at: toLocalInput(t.send_at),
    published: t.published, needs_review: t.needs_review,
    title_es: t.title_es, story_title_es: t.story_title_es, crew_question_es: t.crew_question_es, body_md_es: t.body_md_es,
    spanish_status: t.spanish_status,
  };
}

/** Only the fields you changed are sent. */
function changes(before: Draft, after: Draft): TalkPatch {
  const patch: Record<string, unknown> = {};
  (Object.keys(after) as (keyof Draft)[]).forEach((k) => {
    if (after[k] !== before[k]) patch[k] = k === 'send_at' ? fromLocalInput(after.send_at) : after[k];
  });
  return patch as TalkPatch;
}

const isDirty = (before: Draft, after: Draft) => Object.keys(changes(before, after)).length > 0;

function urlProblem(d: Draft): string {
  for (const [label, v] of [['Hero image', d.hero_url], ['PDF', d.pdf_url]] as const) {
    if (v && !v.startsWith('https://')) return `${label} link must start with https://`;
  }
  return '';
}

export function TalkPills({ t }: { t: TalkAdmin }) {
  return (
    <span className="pills">
      {t.released ? <Pill tone="green">Live</Pill> : t.published ? <Pill>Scheduled</Pill> : <Pill tone="outline">Hidden</Pill>}
      {t.needs_review && <Pill tone="red">Needs review</Pill>}
      {t.spanish_status === 'draft' && <Pill tone="outline">Spanish draft</Pill>}
      {t.spanish_status === 'approved' && <Pill tone="green">Spanish approved</Pill>}
      {t.push_sent_at && <Pill>Pushed</Pill>}
    </span>
  );
}

function TalkEditor({ talk, onSaved }: { talk: TalkAdmin; onSaved: (t: TalkAdmin) => void }) {
  const { base, d, setD, dirty, stale, load } = useDraft(talk, toDraft, isDirty);
  const [tab, setTab] = useState<'en' | 'es' | 'status'>('en');
  const [previewLang, setPreviewLang] = useState<'en' | 'es'>('en');
  const [force, setForce] = useState(false);
  const save = useAction();
  const spanish = useAction();
  const push = useAction();

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const patch = changes(base, d);

  async function saveWith(extra: TalkPatch = {}, okText = 'Saved. Phones pick it up the next time the app opens.') {
    const problem = urlProblem(d);
    if (problem) return save.setResult({ kind: 'error', text: problem });
    const body = { ...patch, ...extra };
    if (Object.keys(body).length === 0) return save.setResult({ kind: 'info', text: 'Nothing to save.' });
    const saved = await save.run(() => api.updateTalk(talk.issue, body), okText);
    if (saved) {
      load(saved);
      onSaved(saved);
    }
  }

  async function approveSpanish() {
    if (!d.title_es.trim() || !d.body_md_es.trim()) {
      return save.setResult({ kind: 'error', text: 'Approving needs at least the Spanish title and talk text.' });
    }
    await saveWith({ spanish_status: 'approved' }, 'Spanish approved. The Español button now shows on this talk.');
  }

  async function draftSpanish() {
    const saved = await spanish.run(() => api.draftSpanish(talk.issue), 'Spanish draft ready. Review every line before you approve it.');
    if (saved) {
      load(saved);
      onSaved(saved);
      setPreviewLang('es');
    }
  }

  async function sendPush() {
    await push.run(() => api.pushTalk(talk.issue, force), (r) =>
      r.ok ? `Push sent. ${detailText(r.detail)}` : `OneSignal did not send it: ${detailText(r.detail)}`);
    const fresh = await api.talk(talk.issue).catch(() => null);
    if (fresh) onSaved(fresh);
  }

  const preview = previewLang === 'es'
    ? { number: talk.number, month_theme: d.month_theme, title: d.title_es, story_title: d.story_title_es, crew_question: d.crew_question_es, body_md: d.body_md_es, hero_url: d.hero_url, pdf_url: d.pdf_url }
    : { number: talk.number, month_theme: d.month_theme, title: d.title, story_title: d.story_title, crew_question: d.crew_question, body_md: d.body_md, hero_url: d.hero_url, pdf_url: d.pdf_url };

  return (
    <div className="editor-grid">
      <div className="editor">
        <div className="editor-head">
          <div>
            <h2>#{String(talk.number).padStart(2, '0')} · {talk.title}</h2>
            <p className="muted small">Issue dated {talk.issue_date} · Opens {formatPacific(talk.send_at)} · Updated {formatPacific(talk.updated_at)}</p>
            <TalkPills t={talk} />
          </div>
        </div>

        <div className="tabs" role="tablist" aria-label="Talk editor">
          {([['en', 'English'], ['es', 'Spanish'], ['status', 'Schedule & status']] as const).map(([id, label]) => (
            <button key={id} role="tab" type="button" aria-selected={tab === id} className="tab" onClick={() => { setTab(id); if (id !== 'status') setPreviewLang(id); }}>
              {label}
            </button>
          ))}
        </div>

        {tab === 'en' && (
          <div className="form" role="tabpanel">
            <TextField label="Title" value={d.title} onChange={(v) => set('title', v)} max={200} />
            <TextField label="Story title" value={d.story_title} onChange={(v) => set('story_title', v)} max={200} />
            <TextField label="Month theme" value={d.month_theme} onChange={(v) => set('month_theme', v)} max={80} />
            <TextArea label="Talk text" rows={14} value={d.body_md} onChange={(v) => set('body_md', v)}
              hint="Leave a blank line between paragraphs. Start a line with ## for a section heading." />
            <TextArea label="Crew question" rows={3} value={d.crew_question} onChange={(v) => set('crew_question', v)} />
            <TextField label="Hero image link" type="url" value={d.hero_url} onChange={(v) => set('hero_url', v)} placeholder="https://" />
            <TextField label="Printable PDF link" type="url" value={d.pdf_url} onChange={(v) => set('pdf_url', v)} placeholder="https://" />
          </div>
        )}

        {tab === 'es' && (
          <div className="form" role="tabpanel">
            <div className="note">
              <p>
                Spanish status: <strong>{d.spanish_status === 'approved' ? 'Approved, shown in the app' : d.spanish_status === 'draft' ? 'Draft, not shown yet' : 'No Spanish'}</strong>.
                The Español button appears in the app only after you approve.
              </p>
              <div className="row">
                {d.title_es || d.body_md_es ? (
                  <ConfirmAction kind="secondary" label="Draft Spanish with Claude" confirmLabel="Replace with a new draft"
                    message="This replaces the Spanish text below with a fresh machine draft and sets it back to Draft."
                    onConfirm={draftSpanish} busy={spanish.busy} disabled={dirty} />
                ) : (
                  <Button onClick={draftSpanish} busy={spanish.busy} disabled={dirty}>Draft Spanish with Claude</Button>
                )}
              </div>
              {dirty && <p className="hint">Save or discard your changes before drafting.</p>}
              <ResultLine result={spanish.result} />
            </div>
            <TextField label="Título" value={d.title_es} onChange={(v) => set('title_es', v)} max={200} />
            <TextField label="Título de la historia" value={d.story_title_es} onChange={(v) => set('story_title_es', v)} max={200} />
            <TextArea label="Texto de la charla" rows={14} value={d.body_md_es} onChange={(v) => set('body_md_es', v)} />
            <TextArea label="Pregunta para el equipo" rows={3} value={d.crew_question_es} onChange={(v) => set('crew_question_es', v)} />
            <div className="row">
              {d.spanish_status !== 'approved' ? (
                <ConfirmAction label="Approve Spanish" confirmLabel="Yes, approve and show it"
                  message="Have you read every line? Approving saves this text and shows the Español button to everyone."
                  onConfirm={approveSpanish} busy={save.busy} />
              ) : (
                <Button kind="secondary" onClick={() => saveWith({ spanish_status: 'draft' }, 'Spanish moved back to draft and hidden from the app.')} busy={save.busy}>
                  Hide Spanish (back to draft)
                </Button>
              )}
            </div>
          </div>
        )}

        {tab === 'status' && (
          <div className="form" role="tabpanel">
            <TextField label="Opens in the app (Pacific time)" type="datetime-local" value={d.send_at} onChange={(v) => set('send_at', v)}
              hint="Normally Sunday 11:59 AM, the day before the issue date." />
            <Toggle label="Published" checked={d.published} onChange={(v) => set('published', v)} hint="Off hides the talk from the app." />
            <Toggle label="Needs review" checked={d.needs_review} onChange={(v) => set('needs_review', v)} hint="On holds the talk out of the app until you clear it." />
            {talk.review_flags && (
              <div className="note note-warn">
                <strong>Review flags from GoHighLevel</strong>
                <pre className="flags">{talk.review_flags}</pre>
              </div>
            )}
            <Select<SpanishStatus> label="Spanish" value={d.spanish_status} onChange={(v) => set('spanish_status', v)}
              options={[{ value: 'none', label: 'No Spanish' }, { value: 'draft', label: 'Draft, needs review' }, { value: 'approved', label: 'Approved, shown in app' }]} />
          </div>
        )}

        <div className="save-bar">
          <Button kind="primary" onClick={() => saveWith()} busy={save.busy} disabled={!dirty}>Save changes</Button>
          <Button kind="quiet" onClick={() => load(talk)} disabled={!dirty}>Discard</Button>
          {dirty && <span className="muted small">Unsaved changes</span>}
          <ResultLine result={save.result} />
        </div>
        {stale && <StaleNote what="talk" />}

        <Section title="Send push now">
          <p className="muted">
            {talk.push_sent_at ? `A push for this talk already went out ${formatPacific(talk.push_sent_at)}.` : 'The Sunday push normally goes out on its own.'}
          </p>
          {!talk.released && (
            <Toggle label="Send even though the talk isn’t live yet" checked={force} onChange={setForce}
              hint="Phones that tap the notification will see “This talk isn’t available yet”. The scheduled Sunday push still goes out when the talk goes live." />
          )}
          <ConfirmAction label="Send push now" confirmLabel="Yes, send it"
            message={<p>This sends a notification to <strong>everyone with Weekly toolbox talk on</strong>. It can’t be taken back.</p>}
            onConfirm={sendPush} busy={push.busy} disabled={dirty || (!talk.released && !force)} />
          {dirty && <p className="hint">Save your changes first.</p>}
          <ResultLine result={push.result} />
        </Section>
      </div>

      <aside className="preview-col" aria-label="Preview">
        <div className="segmented" role="radiogroup" aria-label="Preview language">
          {(['en', 'es'] as const).map((l) => (
            <button key={l} type="button" role="radio" aria-checked={previewLang === l} onClick={() => setPreviewLang(l)}>
              {l === 'en' ? 'English' : 'Español'}
            </button>
          ))}
        </div>
        <TalkPreview talk={preview} lang={previewLang} />
        {previewLang === 'es' && d.spanish_status !== 'approved' && <p className="hint">Not shown in the app until approved.</p>}
      </aside>
    </div>
  );
}

export default function Talks() {
  const { data: talks, setData, error, loading, reload } = useLoad(api.talks);
  const [selected, setSelected] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  useEffect(() => { reload(); }, [reload]);

  const shown = (talks ?? []).filter((t) => `${t.number} ${t.title} ${t.month_theme}`.toLowerCase().includes(query.toLowerCase()));
  const current = talks?.find((t) => t.issue === selected) ?? null;

  function replace(t: TalkAdmin) {
    setData((list) => list?.map((x) => (x.issue === t.issue ? t : x)));
  }

  return (
    <>
      <PageHeader title="Talks" intro="Edit the weekly toolbox talks, approve Spanish, and send the push."
        actions={<Button onClick={reload} busy={loading}>Refresh</Button>} />
      {error && !talks && <p className="result result-error" role="alert">{error}</p>}
      {!talks && !error && <Loading what="talks" />}
      {talks && (
        <div className="master-detail">
          <div className="master">
            <TextField label="Find a talk" type="search" value={query} onChange={setQuery} placeholder="Number, title or theme" />
            <ul className="plain picker">
              {shown.map((t) => (
                <li key={t.issue}>
                  <button type="button" className="pick" aria-current={selected === t.issue || undefined} onClick={() => setSelected(t.issue)}>
                    <span className="row-title">#{String(t.number).padStart(2, '0')} {t.title}</span>
                    <span className="muted small">{formatPacific(t.send_at)}</span>
                    <TalkPills t={t} />
                  </button>
                </li>
              ))}
              {shown.length === 0 && <li className="muted">No talks match.</li>}
            </ul>
          </div>
          <div className="detail">
            {current ? <TalkEditor key={current.issue} talk={current} onSaved={replace} /> : <p className="muted">Pick a talk to edit it.</p>}
          </div>
        </div>
      )}
    </>
  );
}
