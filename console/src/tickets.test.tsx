import { readFileSync } from 'node:fs';

import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';

import type { CrashReport, Ticket } from './api';
import {
  crashCountText, CrashReports, DEFAULT_FILTER, deviceLine, FLAGGED_ANSWER, inMyReports, LIST_LIMIT, MAX_NOTE, MAX_REPLY, PHONE_STATUS, savedText,
  statusLabel, TicketBody, ticketChanges, TicketEditor, ticketMatches, ticketTitle,
} from './screens/Tickets';

const problem: Ticket = {
  id: 12, number: 'ZH-12', kind: 'problem', status: 'new', source: 'form', title: 'The app closes', text: 'The app closes when I open a talk.\nEvery time.',
  reply: '', owner_note: '', count: 1, app_version: '1.4.0', platform: 'android', os_version: '15', device: 'Pixel 8', screen: '/talk/[id]',
  lang: 'es', name: 'Sam', email: 'sam@example.com', may_contact: true, created_at: '2026-11-10T18:00:00Z', updated_at: '2026-11-10T18:05:00Z', last_seen: null,
};

const crash: Ticket = {
  ...problem, id: 13, number: 'ZH-13', kind: 'crash', source: 'crash', title: 'TypeError: x is undefined', text: 'TypeError: x is undefined',
  count: 340, name: '', email: '', may_contact: false, lang: '', platform: 'ios', os_version: '26.1', device: 'iPhone 17', last_seen: '2026-11-11T02:00:00Z',
};

const flagged: Ticket = {
  ...problem, id: 14, number: 'ZH-14', kind: 'answer', source: 'otis_answer', title: 'Flagged OTIS answer', text: 'This is wrong for scaffolds.',
  name: '', email: '', may_contact: false, question: 'How high before I need a harness?', answer: 'At 6 feet in construction.', model_key: 'gemma-3n-e2b',
};

const report: CrashReport = {
  created_at: '2026-11-11T02:00:00Z', fatal: true, name: 'TypeError', message: 'x is undefined', stack: 'at open (talk.tsx:10)\nat press (list.tsx:4)',
  screen: '/talk/[id]', app_version: '1.4.0', platform: 'ios', os_version: '26.1', device: 'iPhone 17',
};

const html = (node: ReactElement) => renderToStaticMarkup(node);
const noop = () => undefined;

describe('ticket filters', () => {
  test('the screen starts on open tickets of every kind', () => {
    expect(DEFAULT_FILTER).toEqual({ status: 'open', kind: 'all' });
  });

  test('"open" means new and in progress, nothing else', () => {
    const open = { status: 'open', kind: 'all' } as const;
    expect(ticketMatches({ status: 'new', kind: 'problem' }, open)).toBe(true);
    expect(ticketMatches({ status: 'in_progress', kind: 'crash' }, open)).toBe(true);
    expect(ticketMatches({ status: 'fixed', kind: 'problem' }, open)).toBe(false);
    expect(ticketMatches({ status: 'closed', kind: 'answer' }, open)).toBe(false);
  });

  test('a single status matches only itself, and "all" matches every status', () => {
    for (const s of ['new', 'in_progress', 'fixed', 'closed'] as const) {
      expect(ticketMatches({ status: s, kind: 'problem' }, { status: s, kind: 'all' })).toBe(true);
      expect(ticketMatches({ status: s, kind: 'problem' }, { status: 'all', kind: 'all' })).toBe(true);
    }
    expect(ticketMatches({ status: 'new', kind: 'problem' }, { status: 'fixed', kind: 'all' })).toBe(false);
  });

  test('the kind filter narrows whatever the status filter lets through', () => {
    expect(ticketMatches({ status: 'new', kind: 'crash' }, { status: 'open', kind: 'crash' })).toBe(true);
    expect(ticketMatches({ status: 'new', kind: 'problem' }, { status: 'open', kind: 'crash' })).toBe(false);
    expect(ticketMatches({ status: 'new', kind: 'answer' }, { status: 'all', kind: 'answer' })).toBe(true);
    expect(ticketMatches({ status: 'fixed', kind: 'crash' }, { status: 'open', kind: 'crash' })).toBe(false);
  });
});

