import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

import {
  api, type CrashReport, type Ticket, type TicketFilter, type TicketKind, type TicketKindFilter, type TicketPatch,
  type TicketSource, type TicketStatus, type TicketStatusFilter,
} from '../api';
import { formatPacific } from '../time';
import { Button, errorText, Loading, PageHeader, Pill, ResultLine, Section, Select, StaleNote, TextArea, useAction, useDraft, type Result, type Tone } from '../ui';

export const DEFAULT_FILTER: TicketFilter = { status: 'open', kind: 'all' };

/** The server's caps for the reply and the private note. Checked here too, so a long one is caught before it is sent. */
export const MAX_REPLY = 2000;
export const MAX_NOTE = 2000;
/** The most tickets one list answer holds (LIST_LIMIT in backend/support/console.py). A full list may be hiding older ones. */
export const LIST_LIMIT = 200;

const STATUSES: { value: TicketStatus; label: string }[] = [
  { value: 'new', label: 'New' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'fixed', label: 'Fixed' },
  { value: 'closed', label: 'Closed' },
];

const STATUS_FILTERS: { value: TicketStatusFilter; label: string }[] = [
  { value: 'open', label: 'Open (new and in progress)' },
  ...STATUSES,
  { value: 'all', label: 'All tickets' },
];

const KIND_FILTERS: { value: TicketKindFilter; label: string }[] = [
  { value: 'all', label: 'Every kind' },
  { value: 'problem', label: 'Problems people reported' },
  { value: 'answer', label: 'OTIS answers people flagged' },
  { value: 'crash', label: 'Crashes' },
];

const KIND_LABEL: Record<TicketKind, string> = { problem: 'Reported problem', answer: 'Flagged OTIS answer', crash: 'Crash' };

const SOURCE_TEXT: Record<TicketSource, string> = {
  otis: 'Reported in the OTIS chat',
  form: 'Sent from the Report a problem screen',
  otis_answer: 'Flagged with “Report this answer”',
  crash: 'Sent by the app on its own',
};

const STATUS_TONE: Record<TicketStatus, Tone> = { new: 'red', in_progress: 'neutral', fixed: 'green', closed: 'outline' };

export const statusLabel = (s: TicketStatus) => STATUSES.find((x) => x.value === s)?.label ?? s;

/**
 * The words the phone's My reports screen shows for each status (STATUS in app/my-reports.tsx). They differ from the
 * console's own labels for two of them, so a save quotes these: the owner is told what the person actually reads.
 */
export const PHONE_STATUS: Record<TicketStatus, string> = { new: 'Received', in_progress: 'Being looked at', fixed: 'Fixed', closed: 'Closed' };

/**
 * Whether the status and the reply reach the phone that sent the ticket (its My reports screen).
 * True only for a reported problem: /api/v2/support/mine lists kind "problem" and nothing else (backend/support/api.py),
 * and the phone does not keep flagged answers in My reports. A reply on a flagged answer or a crash is read by no one.
 */
export const inMyReports = (t: Pick<Ticket, 'kind'>) => t.kind === 'problem';

/** The text the server stores for a flagged answer when the person added no note (FLAGGED_ANSWER in backend/support/api.py). */
export const FLAGGED_ANSWER = 'Flagged OTIS answer';

const QUESTION_TITLE = 70;

/**
 * The name a ticket is listed under. Every flagged answer arrives with the same title, so those are named by the start
 * of the question instead, which is what tells one from another.
 */
export function ticketTitle(t: Pick<Ticket, 'kind' | 'title' | 'question'>): string {
  const q = t.kind === 'answer' ? (t.question ?? '').replace(/\s+/g, ' ').trim() : '';
  if (!q) return t.title;
  // Counted by characters (code points), not UTF-16 units, so the cut never splits an emoji in half.
  const chars = Array.from(q);
  return `“${chars.length > QUESTION_TITLE ? `${chars.slice(0, QUESTION_TITLE - 1).join('').trimEnd()}…` : q}”`;
}

