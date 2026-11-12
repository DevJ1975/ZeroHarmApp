import { useEffect, useState } from 'react';

import { api, type KbEntry, type KbInput, type KbKind } from '../api';
import { formatPacific } from '../time';
import { Button, ConfirmAction, Loading, PageHeader, Pill, ResultLine, Select, StaleNote, TextArea, TextField, Toggle, useAction, useDraft, useLoad, type Result } from '../ui';

interface Draft {
  kind: KbKind;
  title: string;
  body: string;
  source: string;
  tags: string;
  published: boolean;
}

export const KB_KINDS: { value: KbKind; label: string }[] = [
  { value: 'safety', label: 'Safety answer' },
  { value: 'support', label: 'App help' },
];

/** An entry from a web service that does not know about kinds yet is a safety entry, as every entry was. */
export const kindOf = (e: Pick<KbEntry, 'kind'>): KbKind => (e.kind === 'support' ? 'support' : 'safety');

/** App help is shown as written, so it has to fit on a phone screen. A guide, not a hard stop. */
export const SUPPORT_BODY_GUIDE = 700;

/**
 * The reason an entry can't be saved yet, or '' when it is fine. The server has one more rule, and it stays
 * there so it is written once: app help can't name an OSHA section number. Its sentence is shown as it comes.
 */
export function kbProblem(d: { title: string; body: string; source: string }): string {
  if (!d.title.trim() || !d.body.trim()) return 'An entry needs a title and text.';
  if (!d.source.trim()) return 'Add a source. OTIS cites it in every answer that uses this entry.';
  return '';
}

/**
 * A web service older than this console drops the kind without complaint. Returns what to tell the owner
 * when that happened ('' when the kind was kept), because app help saved as a safety entry gets mixed into safety answers.
 */
export function kindLost(asked: KbKind, got: Pick<KbEntry, 'kind'>): string {
  if (kindOf(got) === asked) return '';
  return 'Saved, but the kind did not change. The web service is older than this console. Deploy the backend, then set the kind again.';
}

const EMPTY: Draft = { kind: 'safety', title: '', body: '', source: '', tags: '', published: true };
const toDraft = (e: KbEntry): Draft => ({ kind: kindOf(e), title: e.title, body: e.body, source: e.source, tags: e.tags, published: e.published });

function changes(before: Draft, after: Draft): KbInput {
  const out: Record<string, unknown> = {};
  (Object.keys(after) as (keyof Draft)[]).forEach((k) => { if (after[k] !== before[k]) out[k] = after[k]; });
  return out as KbInput;
}

const draftOf = (e: KbEntry | null) => (e ? toDraft(e) : EMPTY);

function KbEditor({ entry, onSaved, onCreated }: { entry: KbEntry | null; onSaved: (e: KbEntry) => void; onCreated: (e: KbEntry, problem: string) => void }) {
  // A new entry is always "dirty", so nothing from the server ever replaces what you're typing.
  const { base, d, setD, dirty, stale, load } = useDraft(entry, draftOf, (b, x) => (entry ? Object.keys(changes(b, x)).length > 0 : true));
  const save = useAction();

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const patch = changes(base, d);
  const support = d.kind === 'support';

  async function submit() {
    const problem = kbProblem(d);
    if (problem) return save.setResult({ kind: 'error', text: problem });
    if (!entry) {
      const made = await save.run(() => api.createKb(d), 'Added. OTIS can use it once phones refresh their knowledge base.');
      // The new entry opens in its own editor, so anything to say about it is handed up with it.
      if (made) onCreated(made, kindLost(d.kind, made));
      return;
    }
    if (!dirty) return save.setResult({ kind: 'info', text: 'Nothing to save.' });
    const saved = await save.run(() => api.updateKb(entry.id, patch), 'Saved. OTIS picks it up the next time the app opens.');
    if (saved) {
      load(saved);
      onSaved(saved);
      const lost = patch.kind ? kindLost(patch.kind, saved) : '';
      if (lost) save.setResult({ kind: 'error', text: lost });
    }
  }

  async function unpublish() {
    if (!entry) return;
    const saved = await save.run(() => api.unpublishKb(entry.id), 'Unpublished. OTIS will stop using it once phones refresh.');
    if (saved) {
      load(saved);
      onSaved(saved);
    }
  }

  return (
    <div className="editor">
      <div className="editor-head">
        <h2>{entry ? entry.title : 'New OTIS entry'}</h2>
        {entry?.updated_at && <p className="muted small">Updated {formatPacific(entry.updated_at)}</p>}
      </div>
      {support ? (
        <div className="note note-warn">
          <strong>App help is shown word for word.</strong> When someone tells OTIS the app is not working, they see this text exactly as you wrote it.
          Try the steps on a phone before you save.
        </div>
      ) : (
        <div className="note note-warn">
          <strong>OTIS answers only from this text.</strong> Whatever you write here is what workers hear back, word for word in spirit.
          Check every fact against the source before you save.
        </div>
      )}
      <div className="form">
        <Select<KbKind> label="Kind" value={d.kind} options={KB_KINDS} onChange={(v) => set('kind', v)}
          hint={support
            ? 'App help: how to fix a problem with the app itself. Shown as written, and never used in a safety answer.'
            : 'Safety answer: OTIS uses it to answer safety questions. Never shown as app help.'} />
        <TextField label="Source (what OTIS cites)" value={d.source} onChange={(v) => set('source', v)} max={200}
          placeholder={support ? 'Zero Harm app help' : 'OSHA 1910.147'} hint={support ? 'Use “Zero Harm app help”. No OSHA section numbers like 1910.147: the weekly OSHA check would tie this entry to that rule.' : 'Shown with every answer. Name the standard, document or page.'} />
        <TextField label="Title" value={d.title} onChange={(v) => set('title', v)} max={200}
          hint={support ? 'The problem in the words people type, like “The app keeps closing”.' : undefined} />
        <TextArea label="Text" rows={12} value={d.body} onChange={(v) => set('body', v)} max={support ? SUPPORT_BODY_GUIDE : undefined}
          hint={support ? `One problem per entry. 2 to 6 short numbered steps. Keep it under ${SUPPORT_BODY_GUIDE} characters so it fits on a phone.` : 'Plain, short sentences. One topic per entry.'} />
        <TextField label="Search words" value={d.tags} onChange={(v) => set('tags', v)} max={200}
          hint={support
            ? 'Comma separated. The exact words people type, in English and in Spanish without accents, e.g. crash, frozen, stuck, se cierra, no funciona.'
            : 'Comma separated. Words workers might use, e.g. lockout, LOTO, tag.'} />
        <Toggle label="Published" checked={d.published} onChange={(v) => set('published', v)} />
      </div>
      <div className="save-bar">
        <Button kind="primary" onClick={submit} busy={save.busy} disabled={!dirty}>{entry ? 'Save changes' : 'Add entry'}</Button>
        {entry && <Button kind="quiet" onClick={() => load(entry)} disabled={!dirty}>Discard</Button>}
        {entry?.published && (
          <ConfirmAction kind="danger" label="Unpublish" confirmLabel="Yes, unpublish"
            message="OTIS stops using this entry. Nothing is deleted." onConfirm={unpublish} busy={save.busy} />
        )}
        <ResultLine result={save.result} />
      </div>
      {entry && stale && <StaleNote what="entry" />}
    </div>
  );
}

