import * as Print from 'expo-print';

import { weekLabel, type Minute } from './monday';
import { sharePdf } from './pdf';

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
const ORANGE = '#FF6A13';
const INK = '#17212B';
const PAPER_ROWS = 18;

/** The Monday Minute stopwatch mark as inline SVG, so the printed page needs no network or image files. */
const MARK = `<svg viewBox="0 0 200 200" width="64" height="64" xmlns="http://www.w3.org/2000/svg">
  <rect x="84" y="6" width="32" height="14" rx="4" fill="${ORANGE}"/><rect x="94" y="16" width="12" height="16" fill="${ORANGE}"/>
  <g transform="rotate(45 100 114)"><rect x="93" y="22" width="14" height="14" rx="3" fill="${ORANGE}"/></g>
  <circle cx="100" cy="114" r="82" fill="${ORANGE}"/><circle cx="100" cy="114" r="69" fill="${INK}"/>
  <circle cx="100" cy="51" r="6" fill="${ORANGE}"/>
  <text x="100" y="140" text-anchor="middle" font-family="Helvetica Neue, Arial, sans-serif" font-weight="800" font-size="80" fill="#fff">M</text></svg>`;

/**
 * A printable Monday Minute: page 1 is the talk to read aloud, page 2 is a paper sign-in sheet for crews signing with a pen.
 * US Letter. Works with no signal.
 */
export function handoutHtml(m: Minute) {
  const rows = Array.from({ length: PAPER_ROWS }, (_, i) => `<tr><td class="n">${i + 1}</td><td></td><td></td><td></td></tr>`).join('');
  const header = (sub: string) => `<div class="head">${MARK}<div><div class="brand">MONDAY <span>MINUTE</span></div>
    <div class="sub">${esc(sub)}</div></div></div>`;
  return `<html><head><meta name="viewport" content="width=device-width, initial-scale=1"/><style>
  @page { size: letter; margin: 0.6in; }
  body { font-family: Helvetica, Arial, sans-serif; color: ${INK}; font-size: 12.5pt; line-height: 1.4; margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .head { display: flex; align-items: center; gap: 14px; border-bottom: 4px solid ${ORANGE}; padding-bottom: 10px; }
  .brand { font: 800 26pt/1 'Helvetica Neue', Arial, sans-serif; letter-spacing: 1px; } .brand span { color: ${ORANGE}; }
  .sub { color: #5B6773; font-size: 10.5pt; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
  h1 { font-size: 24pt; line-height: 1.1; margin: 18px 0 8px; }
  h2 { font-size: 14pt; margin: 18px 0 6px; }
  ol { padding-left: 22px; margin: 0; } li { margin: 0 0 8px; padding-left: 4px; } li::marker { color: ${ORANGE}; font-weight: 800; }
  .q { border: 3px solid ${ORANGE}; border-radius: 6px; padding: 10px 14px; margin-top: 16px; break-inside: avoid; }
  .q b { display: block; font-size: 13pt; margin-bottom: 4px; }
  .take { font-weight: 700; font-size: 13.5pt; margin-top: 14px; }
  .fine { color: #5B6773; font-size: 9pt; margin-top: 16px; }
  .sheet { page-break-before: always; }
  .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 24px; margin: 16px 0; font-size: 11pt; }
  .fields div { border-bottom: 1px solid ${INK}; padding: 14px 0 2px; }
  table { width: 100%; border-collapse: collapse; font-size: 11pt; }
  th { background: ${INK}; color: #fff; text-align: left; padding: 6px 8px; }
  td { border: 1px solid #9AA6B1; height: 30px; padding: 0 8px; } td.n { width: 28px; color: #5B6773; text-align: center; }
  </style></head><body>
  ${header(`Week of ${weekLabel(m)} · ${m.category}`)}
  <h1>${esc(m.title)}</h1>
  <p>${esc(m.intro)}</p>
  <h2>Talk it through</h2>
  <ol>${m.points.map((p) => `<li>${esc(p)}</li>`).join('')}</ol>
  <h2>Close call: ${esc(m.story_title)}</h2>
  <p>${esc(m.story)}</p>
  <div class="q"><b>Ask your crew</b>${esc(m.crew_question)}</div>
  <div class="take">${esc(m.takeaway)}</div>
  ${m.references.length ? `<div class="fine">OSHA: ${m.references.map((r) => `29 CFR ${esc(r)}`).join(', ')}</div>` : ''}
  <div class="fine">Written by AI from a topic reviewed by a safety professional and checked automatically before publishing. It adds to your
  training and does not replace it. Always follow your site's written steps. Not sure it's safe? Stop and ask. Free from the Zero Harm app, Trainovate Technologies.</div>

  <div class="sheet">
    ${header('Toolbox talk sign-in sheet')}
    <h1>${esc(m.title)}</h1>
    <div class="fields"><div>Date:</div><div>Time:</div><div>Supervisor:</div><div>Location:</div></div>
    <table><tr><th>#</th><th style="width:40%">Name (print)</th><th style="width:34%">Signature</th><th>Employee ID / Dept</th></tr>${rows}</table>
    <div class="fine">By signing, I confirm I attended this toolbox talk. Keep this sheet with your training records.</div>
  </div>
  </body></html>`;
}

/** Opens the phone's print dialog (AirPrint on iPhone, the print service on Android). */
export const printHandout = (m: Minute) => Print.printAsync({ html: handoutHtml(m) });

/** Makes the PDF and opens the share sheet: Mail, Gmail, Files, Drive, Messages and so on. */
export async function shareHandout(m: Minute) {
  const { uri } = await Print.printToFileAsync({ html: handoutHtml(m) });
  await sharePdf(uri);
}