/** The same rule the server uses for its filters, so a ticket leaves the list as soon as a save moves it out. */
export function ticketMatches(t: Pick<Ticket, 'status' | 'kind'>, f: TicketFilter): boolean {
  const statusOk = f.status === 'all' || (f.status === 'open' ? t.status === 'new' || t.status === 'in_progress' : t.status === f.status);
  return statusOk && (f.kind === 'all' || t.kind === f.kind);
}

export interface TicketDraft {
  status: TicketStatus;
  reply: string;
  owner_note: string;
}

const toDraft = (t: Ticket): TicketDraft => ({ status: t.status, reply: t.reply, owner_note: t.owner_note });

/** Only what changed is sent, so saving a note never rewrites a status someone set in the Django admin meanwhile. */
export function ticketChanges(before: TicketDraft, after: TicketDraft): TicketPatch {
  const out: TicketPatch = {};
  if (after.status !== before.status) out.status = after.status;
  if (after.reply !== before.reply) out.reply = after.reply;
  if (after.owner_note !== before.owner_note) out.owner_note = after.owner_note;
  return out;
}

const isDirty = (base: TicketDraft, d: TicketDraft) => Object.keys(ticketChanges(base, d)).length > 0;

/** Says what a save did, and above all whether anything now shows on the person's phone. */
export function savedText(patch: TicketPatch, t: Ticket): string {
  const out = ['Saved.'];
  if (inMyReports(t)) {
    if (patch.status) out.push(`The person sees “${PHONE_STATUS[t.status] ?? statusLabel(t.status)}” in My reports.`);
    if (patch.reply !== undefined) {
      out.push(t.reply.trim() ? 'The person sees your reply the next time they open My reports in the app.' : 'The reply is no longer shown in the app.');
    }
  } else if (t.kind === 'answer' && (patch.reply !== undefined || patch.status)) {
    out.push('The person does not see this. The app shows only reported problems under My reports, not flagged answers.');
  }
  if (patch.owner_note !== undefined && patch.reply === undefined) out.push('Your private note stays here. It is not sent to the phone.');
  return out.join(' ');
}

const PLATFORM: Record<string, string> = { ios: 'iPhone or iPad (iOS)', android: 'Android' };

/** "Pixel 8 · Android 15 · app 1.4.0", leaving out whatever the phone did not send. */
export function deviceLine(x: { device: string; platform: string; os_version: string; app_version: string }): string {
  const os = [PLATFORM[x.platform] ?? x.platform, x.os_version].filter(Boolean).join(' ');
  return [x.device, os, x.app_version && `app ${x.app_version}`].filter(Boolean).join(' · ') || 'The phone did not say';
}

