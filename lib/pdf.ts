import { Directory, File, Paths } from 'expo-file-system';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

import type { Signin, SigninSession } from './signins';
import type { SheetSubject } from './subject';

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/** How many people attended: every signature, or the head count given for the group photo, whichever is larger. */
export const attendeeCount = (session: SigninSession, signins: Signin[]) => Math.max(signins.length, session.photo_count ?? 0);

/** Builds the crew sign-in sheet PDF (signatures and/or group photo) and returns its file URI. */
export async function buildSigninSheet(subject: SheetSubject, session: SigninSession, signins: Signin[]) {
  const rows = signins
    .map(
      (s, i) => `<tr><td>${i + 1}</td><td>${esc(s.crew_name)}</td>
      <td><img src="${s.signature}" style="height:42px"/></td><td>${esc(s.signed_at)} UTC</td></tr>`,
    )
    .join('');
  const photo = session.group_photo
    ? `<h2>Group photo</h2><img class="photo" src="${session.group_photo}"/>
       <div class="meta">${session.photo_count ? `${session.photo_count} people in the photo, as counted by the supervisor.` : ''}</div>`
    : '';
  const table = signins.length
    ? `<h2>Signatures</h2><table><tr><th>#</th><th>Name</th><th>Signature</th><th>Signed</th></tr>${rows}</table>`
    : '';
  const html = `<html><head><meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body{font-family:Helvetica,Arial,sans-serif;color:#17212B;margin:32px}
    .band{background:#F5C400;padding:14px 18px;font-weight:700;font-size:13px}
    h1{font-size:24px;margin:16px 0 4px} h2{font-size:16px;margin:20px 0 8px}
    .meta{color:#5B6773;font-size:13px;margin-bottom:12px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{border:1px solid #CDD2D6;padding:8px;text-align:left;vertical-align:middle}
    th{background:#ECEEEF} .photo{width:100%;max-height:560px;object-fit:contain;border:1px solid #CDD2D6}
    footer{margin-top:24px;color:#5B6773;font-size:11px}
  </style></head><body>
  <div class="band">Toolbox talk sign-in sheet</div>
  <h1>${esc(subject.title)}</h1>
  <div class="meta">${esc(subject.label)}<br/>
  Supervisor: ${esc(session.supervisor ?? '')} &nbsp; Location: ${esc(session.location ?? '')} &nbsp; Held: ${esc(session.created_at)} UTC<br/>
  Attendees: ${attendeeCount(session, signins)}</div>
  ${photo}${table}
  <footer>Made with the free Zero Harm app from Trainovate Technologies. go.trainovate.ai/zero-harm-weekly-page</footer>
  </body></html>`;
  const { uri } = await Print.printToFileAsync({ html });
  return uri;
}

/** Opens the share sheet for a PDF: Mail, Gmail, Files, Drive, Messages, and Print on iPhone. */
export async function sharePdf(uri: string, dialogTitle = 'Email or share') {
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', dialogTitle, UTI: 'com.adobe.pdf' });
  }
}

/** Sends a PDF on this phone to a printer (AirPrint on iPhone, the print service on Android). */
export const printPdf = (uri: string) => Print.printAsync({ uri });

/** Copies a sheet into the app's Documents folder, where the phone keeps it until the app is deleted. Returns its new uri. */
export async function keepOnPhone(uri: string, name: string) {
  const dir = new Directory(Paths.document, 'sign-in-sheets');
  dir.create({ idempotent: true });
  const safe = name.replace(/[^A-Za-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'sheet';
  const dest = new File(dir, `${safe}.pdf`);
  if (dest.exists) dest.delete();
  await new File(uri).copy(dest);
  return dest.uri;
}

/** True if a kept sheet is still on the phone. */
export const stillOnPhone = (uri: string | null) => Boolean(uri) && new File(uri!).exists;

export const pdfBase64 = (uri: string) => new File(uri).base64();
