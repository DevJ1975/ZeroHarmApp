import { useEffect, useState } from 'react';

import { api, detailText, JURISDICTIONS, jurisdictionCode, type FeedAdmin, type FeedInput, type FeedKind, type Jurisdiction } from '../api';
import { formatPacific, fromLocalInput, isFuture, toLocalInput } from '../time';
import {
  Button, ConfirmAction, Loading, PageHeader, Pill, ResultLine, Section, Select, StaleNote, TextArea, TextField, Toggle, useAction, useDraft, useLoad,
} from '../ui';

const KINDS: { value: FeedKind; label: string }[] = [
  { value: 'alert', label: 'Regulatory alert' },
  { value: 'course', label: 'Free course' },
  { value: 'tool', label: 'Free tool' },
  { value: 'video', label: 'Video' },
  { value: 'newsletter', label: 'Newsletter issue' },
];
const kindLabel = (k: FeedKind) => KINDS.find((x) => x.value === k)?.label ?? k;

/** Alerts go to people with Regulatory alerts on; everything else is promotional and goes to News and offers. */
export function feedAudience(kind: FeedKind) {
  return kind === 'alert' ? 'everyone with Regulatory alerts on' : 'everyone with News and offers on';
}

interface Draft {
  kind: FeedKind;
  title: string;
  summary: string;
  body_md: string;
  link_url: string;
  image_url: string;
  jurisdiction: Jurisdiction;
  effective_date: string;
  publish_at: string;
  expires_at: string;
  send_push: boolean;
  featured: boolean;
  published: boolean;
}

const EMPTY: Draft = {
  kind: 'alert', title: '', summary: '', body_md: '', link_url: '', image_url: '', jurisdiction: '', effective_date: '',
  publish_at: '', expires_at: '', send_push: false, featured: false, published: true,
};

function toDraft(f: FeedAdmin): Draft {
  return {
    kind: f.kind, title: f.title, summary: f.summary, body_md: f.body_md ?? '', link_url: f.link_url_raw ?? '', image_url: f.image_url ?? '',
    jurisdiction: jurisdictionCode(f.jurisdiction), effective_date: f.effective_date ?? '', publish_at: toLocalInput(f.publish_at),
    expires_at: toLocalInput(f.expires_at), send_push: f.send_push, featured: f.featured, published: f.published,
  };
}

const draftOf = (f: FeedAdmin | null) => (f ? toDraft(f) : EMPTY);

function toInput(d: Draft, only?: Draft): FeedInput {
  const out: Record<string, unknown> = {};
  (Object.keys(d) as (keyof Draft)[]).forEach((k) => {
    if (only && only[k] === d[k]) return;
    const v = d[k];
    if (k === 'publish_at') { if (v) out[k] = fromLocalInput(v as string); }
    else if (k === 'expires_at') out[k] = v ? fromLocalInput(v as string) : null;
    else if (k === 'effective_date') out[k] = v || null;
    else out[k] = v;
  });
  return out as FeedInput;
}

function problem(d: Draft): string {
  if (!d.title.trim()) return 'Give it a title.';
  for (const [label, v] of [['Link', d.link_url], ['Image', d.image_url]] as const) {
    if (v && !v.startsWith('https://')) return `${label} must start with https://`;
  }
  if (d.publish_at && d.expires_at && d.expires_at <= d.publish_at) return 'The end date must be after the start date.';
  return '';
}

function FeedPills({ f }: { f: FeedAdmin }) {
  return (
    <span className="pills">
      {f.live ? <Pill tone="green">Live</Pill> : !f.published ? <Pill tone="outline">Unpublished</Pill> : isFuture(f.publish_at) ? <Pill>Scheduled</Pill> : <Pill tone="outline">Ended</Pill>}
      {f.featured && <Pill>Featured</Pill>}
      {f.send_push && !f.push_sent_at && <Pill>Push on</Pill>}
      {f.push_sent_at && <Pill>Pushed</Pill>}
    </span>
  );
}

