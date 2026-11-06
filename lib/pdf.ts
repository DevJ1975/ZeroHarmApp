import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

import type { Signin, SigninSession } from './signins';
import type { Talk } from './talks';

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

/** Builds the crew sign-in sheet as a PDF and opens the share sheet (email, Files, print). */
export async function shareSigninSheet(talk: Talk, session: SigninSession, signins: Signin[]) {
  const rows = signins
    .map(
      (s, i) => `<tr><td>${i + 1}</td><td>${esc(s.crew_name)}</td>
      <td><img src="${s.signature}" style="height:42px"/></td><td>${esc(s.signed_at)} UTC</td></tr>`,
    )
    .join('');
  const html = `<html><head><meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body{font-family:Helvetica,Arial,sans-serif;color:#17212B;margin:32px}
    .band{background:#F5C400;padding:14px 18px;font-weight:700;font-size:13px}
    h1{font-size:24px;margin:16px 0 4px} .meta{color:#5B6773;font-size:13px;margin-bottom:16px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{border:1px solid #CDD2D6;padding:8px;text-align:left;vertical-align:middle}
    th{background:#ECEEEF} footer{margin-top:24px;color:#5B6773;font-size:11px}
  </style></head><body>
  <div class="band">Toolbox talk sign-in sheet</div>
  <h1>${esc(talk.title)}</h1>
  <div class="meta">Zero Harm Weekly issue ${talk.issue} (${esc(talk.month_theme)})<br/>
  Supervisor: ${esc(session.supervisor ?? '')} &nbsp; Location: ${esc(session.location ?? '')} &nbsp; Held: ${esc(session.created_at)} UTC</div>
  <table><tr><th>#</th><th>Name</th><th>Signature</th><th>Signed</th></tr>${rows}</table>
  <footer>Made with the free Zero Harm app from Trainovate Technologies. go.trainovate.ai/zero-harm-weekly-page</footer>
  </body></html>`;

  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', dialogTitle: 'Share sign-in sheet', UTI: 'com.adobe.pdf' });
  }
  return uri;
}