export default function Kb() {
  const { data: entries, setData, error, loading, reload } = useLoad(api.kb);
  const [selected, setSelected] = useState<number | 'new' | null>(null);
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<KbKind | 'all'>('all');
  const [note, setNote] = useState<Result>(null); // about the entry just added; cleared when another is picked
  useEffect(() => { reload(); }, [reload]);

  const q = query.toLowerCase();
  const shown = (entries ?? []).filter((e) => (kind === 'all' || kindOf(e) === kind) && `${e.title} ${e.source} ${e.tags} ${e.body}`.toLowerCase().includes(q));
  const current = typeof selected === 'number' ? entries?.find((e) => e.id === selected) ?? null : null;

  return (
    <>
      <PageHeader title="OTIS knowledge base"
        intro="The text the on-device assistant answers from. Released talks are added automatically. App help entries are shown word for word when someone says the app is not working."
        actions={<>
          <Button onClick={reload} busy={loading}>Refresh</Button>
          <Button kind="primary" onClick={() => { setSelected('new'); setNote(null); }}>New entry</Button>
        </>} />
      {error && !entries && <p className="result result-error" role="alert">{error}</p>}
      {!entries && !error && <Loading what="the knowledge base" />}
      {entries && (
        <div className="master-detail">
          <div className="master">
            <TextField label="Search" type="search" value={query} onChange={setQuery} placeholder="Title, source, words" />
            <Select<KbKind | 'all'> label="Show" value={kind} onChange={setKind}
              options={[{ value: 'all', label: 'Every kind' }, { value: 'safety', label: 'Safety answers' }, { value: 'support', label: 'App help' }]} />
            <p className="muted small">{shown.length} of {entries.length} entries</p>
            <ul className="plain picker">
              {shown.map((e) => (
                <li key={e.id}>
                  <button type="button" className="pick" aria-current={selected === e.id || undefined} onClick={() => { setSelected(e.id); setNote(null); }}>
                    <span className="row-title">{e.title}</span>
                    <span className="source-line">{e.source || 'No source'}</span>
                    <span className="pills">
                      {e.published ? <Pill tone="green">Published</Pill> : <Pill tone="outline">Unpublished</Pill>}
                      {kindOf(e) === 'support' && <Pill tone="neutral">App help</Pill>}
                      {!e.source && <Pill tone="red">Missing source</Pill>}
                    </span>
                  </button>
                </li>
              ))}
              {shown.length === 0 && <li className="muted">No entries match.</li>}
            </ul>
          </div>
          <div className="detail">
            <ResultLine result={note} />
            {selected === 'new' && (
              <KbEditor entry={null} onSaved={() => undefined}
                onCreated={(e, problem) => {
                  setData((list) => [e, ...(list ?? [])]);
                  setSelected(e.id);
                  setNote(problem ? { kind: 'error', text: problem } : { kind: 'ok', text: `Added “${e.title}”. OTIS can use it once phones refresh their knowledge base.` });
                }} />
            )}
            {current && (
              <KbEditor key={current.id} entry={current} onSaved={(e) => setData((list) => list?.map((x) => (x.id === e.id ? e : x)))} onCreated={() => undefined} />
            )}
            {selected === null && <p className="muted">Pick an entry to edit it, or add a new one.</p>}
          </div>
        </div>
      )}
    </>
  );
}