function FeedEditor({ item, onSaved, onCreated }: { item: FeedAdmin | null; onSaved: (f: FeedAdmin) => void; onCreated: (f: FeedAdmin) => void }) {
  // A new item is always "dirty", so nothing from the server ever replaces what you're typing.
  const { base, d, setD, dirty, stale, load } = useDraft(item, draftOf, (b, x) => (item ? Object.keys(toInput(x, b)).length > 0 : true));
  const [force, setForce] = useState(false);
  const save = useAction();
  const push = useAction();

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const patch = item ? toInput(d, base) : null;

  async function submit() {
    const p = problem(d);
    if (p) return save.setResult({ kind: 'error', text: p });
    if (!item) {
      const made = await save.run(() => api.createFeed(toInput(d)), (f) => `Created “${f.title}”. ${f.live ? 'It’s live now.' : `It goes live ${formatPacific(f.publish_at)}.`}`);
      if (made) onCreated(made);
      return;
    }
    if (!dirty) return save.setResult({ kind: 'info', text: 'Nothing to save.' });
    const saved = await save.run(() => api.updateFeed(item.id, patch!), 'Saved. Phones pick it up the next time the app opens.');
    if (saved) {
      load(saved);
      onSaved(saved);
    }
  }

  async function unpublish() {
    if (!item) return;
    const saved = await save.run(() => api.unpublishFeed(item.id), 'Unpublished. It’s gone from the app; you can publish it again anytime.');
    if (saved) {
      load(saved);
      onSaved(saved);
    }
  }

  async function sendPush() {
    if (!item) return;
    await push.run(() => api.pushFeed(item.id, force), (r) => (r.ok ? `Push sent. ${detailText(r.detail)}` : `OneSignal did not send it: ${detailText(r.detail)}`));
    // Re-read it, so "A push already went out" shows and a second push to the whole group is less likely.
    const fresh = await api.feedItem(item.id).catch(() => null);
    if (fresh) onSaved(fresh);
  }

  return (
    <div className="editor">
      <div className="editor-head">
        <h2>{item ? item.title : 'New alert or resource'}</h2>
        {item && (
          <p className="muted small">
            {kindLabel(item.kind)} · id {item.external_id} · starts {formatPacific(item.publish_at)}
          </p>
        )}
        {item && <FeedPills f={item} />}
      </div>

      <div className="form">
        <div className="form-row">
          <Select<FeedKind> label="Kind" value={d.kind} options={KINDS} onChange={(v) => set('kind', v)} />
          <Select<Jurisdiction> label="Jurisdiction" value={d.jurisdiction} options={JURISDICTIONS} onChange={(v) => set('jurisdiction', v)} />
        </div>
        <TextField label="Title" value={d.title} onChange={(v) => set('title', v)} max={200} />
        <TextArea label="Summary" rows={3} value={d.summary} onChange={(v) => set('summary', v)} hint="One or two plain sentences shown on the card." />
        <TextArea label="Details" rows={8} value={d.body_md} onChange={(v) => set('body_md', v)} hint="Optional. Leave a blank line between paragraphs." />
        <TextField label="Button link" type="url" value={d.link_url} onChange={(v) => set('link_url', v)} placeholder="https://"
          hint="Course, tool, video or source rule. The app adds src=zero-harm-app so GoHighLevel credits the lead." />
        <TextField label="Image link" type="url" value={d.image_url} onChange={(v) => set('image_url', v)} placeholder="https://" />
        {d.kind === 'alert' && (
          <TextField label="Rule takes effect" type="date" value={d.effective_date} onChange={(v) => set('effective_date', v)} />
        )}
        <div className="form-row">
          <TextField label="Show from (Pacific)" type="datetime-local" value={d.publish_at} onChange={(v) => set('publish_at', v)} hint={item ? undefined : 'Leave empty to show it now.'} />
          <TextField label="Show until (Pacific)" type="datetime-local" value={d.expires_at} onChange={(v) => set('expires_at', v)} hint="Optional." />
        </div>
        <Toggle label="Featured" checked={d.featured} onChange={(v) => set('featured', v)} hint="Pinned to the top of Learn." />
        <Toggle label="Send a push when it goes live" checked={d.send_push} onChange={(v) => set('send_push', v)} hint={`Goes to ${feedAudience(d.kind)}.`} />
        <Toggle label="Published" checked={d.published} onChange={(v) => set('published', v)} />
      </div>

      <div className="save-bar">
        <Button kind="primary" onClick={submit} busy={save.busy} disabled={!dirty}>{item ? 'Save changes' : 'Create'}</Button>
        {item && <Button kind="quiet" onClick={() => load(item)} disabled={!dirty}>Discard</Button>}
        {item && item.published && (
          <ConfirmAction kind="danger" label="Unpublish" confirmLabel="Yes, unpublish"
            message="It disappears from the app. Nothing is deleted, so you can publish it again." onConfirm={unpublish} busy={save.busy} />
        )}
        <ResultLine result={save.result} />
      </div>
      {item && stale && <StaleNote what="item" />}

      {item && (
        <Section title="Send push now">
          {item.push_sent_at && <p className="muted">A push already went out {formatPacific(item.push_sent_at)}.</p>}
          {!item.live && (
            <Toggle label="Send even though it isn’t live yet" checked={force} onChange={setForce}
              hint="Phones that tap it won’t find it yet. The scheduled push still goes out when it goes live, if that’s switched on." />
          )}
          <ConfirmAction label="Send push now" confirmLabel="Yes, send it"
            message={<p>This sends a notification to <strong>{feedAudience(item.kind)}</strong>. It can’t be taken back.</p>}
            onConfirm={sendPush} busy={push.busy} disabled={dirty || (!item.live && !force)} />
          {dirty && <p className="hint">Save your changes first.</p>}
          <ResultLine result={push.result} />
        </Section>
      )}
    </div>
  );
}