describe('what a save sends and says', () => {
  const base = { status: 'new', reply: '', owner_note: '' } as const;

  test('only changed fields are sent', () => {
    expect(ticketChanges(base, base)).toEqual({});
    expect(ticketChanges(base, { ...base, status: 'fixed' })).toEqual({ status: 'fixed' });
    expect(ticketChanges(base, { ...base, reply: 'Update the app.' })).toEqual({ reply: 'Update the app.' });
    expect(ticketChanges(base, { ...base, owner_note: 'Dup of ZH-9' })).toEqual({ owner_note: 'Dup of ZH-9' });
    expect(ticketChanges({ ...base, reply: 'Old' }, { status: 'closed', reply: '', owner_note: 'n' })).toEqual({ status: 'closed', reply: '', owner_note: 'n' });
  });

  test('the reply and the private note never trade places', () => {
    const patch = ticketChanges(base, { ...base, reply: 'For the person', owner_note: 'For me' });
    expect(patch.reply).toBe('For the person');
    expect(patch.owner_note).toBe('For me');
  });

  test('a saved reply says the person will see it', () => {
    expect(savedText({ reply: 'Update the app.' }, { ...problem, reply: 'Update the app.' })).toBe('Saved. The person sees your reply the next time they open My reports in the app.');
  });

  test('a cleared reply says it is no longer shown', () => {
    expect(savedText({ reply: '' }, problem)).toBe('Saved. The reply is no longer shown in the app.');
  });

  test('a status change on a person’s report says what they now see', () => {
    expect(savedText({ status: 'fixed' }, { ...problem, status: 'fixed' })).toBe('Saved. The person sees “Fixed” in My reports.');
  });

  test('one save that changes both status and reply says the person sees both', () => {
    expect(savedText({ status: 'fixed', reply: 'Done' }, { ...problem, status: 'fixed', reply: 'Done' })).toBe(
      'Saved. The person sees “Fixed” in My reports. The person sees your reply the next time they open My reports in the app.',
    );
    expect(savedText({ status: 'closed', reply: '' }, { ...problem, status: 'closed', reply: '' })).toBe(
      'Saved. The person sees “Closed” in My reports. The reply is no longer shown in the app.',
    );
  });

  test('a note-only save says the note stays private', () => {
    expect(savedText({ owner_note: 'Dup' }, { ...problem, owner_note: 'Dup' })).toBe('Saved. Your private note stays here. It is not sent to the phone.');
  });

  test('a status change quotes the words the phone shows, not the console’s own labels', () => {
    expect(savedText({ status: 'in_progress' }, { ...problem, status: 'in_progress' })).toBe('Saved. The person sees “Being looked at” in My reports.');
    expect(savedText({ status: 'new' }, { ...problem, status: 'new' })).toBe('Saved. The person sees “Received” in My reports.');
    expect(savedText({ status: 'closed' }, { ...problem, status: 'closed' })).toBe('Saved. The person sees “Closed” in My reports.');
  });

  test('a flagged answer never reaches My reports, so a save never says the person sees it', () => {
    expect(inMyReports(problem)).toBe(true);
    expect(inMyReports(flagged)).toBe(false);
    for (const out of [
      savedText({ reply: 'You are right.' }, { ...flagged, reply: 'You are right.' }),
      savedText({ status: 'closed' }, { ...flagged, status: 'closed' }),
    ]) {
      expect(out).not.toMatch(/The person sees/);
      expect(out).toMatch(/The person does not see this/);
    }
  });

  test('a crash never claims a person will see anything', () => {
    expect(inMyReports(crash)).toBe(false);
    expect(savedText({ status: 'fixed' }, { ...crash, status: 'fixed' })).toBe('Saved.');
    expect(savedText({ status: 'fixed', owner_note: 'Fixed in 1.4.1' }, { ...crash, status: 'fixed', owner_note: 'Fixed in 1.4.1' }))
      .toBe('Saved. Your private note stays here. It is not sent to the phone.');
  });

  test('status labels are plain words', () => {
    expect((['new', 'in_progress', 'fixed', 'closed'] as const).map(statusLabel)).toEqual(['New', 'In progress', 'Fixed', 'Closed']);
  });

});

