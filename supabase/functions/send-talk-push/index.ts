// Supabase Edge Function: send-talk-push
// Called by a GoHighLevel workflow (Webhook action) every Sunday at 11:59 AM PT,
// alongside the Zero Harm Weekly email. Sends this week's toolbox talk as a push
// to everyone who has "Weekly toolbox talk" switched on in the app.
//
// Secrets (supabase secrets set ...):
//   ZH_WEBHOOK_SECRET      shared secret GHL sends in the x-zh-secret header
//   ONESIGNAL_APP_ID       OneSignal App ID
//   ONESIGNAL_REST_API_KEY OneSignal App API key
// SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are provided automatically.
//
// Optional JSON body: { "issue": 7, "dry_run": true }

import { createClient } from "npm:@supabase/supabase-js@2";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

Deno.serve(async (req) => {
  if (req.method !== "POST") return json(405, { error: "Use POST." });
  if (req.headers.get("x-zh-secret") !== Deno.env.get("ZH_WEBHOOK_SECRET")) {
    return json(401, { error: "Missing or wrong x-zh-secret header." });
  }

  const body = await req.json().catch(() => ({}));
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  // Pick the requested issue, or the most recent one due within the next 10 minutes.
  let query = supabase.from("toolbox_talks").select("issue, title, story_title").eq("published", true);
  if (body.issue) {
    query = query.eq("issue", body.issue);
  } else {
    const cutoff = new Date(Date.now() + 10 * 60 * 1000).toISOString();
    query = query.lte("send_at", cutoff).order("send_at", { ascending: false }).limit(1);
  }
  const { data: talks, error } = await query;
  if (error) return json(500, { error: error.message });
  const talk = talks?.[0];
  if (!talk) return json(404, { error: "No published talk is due yet." });

  const payload = {
    app_id: Deno.env.get("ONESIGNAL_APP_ID"),
    target_channel: "push",
    filters: [{ field: "tag", key: "weekly_talk", relation: "=", value: "on" }],
    headings: { en: "This week's toolbox talk" },
    contents: { en: `🦺 ${talk.title}. 5 minutes, ready for Monday's crew meeting.` },
    data: { issue: talk.issue }, // the app opens /talk/<issue> when tapped
  };

  if (body.dry_run) return json(200, { dry_run: true, payload });

  const res = await fetch("https://api.onesignal.com/notifications?c=push", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Key ${Deno.env.get("ONESIGNAL_REST_API_KEY")}`,
    },
    body: JSON.stringify(payload),
  });
  const result = await res.json();
  return json(res.ok ? 200 : 502, { issue: talk.issue, onesignal: result });
});