type Filter = 'all' | 'live' | 'scheduled' | 'off';

export default function Feed() {
  const { data: items, setData, error, loading, reload } = useLoad(api.feed);
  const [selected, setSelected] = useState<number | 'new' | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  useEffect(() => { reload(); }, [reload]);

  const shown = (items ?? []).filter((f) => {
    if (filter === 'live' && !f.live) return false;
    if (filter === 'scheduled' && !(f.published && isFuture(f.publish_at))) return false;
    if (filter === 'off' && f.live) return false;
    return `${f.title} ${f.summary}`.toLowerCase().includes(query.toLowerCase());
  });
  const current = typeof selected === 'number' ? items?.find((f) => f.id === selected) ?? null : null;

  return (
    <>
      <PageHeader title="Alerts & resources" intro="Regulatory alerts, free courses, tools, videos and newsletter issues on the Learn tab."
        actions={<>
          <Button onClick={reload} busy={loading}>Refresh</Button>
          <Button kind="primary" onClick={() => setSelected('new')}>New item</Button>
        </>} />
      {error && !items && <p className="result result-error" role="alert">{error}</p>}
      {!items && !error && <Loading what="alerts and resources" />}
      {items && (
        <div className="master-detail">
          <div className="master">
            <TextField label="Search" type="search" value={query} onChange={setQuery} />
            <Select<Filter> label="Show" value={filter} onChange={setFilter}
              options={[{ value: 'all', label: 'Everything' }, { value: 'live', label: 'Live now' }, { value: 'scheduled', label: 'Scheduled' }, { value: 'off', label: 'Not live' }]} />
            <ul className="plain picker">
              {shown.map((f) => (
                <li key={f.id}>
                  <button type="button" className="pick" aria-current={selected === f.id || undefined} onClick={() => setSelected(f.id)}>
                    <span className="row-title">{f.title}</span>
                    <span className="muted small">{kindLabel(f.kind)}{f.jurisdiction ? ` · ${f.jurisdiction}` : ''} · {formatPacific(f.publish_at)}</span>
                    <FeedPills f={f} />
                  </button>
                </li>
              ))}
              {shown.length === 0 && <li className="muted">Nothing matches.</li>}
            </ul>
          </div>
          <div className="detail">
            {selected === 'new' && (
              <FeedEditor item={null} onSaved={() => undefined}
                onCreated={(f) => { setData((list) => [f, ...(list ?? [])]); setSelected(f.id); }} />
            )}
            {current && (
              <FeedEditor key={current.id} item={current}
                onSaved={(f) => setData((list) => list?.map((x) => (x.id === f.id ? f : x)))} onCreated={() => undefined} />
            )}
            {selected === null && <p className="muted">Pick an item to edit it, or create a new one.</p>}
          </div>
        </div>
      )}
    </>
  );
}