// The console repeats four facts the backend decides. Read them from its source, the way api.test.ts does for
// routes, so a change on that side fails here instead of leaving the console saying something untrue.
describe('what the console says matches the backend', () => {
  const root = new URL('../../', import.meta.url);
  const consolePy = readFileSync(new URL('backend/support/console.py', root), 'utf8');
  const modelsPy = readFileSync(new URL('backend/support/models.py', root), 'utf8');
  const apiPy = readFileSync(new URL('backend/support/api.py', root), 'utf8');
  const myReportsTsx = readFileSync(new URL('app/my-reports.tsx', root), 'utf8');

  test('the reply and private note limits', () => {
    expect(Number(consolePy.match(/"reply": text\((\d+)\)/)![1])).toBe(MAX_REPLY);
    expect(Number(consolePy.match(/"owner_note": text\((\d+)\)/)![1])).toBe(MAX_NOTE);
  });

  test('how many tickets one list holds', () => {
    expect(Number(consolePy.match(/^LIST_LIMIT = (\d+)/m)![1])).toBe(LIST_LIMIT);
  });

  test('a reply box is offered for exactly the kinds a phone lists under My reports', () => {
    // The phone's list comes from the mine endpoint, so read the kinds from its filter, not from PERSON_KINDS
    // (that set decides who gets an owner email, which is a different thing).
    const mine = apiPy.match(/\ndef mine\([\s\S]*?(?=\n(?:def |@)|$)/)![0];
    const filter = mine.match(/Ticket\.objects\.filter\(([^\n]*)\)/)![1];
    const kinds = (['problem', 'crash', 'answer'] as const).filter((k) => new RegExp(`kind(?:__in)?=[^)]*Ticket\\.${k.toUpperCase()}\\b`).test(filter));
    expect(kinds).toEqual(['problem']);
    for (const kind of ['problem', 'crash', 'answer'] as const) expect(inMyReports({ kind }), kind).toBe((kinds as readonly string[]).includes(kind));
  });

  test('the placeholder text of a flagged answer with no note', () => {
    expect(apiPy.match(/^FLAGGED_ANSWER = "([^"]+)"/m)![1]).toBe(FLAGGED_ANSWER);
  });

  test('the status words quoted after a save are the ones My reports shows', () => {
    const block = myReportsTsx.match(/const STATUS: [^=]*= \{([\s\S]*?)\};/)![1];
    const phone = Object.fromEntries([...block.matchAll(/(\w+): '([^']+)'/g)].map((m) => [m[1], m[2]]));
    for (const s of ['new', 'in_progress', 'fixed', 'closed'] as const) expect(PHONE_STATUS[s], s).toBe(phone[s]);
  });

  test('the list accepts every filter the console offers', () => {
    expect(consolePy).toMatch(/STATUS_FILTERS = \("open", "all"\) \+ tuple\(s for s, _ in Ticket\.STATUSES\)/);
    expect(consolePy).toMatch(/KIND_FILTERS = \("all",\) \+ tuple\(k for k, _ in Ticket\.KINDS\)/);
    expect(modelsPy).toMatch(/PROBLEM, CRASH, ANSWER = "problem", "crash", "answer"/);
    expect(modelsPy).toMatch(/NEW, IN_PROGRESS, FIXED, CLOSED = "new", "in_progress", "fixed", "closed"/);
  });
});

describe('small lines', () => {
  test('a flagged answer is listed by the start of its question, so each one can be told apart', () => {
    expect(ticketTitle({ ...flagged, title: FLAGGED_ANSWER })).toBe('“How high before I need a harness?”');
    const long = 'What do I do when the lockout lock is missing and the supervisor is not on site and the line has to run today?';
    const t = ticketTitle({ ...flagged, question: long });
    expect(t.length).toBeLessThanOrEqual(72);
    expect(t.endsWith('…”')).toBe(true);
    expect(ticketTitle({ ...flagged, question: '' })).toBe('Flagged OTIS answer');
    expect(ticketTitle(problem)).toBe('The app closes');
    expect(ticketTitle(crash)).toBe('TypeError: x is undefined');
  });

  test('a long question is cut by characters, so an emoji is never split in half', () => {
    const t = ticketTitle({ ...flagged, question: `${'a'.repeat(68)}🔥🔥🔥 is this a fire hazard?` });
    expect(t).not.toMatch(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/);
    expect(t).toBe(`“${'a'.repeat(68)}🔥…”`);
    // 70 characters fit as they are, emoji included; 71 are cut to 69 and an ellipsis.
    const seventy = `${'b'.repeat(69)}🔥`;
    expect(ticketTitle({ ...flagged, question: seventy })).toBe(`“${seventy}”`);
    expect(ticketTitle({ ...flagged, question: `${seventy}c` })).toBe(`“${'b'.repeat(69)}…”`);
  });

  test('the phone line leaves out what the phone did not send', () => {
    expect(deviceLine(problem)).toBe('Pixel 8 · Android 15 · app 1.4.0');
    expect(deviceLine({ device: '', platform: 'ios', os_version: '', app_version: '1.4.0' })).toBe('iPhone or iPad (iOS) · app 1.4.0');
    expect(deviceLine({ device: '', platform: '', os_version: '', app_version: '' })).toBe('The phone did not say');
  });

  test('the crash count says when only some reports are kept', () => {
    expect(crashCountText(1, 1)).toBe('Happened once.');
    expect(crashCountText(12, 12)).toBe('Happened 12 times.');
    expect(crashCountText(340, 50)).toBe('Happened 340 times. The 50 reports below are what is kept. The rest are counted, not stored.');
    expect(crashCountText(3, 1)).toBe('Happened 3 times. The one report below is what is kept. The rest are counted, not stored.');
  });
});

describe('the detail view', () => {
  test('a reported problem shows the person’s words, who sent it, the phone and the app version', () => {
    const out = html(<TicketBody t={problem} />);
    expect(out).toContain('What the person wrote');
    expect(out).toContain('The app closes when I open a talk.\nEvery time.');
    expect(out).toContain('Sam');
    expect(out).toContain('href="mailto:sam@example.com"');
    expect(out).toContain('said OK to reply by email');
    expect(out).toContain('Sent from the Report a problem screen');
    expect(out).toContain('Pixel 8 · Android 15 · app 1.4.0');
    expect(out).toContain('/talk/[id]');
    expect(out).toContain('Spanish');
  });

  test('an email given without "OK to reply" is not shown as a link', () => {
    const out = html(<TicketBody t={{ ...problem, may_contact: false }} />);
    expect(out).not.toContain('mailto:');
    expect(out).not.toContain('sam@example.com');
    expect(out).toContain('Do not email them.');
  });

  test('a flagged OTIS answer shows the question, the answer and the person’s note', () => {
    const out = html(<TicketBody t={flagged} />);
    expect(out).toContain('The OTIS answer they flagged');
    expect(out).toContain('Their question');
    expect(out).toContain('How high before I need a harness?');
    expect(out).toContain('What OTIS answered');
    expect(out).toContain('At 6 feet in construction.');
    expect(out).toContain('This is wrong for scaffolds.');
    expect(out).toContain('gemma-3n-e2b');
    expect(out).toContain('Flagged with “Report this answer”');
  });

  test('a flagged answer with no note of its own says so, instead of showing the server’s placeholder as their words', () => {
    const out = html(<TicketBody t={{ ...flagged, text: FLAGGED_ANSWER, title: FLAGGED_ANSWER }} />);
    expect(out).toContain('No note.');
    expect(out).not.toContain(`<p class="quote">${FLAGGED_ANSWER}</p>`);
  });

  test('a problem or a crash never shows question and answer headings', () => {
    for (const t of [problem, crash]) {
      const out = html(<TicketBody t={t} />);
      expect(out).not.toContain('Their question');
      expect(out).not.toContain('What OTIS answered');
    }
  });

  test('a crash shows the error, that no person sent it, and when it was first and last seen', () => {
    const out = html(<TicketBody t={crash} />);
    expect(out).toContain('The error');
    expect(out).toContain('TypeError: x is undefined');
    expect(out).toContain('No one. The app sent this on its own');
    expect(out).toContain('First seen');
    expect(out).toContain('Last seen');
    expect(out).toContain('iPhone 17 · iPhone or iPad (iOS) 26.1 · app 1.4.0');
  });

  test('a crash lists each report with its stack, and says how many are kept', () => {
    const out = html(<CrashReports t={crash} crashes={[report, { ...report, fatal: false, stack: '' }]} error="" />);
    expect(out).toContain('Happened 340 times. The 2 reports below are what is kept.');
    expect(out).toContain('The app stopped');
    expect(out).toContain('The app kept running');
    expect(out).toContain('at open (talk.tsx:10)\nat press (list.tsx:4)');
    expect(out.match(/<details>/g)).toHaveLength(1); // no empty stack box
  });

  test('crash reports say they are loading, and show the server’s sentence when they fail', () => {
    expect(html(<CrashReports t={crash} crashes={null} error="" />)).toContain('Loading the crash reports');
    const failed = html(<CrashReports t={crash} crashes={null} error="No ticket with that number." />);
    expect(failed).toContain('No ticket with that number.');
    expect(failed).not.toContain('Loading');
  });
});

describe('the reply and the private note', () => {
  test('a reported problem has both boxes, each marked with who sees it', () => {
    const out = html(<TicketEditor ticket={{ ...problem, reply: 'Update the app.', owner_note: 'Dup of ZH-9' }} crashes={[]} crashError="" onSaved={noop} />);
    expect(out).toContain('The person sees this');
    expect(out).toContain('Reply to the person');
    expect(out).toContain('Only you see this');
    expect(out).toContain('Private note');
    expect(out).toContain('It is never sent to the phone');
    expect(out.match(/<textarea/g)).toHaveLength(2);
    // The reply box comes first and holds the reply; the note box holds the note.
    expect(out.indexOf('Update the app.')).toBeLessThan(out.indexOf('Dup of ZH-9'));
    expect(out.indexOf('The person sees this')).toBeLessThan(out.indexOf('Update the app.'));
    expect(out.indexOf('Only you see this')).toBeLessThan(out.indexOf('Dup of ZH-9'));
    expect(out).toContain('The person sees this status in the app');
  });

  test('a crash has only the private note, and says why there is no reply box', () => {
    const out = html(<TicketEditor ticket={crash} crashes={[report]} crashError="" onSaved={noop} />);
    expect(out.match(/<textarea/g)).toHaveLength(1);
    expect(out).not.toContain('Reply to the person');
    expect(out).not.toContain('The person sees this');
    expect(out).toContain('there is no person to answer');
    expect(out).toContain('A Closed one opens again as New if it comes back.');
    expect(out).not.toContain('The person sees this status');
    expect(out).toContain('Only you see this');
    expect(out).toContain('Each time it happened');
    expect(out).toContain('340 times');
  });

  test('a flagged answer has only the private note, and says plainly the person never sees a reply', () => {
    const out = html(<TicketEditor ticket={flagged} crashes={[]} crashError="" onSaved={noop} />);
    expect(out.match(/<textarea/g)).toHaveLength(1);
    expect(out).not.toContain('Reply to the person');
    expect(out).not.toContain('The person sees this');
    expect(out).toContain('The person never sees anything you write on a flagged answer');
    expect(out).toContain('Only you see this status.');
    expect(out).not.toContain('A Closed one opens again'); // that rule is for crashes only
    expect(out).toContain('Only you see this');
    expect(out).not.toContain('Each time it happened');
  });

  test('a reply saved earlier on a flagged answer is shown as never seen', () => {
    const out = html(<TicketEditor ticket={{ ...flagged, reply: 'Thanks, we fixed it.' }} crashes={[]} crashError="" onSaved={noop} />);
    expect(out).toContain('Thanks, we fixed it.');
    expect(out).toContain('The person never saw this');
    expect(out.match(/<textarea/g)).toHaveLength(1);
  });

  test('the header shows the reference, the kind and the status', () => {
    const out = html(<TicketEditor ticket={{ ...problem, status: 'in_progress' }} crashes={[]} crashError="" onSaved={noop} />);
    expect(out).toContain('ZH-12 · The app closes');
    expect(out).toContain('Reported problem');
    expect(out).toContain('In progress');
  });
});
