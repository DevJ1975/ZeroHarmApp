import { useEffect, useState } from 'react';

import { api, type KbEntry, type KbInput } from '../api';
import { formatPacific } from '../time';
import { Button, ConfirmAction, Loading, PageHeader, Pill, ResultLine, StaleNote, TextArea, TextField, Toggle, useAction, useDraft, useLoad } from '../ui';

interface Draft {
  title: string;
  body: string;
  source: string;
  tags: string;
  published: boolean;
}

const EMPTY: Draft = { title: '', body: '', source: '', tags: '', published: true };
const toDraft = (e: KbEntry): Draft => ({ title: e.title, body: e.body, source: e.source, tags: e.tags, published: e.published });

function changes(before: Draft, after: Draft): KbInput {
  const out: Record<string, unknown> = {};
  (Object.keys(after) as (keyof Draft)[]).forEach((k) => { if (after[k] !== before[k]) out[k] = after[k]; });
  return out as KbInput;
}

const draftOf = (e: KbEntry | null) => (e ? toDraft(e) : EMPTY);

function KbEditor({ entry, onSaved, onCreated }: { entry: KbEntry | null; onSaved: (e: KbEntry) => void; onCreated: (e: KbEntry) => void }) {
  // A new entry is always "dirty", so nothing from the server ever replaces what you're typing.
  const { base, d, setD, dirty, stale, load } = useDraft(entry, draftOf, (b, x) => (entry ? Object.keys(changes(b, x)).length > 0 : true));
  const save = useAction();

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const patch = changes(base, d);

  async function submit() {
    if (!d.title.trim() || !d.body.trim()) return save.setResult({ kind: 'error', text: 'An entry needs a title and text.' });
    if (!d.source.trim()) return save.setResult({ kind: 'error', text: 'Add a source. OTIS cites it in every answer that uses this entry.' });
    if (!entry) {
      const made = await save.run(() => api.createKb(d), 'Added. OTIS can use it once phones refresh their knowledge base.');
      if (made) onCreated(made);
      return;
    }
    if (!dirty) return save.setResult({ kind: 'info', text: 'Nothing to save.' });
    const saved = await save.run(() => api.updateKb(entry.id, patch), 'Saved. OTIS picks it up the next time the app opens.');
    if (saved) {
      load(saved);
      onSaved(saved);
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
      <div className="note note-warn">
        <strong>OTIS answers only from this text.</strong> Whatever you write here is what workers hear back, word for word in spirit.
        Check every fact against the source before you save.
      </div>
      <div className="form">
        <TextField label="Source (what OTIS cites)" value={d.source} onChange={(v) => set('source', v)} max={200}
          placeholder="OSHA 1910.147 or Zero Harm app help" hint="Shown with every answer. Name the standard, document or page." />
        <TextField label="Title" value={d.title} onChange={(v) => set('title', v)} max={200} />
        <TextArea label="Text" rows={12} value={d.body} onChange={(v) => set('body', v)} hint="Plain, short sentences. One topic per entry." />
        <TextField label="Search words" value={d.tags} onChange={(v) => set('tags', v)} max={200} hint="Comma separated. Words workers might use, e.g. lockout, LOTO, tag." />
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
  useEffect(() => { reload(); }, [reload]);

  const q = query.toLowerCase();
  const shown = (entries ?? []).filter((e) => `${e.title} ${e.source} ${e.tags} ${e.body}`.toLowerCase().includes(q));
  const current = typeof selected === 'number' ? entries?.find((e) => e.id === selected) ?? null : null;

  return (
    <>
      <PageHeader title="OTIS knowledge base" intro="The text the on-device assistant answers from. Released talks are added automatically."
        actions={<>
          <Button onClick={reload} busy={loading}>Refresh</Button>
          <Button kind="primary" onClick={() => setSelected('new')}>New entry</Button>
        </>} />
      {error && !entries && <p className="result result-error" role="alert">{error}</p>}
      {!entries && !error && <Loading what="the knowledge base" />}
      {entries && (
        <div className="master-detail">
          <div className="master">
            <TextField label="Search" type="search" value={query} onChange={setQuery} placeholder="Title, source, words" />
            <p className="muted small">{shown.length} of {entries.length} entries</p>
            <ul className="plain picker">
              {shown.map((e) => (
                <li key={e.id}>
                  <button type="button" className="pick" aria-current={selected === e.id || undefined} onClick={() => setSelected(e.id)}>
                    <span className="row-title">{e.title}</span>
                    <span className="source-line">{e.source || 'No source'}</span>
                    <span className="pills">
                      {e.published ? <Pill tone="green">Published</Pill> : <Pill tone="outline">Unpublished</Pill>}
                      {!e.source && <Pill tone="red">Missing source</Pill>}
                    </span>
                  </button>
                </li>
              ))}
              {shown.length === 0 && <li className="muted">No entries match.</li>}
            </ul>
          </div>
          <div className="detail">
            {selected === 'new' && (
              <KbEditor entry={null} onSaved={() => undefined}
                onCreated={(e) => { setData((list) => [e, ...(list ?? [])]); setSelected(e.id); }} />
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