/** A crash's count next to how many of its reports the server still holds. */
export function crashCountText(count: number, kept: number): string {
  const times = count === 1 ? 'Happened once.' : `Happened ${count} times.`;
  if (kept >= count) return times;
  return `${times} The ${kept === 1 ? 'one report' : `${kept} reports`} below ${kept === 1 ? 'is' : 'are'} what is kept. The rest are counted, not stored.`;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function From({ t }: { t: Ticket }) {
  if (t.kind === 'crash') return <>No one. The app sent this on its own, with no name, email or message.</>;
  return (
    <>
      {t.name || 'No name given'}
      {t.email && t.may_contact && <> · <a href={`mailto:${t.email}`}>{t.email}</a> (said OK to reply by email)</>}
      {t.email && !t.may_contact && ' · gave an email but did not say OK to use it. Do not email them.'}
      {!t.email && ' · no email given'}
    </>
  );
}

/** Everything the phone sent. Read only. */
export function TicketBody({ t }: { t: Ticket }) {
  return (
    <Section title={t.kind === 'crash' ? 'The error' : t.kind === 'answer' ? 'The OTIS answer they flagged' : 'What the person wrote'}>
      {t.kind === 'answer' && (
        <>
          <h3 className="quote-label">Their question</h3>
          <p className="quote">{t.question || 'The question was not sent.'}</p>
          <h3 className="quote-label">What OTIS answered</h3>
          <p className="quote">{t.answer || 'The answer was not sent.'}</p>
          <h3 className="quote-label">Their note</h3>
        </>
      )}
      {t.kind === 'answer' && (!t.text || t.text === FLAGGED_ANSWER)
        ? <p className="muted">No note. The person flagged the answer without writing anything.</p>
        : <p className={t.kind === 'crash' ? 'quote mono' : 'quote'}>{t.text || 'Nothing written.'}</p>}
      <dl className="facts">
        <Fact label="From"><From t={t} /></Fact>
        <Fact label="How">{SOURCE_TEXT[t.source] ?? t.source}</Fact>
        <Fact label="Phone">{deviceLine(t)}</Fact>
        {t.screen && <Fact label="Screen"><code>{t.screen}</code></Fact>}
        {t.lang && t.kind !== 'crash' && <Fact label="Language">{t.lang === 'es' ? 'Spanish' : t.lang === 'en' ? 'English' : t.lang}</Fact>}
        {t.kind === 'answer' && t.model_key && <Fact label="OTIS model"><code>{t.model_key}</code></Fact>}
        <Fact label={t.kind === 'crash' ? 'First seen' : 'Sent'}>{formatPacific(t.created_at)}</Fact>
        {t.kind === 'crash' && <Fact label="Last seen">{formatPacific(t.last_seen ?? t.created_at)}</Fact>}
      </dl>
    </Section>
  );
}

/** The individual reports behind one crash ticket. crashes is null while they load. */
export function CrashReports({ t, crashes, error }: { t: Ticket; crashes: CrashReport[] | null; error: string }) {
  return (
    <Section title="Each time it happened">
      {error && <p className="result result-error" role="alert">{error}</p>}
      {!crashes && !error && <Loading what="the crash reports" />}
      {crashes && (
        <>
          <p className="muted">{crashCountText(t.count, crashes.length)}</p>
          <ul className="plain crashes">
            {crashes.map((c, i) => (
              <li key={`${c.created_at}-${i}`} className="crash">
                <div className="row">
                  <span className="row-title">{formatPacific(c.created_at)}</span>
                  {c.fatal ? <Pill tone="red">The app stopped</Pill> : <Pill tone="outline">The app kept running</Pill>}
                </div>
                <p className="mono">{c.name}{c.message && `: ${c.message}`}</p>
                <p className="muted small">{deviceLine(c)}{c.screen && <> · on <code>{c.screen}</code></>}</p>
                {c.stack && (
                  <details>
                    <summary>Where in the code</summary>
                    <pre className="stack">{c.stack}</pre>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </Section>
  );
}

export function TicketEditor({ ticket, crashes, crashError, onSaved }: {
  ticket: Ticket;
  crashes: CrashReport[] | null;
  crashError: string;
  onSaved: (t: Ticket) => void;
}) {
  const { base, d, setD, dirty, stale, load } = useDraft(ticket, toDraft, isDirty);
  const save = useAction();
  const set = <K extends keyof TicketDraft>(k: K, v: TicketDraft[K]) => setD((x) => ({ ...x, [k]: v }));
  const person = inMyReports(ticket);

  async function submit() {
    if (!dirty) return save.setResult({ kind: 'info', text: 'Nothing to save.' });
    if (d.reply.length > MAX_REPLY) return save.setResult({ kind: 'error', text: `The reply is too long. Keep it under ${MAX_REPLY} characters.` });
    if (d.owner_note.length > MAX_NOTE) return save.setResult({ kind: 'error', text: `The private note is too long. Keep it under ${MAX_NOTE} characters.` });
    const patch = ticketChanges(base, d);
    const saved = await save.run(() => api.updateTicket(ticket.id, patch), (t) => savedText(patch, t));
    if (saved) {
      load(saved);
      onSaved(saved);
    }
  }

  return (
    <div className="editor">
      <div className="editor-head">
        <h2>{ticket.number} · {ticketTitle(ticket)}</h2>
        <div className="pills">
          <Pill tone="neutral">{KIND_LABEL[ticket.kind] ?? ticket.kind}</Pill>
          <Pill tone={STATUS_TONE[ticket.status] ?? 'neutral'}>{statusLabel(ticket.status)}</Pill>
          {ticket.kind === 'crash' && <Pill tone="outline">{ticket.count === 1 ? 'Once' : `${ticket.count} times`}</Pill>}
        </div>
        <p className="muted small">Updated {formatPacific(ticket.updated_at)}</p>
      </div>

      <TicketBody t={ticket} />
      {ticket.kind === 'crash' && <CrashReports t={ticket} crashes={crashes} error={crashError} />}

      <Section title="Your side">
        <div className="form">
          <Select<TicketStatus> label="Status" value={d.status} options={STATUSES} onChange={(v) => set('status', v)}
            hint={person
              ? 'The person sees this status in the app, under My reports.'
              : ticket.kind === 'crash'
                // The server's rule for a crash that is reported again (backend/support/api.py): only a Closed ticket reopens.
                ? 'Only you see this status. Fixed and Closed take it off the open list. A Fixed crash keeps counting but stays Fixed. A Closed one opens again as New if it comes back.'
                : 'Only you see this status. Fixed and Closed take it off the open list. The person is not shown it.'} />

          {person ? (
            <div className="goes-out">
              <p className="goes-label"><Pill tone="neutral">The person sees this</Pill></p>
              <TextArea label="Reply to the person" rows={5} max={MAX_REPLY} value={d.reply} onChange={(v) => set('reply', v)}
                hint="Shown in the app under My reports, on the phone that sent this ticket. Use plain words. Leave it empty to send no reply." />
            </div>
          ) : (
            <>
              <p className="note">
                {ticket.kind === 'crash'
                  ? 'There is no reply box here. The app sent this on its own, so there is no person to answer.'
                  : 'There is no reply box here. The person never sees anything you write on a flagged answer: the app does not list flagged answers under My reports. Use the private note below for your own tracking.'}
              </p>
              {ticket.reply.trim() && (
                <div className="stays-here">
                  <p className="goes-label"><Pill tone="outline">The person never saw this</Pill></p>
                  <p className="quote">{ticket.reply}</p>
                  <p className="hint">A reply was saved on this ticket earlier. It was never shown in the app. Treat it as a private note.</p>
                </div>
              )}
            </>
          )}

          <div className="stays-here">
            <p className="goes-label"><Pill tone="outline">Only you see this</Pill></p>
            <TextArea label="Private note" rows={4} max={MAX_NOTE} value={d.owner_note} onChange={(v) => set('owner_note', v)}
              hint="For your own tracking. It is never sent to the phone or to anyone else." />
          </div>
        </div>
      </Section>

      <div className="save-bar">
        <Button kind="primary" onClick={submit} busy={save.busy} disabled={!dirty}>Save changes</Button>
        <Button kind="quiet" onClick={() => load(ticket)} disabled={!dirty}>Discard</Button>
        <ResultLine result={save.result} />
      </div>
      {stale && <StaleNote what="ticket" />}
    </div>
  );
}

/** The ticket open in the detail pane. It stays open after a save moves it out of the filtered list. */
interface Open {
  ticket: Ticket;
  crashes: CrashReport[] | null;
  error: string;
}

// The same ticket fetched twice arrives as two objects. Keeping the first one when nothing differs
// stops the editor from saying "changed on the server" when it did not.
const same = (a: Ticket, b: Ticket) => JSON.stringify(a) === JSON.stringify(b);

export default function Tickets() {
  const [filter, setFilter] = useState<TicketFilter>(DEFAULT_FILTER);
  const [tickets, setTickets] = useState<Ticket[] | undefined>(undefined);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState<Open | null>(null);
  const [last, setLast] = useState<Result>(null);
  // Answers can come back out of order when a filter is changed quickly. Only the newest request counts.
  const listRequest = useRef(0);
  const openRequest = useRef(0);

  const loadList = useCallback(async (f: TicketFilter) => {
    const mine = ++listRequest.current;
    setLoading(true);
    try {
      const list = await api.tickets(f);
      if (mine !== listRequest.current) return;
      setTickets(list);
      setError('');
    } catch (e) {
      if (mine === listRequest.current) setError(errorText(e));
    } finally {
      if (mine === listRequest.current) setLoading(false);
    }
  }, []);

  const loadOne = useCallback(async (id: number) => {
    const mine = ++openRequest.current;
    try {
      const got = await api.ticket(id);
      if (mine !== openRequest.current) return;
      setOpen((o) => (o && o.ticket.id === id ? { ticket: same(o.ticket, got.ticket) ? o.ticket : got.ticket, crashes: got.crashes ?? [], error: '' } : o));
      setTickets((list) => list?.map((x) => (x.id === id && !same(x, got.ticket) ? got.ticket : x)));
    } catch (e) {
      if (mine !== openRequest.current) return;
      setOpen((o) => (o && o.ticket.id === id ? { ...o, error: errorText(e) } : o));
    }
  }, []);

  useEffect(() => { loadList(DEFAULT_FILTER); }, [loadList]);

  function changeFilter(next: TicketFilter) {
    setFilter(next);
    setLast(null);
    loadList(next);
  }

  function pick(t: Ticket) {
    setLast(null);
    setOpen({ ticket: t, crashes: null, error: '' });
    loadOne(t.id);
  }

  function refresh() {
    loadList(filter);
    if (open) loadOne(open.ticket.id);
  }

  function saved(t: Ticket) {
    // A fetch of this ticket that started before the save still holds the old copy. Drop its answer,
    // and ask again only if the crash reports had not arrived yet.
    openRequest.current++;
    if (open && open.ticket.id === t.id && open.crashes === null) loadOne(t.id);
    setTickets((list) => list?.map((x) => (x.id === t.id ? t : x)));
    setOpen((o) => (o && o.ticket.id === t.id ? { ...o, ticket: t } : o));
    // A status change can take the ticket out of the filtered list, so say where it went.
    setLast(ticketMatches(t, filter) ? null : { kind: 'info', text: `${t.number} is now ${statusLabel(t.status)}, so it left this list. It stays open on the right until you pick another ticket.` });
  }

  const shown = (tickets ?? []).filter((t) => ticketMatches(t, filter));

  return (
    <>
      <PageHeader title="Support tickets"
        intro="Problems people reported from the app, OTIS answers they flagged, and crashes the app reported on its own."
        actions={<Button onClick={refresh} busy={loading}>Refresh</Button>} />
      {error && <p className="result result-error" role="alert">{error}</p>}
      {!tickets && !error && <Loading what="tickets" />}
      {tickets && (
        <div className="filters filters-two">
          <Select<TicketStatusFilter> label="Show" value={filter.status} options={STATUS_FILTERS} onChange={(status) => changeFilter({ ...filter, status })} />
          <Select<TicketKindFilter> label="Kind" value={filter.kind} options={KIND_FILTERS} onChange={(kind) => changeFilter({ ...filter, kind })} />
        </div>
      )}
      {tickets && (
        <div className="master-detail">
          <div className="master">
            <p className="muted small" role="status">{loading ? 'Loading…' : `${shown.length} ticket${shown.length === 1 ? '' : 's'}`}</p>
            {tickets.length >= LIST_LIMIT && <p className="hint">Only the {LIST_LIMIT} most recent are listed. Narrow the list with Show and Kind to find older ones.</p>}
            <ResultLine result={last} />
            <ul className="plain picker">
              {shown.map((t) => (
                <li key={t.id}>
                  <button type="button" className="pick" aria-current={open?.ticket.id === t.id || undefined} onClick={() => pick(t)}>
                    <span className="row-title">{t.number} · {ticketTitle(t)}</span>
                    <span className="muted small">{KIND_LABEL[t.kind] ?? t.kind} · {formatPacific(t.last_seen ?? t.created_at)}</span>
                    <span className="pills">
                      <Pill tone={STATUS_TONE[t.status] ?? 'neutral'}>{statusLabel(t.status)}</Pill>
                      {t.kind === 'crash' && t.count > 1 && <Pill tone="outline">{t.count} times</Pill>}
                      {inMyReports(t) && !t.reply && <Pill tone="outline">No reply yet</Pill>}
                    </span>
                  </button>
                </li>
              ))}
              {shown.length === 0 && <li className="muted">{filter.status === 'open' && filter.kind === 'all' ? 'No open tickets. Nothing is waiting on you.' : 'No tickets here.'}</li>}
            </ul>
          </div>
          <div className="detail">
            {open
              ? <TicketEditor key={open.ticket.id} ticket={open.ticket} crashes={open.crashes} crashError={open.error} onSaved={saved} />
              : <p className="muted">Pick a ticket to read it, change its status, or reply.</p>}
          </div>
        </div>
      )}
    </>
  );
}
