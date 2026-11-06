# Zero Harm (Expo / React Native)

The free Zero Harm safety app from Trainovate Technologies. Version 1 scaffold:
five tabs (Today, Inspect, Report, Tools, Learn), the weekly toolbox talk with crew
sign-in and a PDF sign-in sheet, an injury-rate calculator, optional email sign-up,
and Sunday push notifications driven by GoHighLevel.

Built on Expo SDK 58, React Native 0.88, Expo Router, Supabase and OneSignal.
Typecheck, lint, expo-doctor (20/20) and an Android bundle export all pass.

## What works now
- **Today:** this week's talk as a safety-yellow placard, past talks below, offline copy on the phone.
- **Talk screen:** story, crew question, printable PDF link, a weekly-reminder prompt shown after the first talk is opened.
- **Crew sign-in:** pass the phone around, type a name, sign, then share a branded PDF sign-in sheet. Stored on the device only.
- **Tools:** TRIR and DART rate calculator (200,000-hour base).
- **Settings:** two separate switches, "Weekly toolbox talk" and "News and offers" (promotional, off by default), plus optional email sign-up.
- **Inspect, Report, Learn:** clear placeholders for the first updates.

## Setup
1. `npm install`
2. Copy `.env.example` to `.env` and fill in the Supabase URL, publishable key and OneSignal App ID.
3. **Supabase:** run `supabase/migrations/0001_toolbox_talks.sql`, then `supabase/seed.sql`
   (all 52 issues of 2027, each released Sunday 11:59 AM Pacific, daylight saving handled).
   Row-level security only shows a talk after its send time. Add `body_md`, `hero_url` and `pdf_url`
   per issue to point at the files already hosted on the Vercel site.
4. **OneSignal:** create an app, add the Apple push key (.p8) and Firebase credentials in OneSignal.
5. **Run it:** OneSignal and the signature pad need native code, so use a development build, not Expo Go:
   `npx eas-cli@latest build --profile development --platform ios` (or `android`), then `npx expo start`.
6. Before the store build, change `onesignal-expo-plugin` mode in `app.json` from `development` to `production`.

## Sunday push from GoHighLevel
1. Deploy the function: `supabase functions deploy send-talk-push --no-verify-jwt`
2. Set secrets: `supabase secrets set ZH_WEBHOOK_SECRET=... ONESIGNAL_APP_ID=... ONESIGNAL_REST_API_KEY=...`
3. In the GHL workflow that sends Zero Harm Weekly on Sunday at 11:59 AM PT, add a **Webhook** action:
   POST `https://YOUR-PROJECT.supabase.co/functions/v1/send-talk-push`, header `x-zh-secret: <secret>`.
4. Test first with body `{"issue": 1, "dry_run": true}`. It returns the exact payload without sending.

The function sends only to devices tagged `weekly_talk = on`, and tapping the push opens `/talk/<issue>`.

## Still to do before App Store submission
- App icon, splash art and store screenshots (current images are Expo placeholders).
- Add `body_md` text for each issue, and clear the open pre-send flags in the topic ledger.
- Sync `app_signups` to GoHighLevel (edge function or GHL inbound webhook), with app-specific tags.
- Privacy policy URL and App Privacy answers (email, push token, crash data).
- Apple Developer account under Trainovate Technologies (D-U-N-S) and Google Play account.

## Project map
```
app/(tabs)/        index (Today), inspect, report, tools, learn
app/talk/[issue]   talk screen
app/signin/[session] crew sign-in
app/settings       notification switches, email sign-up
constants/theme.ts colors (ANSI safety yellow), Barlow fonts
lib/               supabase, offline db, talks, push, sign-ins, pdf
supabase/          migration, 52-issue seed, send-talk-push function
```
