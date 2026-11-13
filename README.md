# Zero Harm

The free Zero Harm safety app from Trainovate Technologies, plus the Django backend that serves it.

```
/            Expo / React Native app (iOS and Android)
/backend     Django API + admin, Dockerized, deployed on Railway
/console     Content console that runs on your Mac (see console/README.md)
```

## The app (Expo SDK 58, React Native 0.88, Expo Router, OneSignal)
- **Today:** this week's talk as a safety-yellow placard, past talks below, offline copy on the phone.
- **Talk screen:** story, crew question, printable PDF, and a weekly-reminder prompt after the first talk.
- **Crew sign-in:** pass the phone around, type a name, sign, share a branded PDF sign-in sheet. Every sheet is kept on
  the phone. Tapping **Save sheet to my records** also uploads the PDF, with its signatures and photo, to the server,
  which files it in GoHighLevel under the supervisor's email.
- **Tools:** TRIR and DART rate calculator (200,000-hour base).
- **Settings:** a switch for each kind of notification (Monday Minute, Weekly toolbox talk, Regulatory alerts, Zero Hour
  episodes, and "News and offers", which is promotional and off by default), optional email sign-up, and two privacy
  switches, "Daily usage count" and "Crash reports" (both on by default).
- **Problems with the app:** "Report a problem" and "My reports" in Settings. OTIS can take a report too, and the app's
  own error screen offers one. See *Support tickets and crash reports* below.
- **Learn:** Zero Hour episodes, free courses and tools published from GoHighLevel, and the newsletter sign-up.

Run it:
1. `npm install`
2. Copy `.env.example` to `.env`; set `EXPO_PUBLIC_API_URL` to the Railway URL and `EXPO_PUBLIC_ONESIGNAL_APP_ID`.
3. OneSignal and the signature pad need native code, so use a development build, not Expo Go:
   `npx eas-cli@latest build --profile development --platform ios`, then `npx expo start`.
4. Nothing in `app.json` is edited by hand before a store build. `app.config.js` does it: OneSignal uses Apple's
   production service when EAS builds the `production` profile, and tester and store builds (`preview` and
   `production`) leave out Android's "draw over other apps" permission, which only React Native's developer tools use.

App tests: `npm test` (Jest), `npx tsc --noEmit`, `npx expo lint`.

## The backend (Django 5.2 LTS, Postgres, Docker, Railway)
- `GET /api/talks/` talks the app shows, newest first: every talk past its Sunday 11:59 AM Pacific send time, plus the next two upcoming talks that have their text (`early: true`), so supervisors can run them ahead with crew sign-in. An early talk leaves out "Last week's answer" until its own send time, so it can't give away the previous crew question. `TALKS_EARLY_COUNT` changes how many open early; `TALKS_UNLOCK_EARLY=0` holds every talk until Sunday. The Sunday push goes out on schedule either way.
- `GET /api/talks/<issue>/` one talk.
- `POST /api/signups/` name and email from the welcome screen or Settings (optional, rate limited). Body: `{"email"}` plus
  optional `name`, `company`, `wants_offers`, `install_id`, `source` (`"welcome"` or `"settings"`) and `consent` (the
  consent line the app showed). One row per email. Emails longer than 254 characters are refused.
  There is no password and no email check, so the first phone linked to a sign-up owns it. Only that phone can change
  the name, company or offers choice. Any other phone that signs up with the same email is linked and changes nothing;
  it gets `{"ok": true, "changed": false}` and the app says the details were not changed. A new email and the owner
  phone get `{"ok": true}`. A sign-up made without a phone id has no owner and cannot be changed from the app.
  Known trade-off: `changed: false` tells a caller that sends a phone id that the email is already signed up.
  At most 30 new emails an hour from one network (a crew on one plant Wi-Fi; IPv6 counted per /64). Repeats are not
  counted, but once the 30 are used every sign-up from that network gets 429 until the hour ends. The app sends a
  refused sign-up again later. Instant owner emails stop at 20 an hour; the rest are in the daily summary. See *Leads
  and alerts* below.
- `POST /api/signups/remove/` with `{"install_id"}`. From the phone that made the sign-up (the first phone linked to it)
  the sign-up is deleted, with every phone linked to it, and the answer is `{"ok": true}`. From any other linked phone
  that phone is unlinked, nothing is deleted, the request is noted on the sign-up and emailed to the owner, and the
  answer is `{"ok": true, "pending": true}`. When nothing matched the answer is also `{"ok": true}`. At most 5 an hour
  from one network.
- `POST /api/signin-sheets/` a finished crew sign-in sheet (see *Sign-in sheets and talk ideas* below).
- `GET /api/weather/?lat=&lon=` weather and heat risk for a US point. One network may send 360 lookups an hour to the
  weather service. A point looked up in the last 10 minutes is answered from memory and costs nothing. A failed lookup
  is not counted, and that point is not tried again for 2 minutes. Each lookup waits at most 9 seconds.
- `/admin/` edit talk text, PDF and image links, see sign-ups, send a push or retry a GHL sync by hand. *Send the push
  now* sends one item per click, only once the item is live in the app, and asks first. An early push for content that
  is not live yet is sent from the console; it does not cancel the scheduled push.
- All 52 issues of 2027 load automatically on the first migrate.
- `python manage.py cron` sends any due push (once only), retries what did not reach GoHighLevel or the owner, and looks
  after support tickets and crash reports (the full list is under *Railway layout*). Each step runs even if another
  fails. A failed step is written to the log with its traceback, and the command exits with code 1 when any step
  failed, so the run shows as failed in Railway.
- `python manage.py sync_signups` retries every sign-up still waiting for GoHighLevel. `--min-age MINUTES` skips newer
  ones (the cron uses 2).

### Limits, errors and logs
- **Limits count per network:** the caller's address for IPv4, the /64 for IPv6. Each hourly limit starts with the
  first try and ends an hour later. Every endpoint has its own count, so one busy feature does not use up another's.
- **Where the counts live:** in memory on the web service, in a store of their own with room for 100,000, so weather
  and other cached content cannot push them out. They start again from zero when the web service restarts. The console
  wrong-key count and the admin sign-in counts are kept in the database and survive a restart.
- **Which address is counted:** see *After a deploy: check the caller address* under *Railway layout*. This has not
  been checked on the live server yet.
- **Errors:** every error under `/api/` is JSON, `{"error": "..."}`, including an unknown address (404), a wrong
  method (405) and a server error (500). Django Ninja's own validation and rate-limit answers under `/api/v2/` are
  shaped `{"detail": ...}`.
- **Logs:** every line in the web log is `LEVEL logger.name: message`. A server error (HTTP 500) is written by
  `django.request` with its full traceback. gunicorn writes one line per request; query strings are removed from those
  lines and from the Referer, so the back office key and invite contact ids never appear in the log.
- **Admin sign-in:** the admin sign-in page allows 10 failed sign-ins from one network in an hour; the hour starts with
  the first failure. After that the network sees "Too many failed sign-ins. Try again in an hour." until that hour is
  over, whatever it sends. When one username has had 10 failures in the hour from anywhere, each network gets 3 wrong
  tries at that username instead of 10. The right password from a network that has not failed always signs in.
- **Tests:** `python manage.py test` runs everything (791 tests). The rate-limit counts are emptied before every test
  (`backend/zeroharm/testing.py`). Three support tests that send requests at the same moment run only on PostgreSQL.

### Leads and alerts
Everyone who signs in on the welcome screen (or in Settings) becomes a lead in GoHighLevel and gets the weekly newsletter.
- **The lead in GHL:** the contact is created or updated with first name, last name, company and source "Zero Harm app",
  then tagged `zero-harm-app`, `zero-harm-weekly`, `zero-harm-app-signup`, and `zero-harm-offers-optin` when they said
  yes to offers. Tags are added, never replaced, so a contact keeps the tags it already had.
- **The newsletter (set up in GHL):** send Zero Harm Weekly to the tag `zero-harm-weekly`, for example a workflow or a
  scheduled campaign whose audience is that tag. The app only adds the tag. GHL sends the email and handles unsubscribes.
- **A notification in the GHL app (set up in GHL):** make a workflow with the trigger *Contact tag added:
  `zero-harm-app-signup`* and the action *Internal notification* to yourself.
- **Email to you on every new sign-up:** set `OWNER_ALERT_EMAIL` on web and cron (this restarts both; see *Changing a
  Railway variable*). The moment a new email signs up you get
  "New Zero Harm sign-up: Jane Doe" with the name, email, company, where they signed up, the Pacific time and the total so
  far. A repeat sign-up with the same email does not send another. The email goes out through GoHighLevel (your address
  becomes a contact tagged `zero-harm-owner`), so the location needs a working email sender and the private token needs
  the scopes `contacts.write`, `contacts.readonly` and `conversations/message.write`. `contacts.readonly` lets the server
  look at a contact's tags and notes before changing them. Blank `OWNER_ALERT_EMAIL` means no alerts.
- **Other notices to the same address,** each sent once: no Monday Minute went out this week, this week's Monday Minute
  is waiting for your approval, a Monday Minute was pulled after crew reports, a removal request to check, a sign-in
  sheet GoHighLevel will not take, and support tickets and crashes (see *Support tickets and crash reports*). Sign-up
  alerts and notices together are limited to 20 an hour.
- **One email a day for downloads:** the first cron run after 7:00 AM Pacific sends "Zero Harm yesterday: 12 new phones,
  3 sign-ups": new phones with the iPhone and Android split and the top places, new sign-ups, phones active and totals.
  A "new phone" is a phone's first-ever anonymous open, the closest thing to a download the server can see (the app
  stores don't tell the server about downloads). People who switched off the daily usage count are not included.
  Nothing is sent on a day with no new phones and no sign-ups, and after an outage at most 3 missed days are sent.
- **Removal:** "Remove my info" on the phone that signed up deletes the sign-up at once: the name and email are deleted
  from this server. In GHL the tags `zero-harm-weekly`, `zero-harm-offers-optin` and `zero-harm-app-signup` come off,
  but only the ones the app added: a tag the contact already had before signing up in the app stays on.
  `zero-harm-removed` and a dated note go on, and you get a "removal request" email. The GHL contact itself is kept;
  delete it in GHL if they ask for that. Signing up again later takes `zero-harm-removed` back off, and a removal still
  waiting for GHL is called off.
- **Removal from another phone:** on a second phone, or after a reinstall, "Remove my info" is a request. Nothing is
  deleted, the app says "We got your request. A person will remove your info.", the sign-up shows *Removal asked* in
  the admin, and you get an email "Zero Harm removal request to check". If the request is real, delete the sign-up in
  the admin and take the tags off the contact in GHL. If it is not, use *Keep these sign-ups: clear the removal
  request*. This is the price of having no password: a stranger who knows an email can remove nobody, but a real person
  on a new phone needs you to finish the job.
- **If GoHighLevel is down:** the sign-up or removal still succeeds on the phone. That also covers a dropped connection
  or an answer that is not JSON. The cron (every 15 minutes) sends the lead, the alert and the tag changes later. A
  removal GHL still won't take after 7 days is dropped from the server and you get an email listing the tags to take
  off by hand. If GHL says the contact no longer exists, the removal is done.
- **Notes the server writes in GHL** for a talk idea, a sign-in sheet or a support ticket end with a line like
  `Ref: zh-3f9a2c41d0aa`. Leave it there: it is how the server sees that its note is already on the contact and does
  not write it twice.

### Sign-in sheets and talk ideas
- **A saved sheet** (`POST /api/signin-sheets/`, 30 an hour per network) is uploaded to GoHighLevel Media Storage once,
  then filed on the supervisor's contact with a note. The upload to GoHighLevel happens while the phone waits.
- **Sent twice:** a sheet the phone sends twice (a lost signal, a slow answer) is stored and forwarded once. The server
  recognises it by a fingerprint of the PDF, also after a restart and after GoHighLevel has taken the PDF. The second
  answer is 200 with the first sheet's id.
- **If GoHighLevel does not take it:** the cron tries again from the step that failed, 20 sheets a run, leaving sheets
  younger than 5 minutes alone. A sheet is tried every 15 minutes for its first 8 tries, then about every 4 hours until
  it is 14 days old. When the 8th try fails you get one email with the sheet, the last error and how to retry by hand
  (admin, Sign-in sheets, tick it, *Retry saving to GoHighLevel*). The sheet and its PDF stay on the server meanwhile.
- **Talk ideas** (`POST /api/suggestions/`, 10 an hour per network): the same idea sent again within 10 minutes, every
  field equal, is answered with the first one's id and not stored twice. Ideas with an email are sent to GoHighLevel;
  the cron keeps trying for up to 14 days.
- **Publishing from GoHighLevel** (`POST /api/ingest/` with the `X-ZeroHarm-Key` header): `effective_date` takes
  `2027-01-03`, `2027/01/03`, or either with a time. `null` means no date and clears the date on an update; text that
  is not a date is refused with 400. `expires_at: null` means the item does not expire. `link` and `image` may be up
  to 500 characters; longer ones are refused with a 400 that says so. `sync_year` takes a year from 2020 to 2100. A
  queued year sync stays Pending, with the reason in its log, while `GHL_PRIVATE_TOKEN` or `GHL_LOCATION_ID` is
  missing, and runs once they are set.

### Invite link
Send people a link that opens the right app store on their phone.
- **The link:** `https://YOUR-SERVER/get/?c={{contact.id}}` (YOUR-SERVER is the web service's domain). `{{contact.id}}`
  is GoHighLevel's merge field, so each person gets their own link.
- **In GHL:** put it in an email or SMS template, or a workflow *Send email* action, as a button or a link.
- **What happens on a tap:** an iPhone or iPad goes straight to the App Store and an Android phone to Google Play, once
  that store's address is set. A computer, or a phone whose store isn't live yet, gets a small Zero Harm page with the
  store buttons that exist, or "Coming soon to the App Store and Google Play" while neither is set.
- **Follow-up:** the contact who tapped gets the tag `zero-harm-invite-clicked`. Use it as a workflow trigger (*Contact tag
  added*) for a follow-up. If GHL is down, the cron adds the tag later (it keeps trying for 2 days).
- **Store addresses:** set `APP_STORE_URL` and `PLAY_STORE_URL` on Railway (web service) once the app is approved. No app
  update needed, and links already sent start working at once. Setting them restarts the web service: see *Changing a
  Railway variable*. Only `https://` addresses are used.
- **What is counted:** one tap per contact per day, with iPhone, Android or other, shown as *Invite link taps* in the back
  office. No network address or browser details are kept. A contact id must be 10 to 40 letters and digits, nothing
  else; a link without a valid one still works but isn't counted. One network can add at most 30 new taps an hour, so
  a script can't fill the table.

### Monday Minute (the app's first screen)
A weekly 5-minute crew talk written by AI, separate from Zero Harm Weekly (code in `backend/monday/`, screens in `app/monday/`).
- **Topic bank:** 104 topic briefs (two years with no repeats), each checked against the eCFR text and reviewed in the
  CSP role before use (`backend/monday/topics.json`, review record in `docs/monday-minute-topic-review.md`). Edit them
  in the admin under *Monday Minute topics*.
- **Weekly run, no human approval:** from Wednesday, the cron picks a topic (in season, well rated, not used in two years),
  and the AI (your local model, or Claude) writes the talk from that one brief. Hard checks run on every draft: required lines word for word, no number
  that isn't in the brief, no links, one crew question. A second AI call then reviews it as a Certified Safety
  Professional and maps every point to a brief line. Any MUST FIX finding or ungrounded point means a rewrite, up to
  3 tries on each of 2 topics. With the local model, a second, independent review must also pass, and both must be
  highly confident. If nothing passes, that week
  doesn't publish. Talks publish Monday at 5:00 AM Pacific with a push to devices with *Monday Minute* turned on.
- **Writing takes several cron runs if it has to:** each run may spend `MONDAY_STEP_BUDGET` seconds on AI work (default
  1800), so the other scheduled jobs are never held back longer than that. What is not finished carries on in the next
  run: every AI answer is kept for 12 hours. A deploy or restart during a write does not block writing either: the next
  cron run takes over within about 5 minutes. An answer that cannot be used (cut off, refused, not valid JSON) is asked
  for once more, worded differently, and then counts as a failed try. A draft that uses up its three tries is saved as
  *Blocked by the safety checks* with the reason in its check log. The database allows one talk per week, whoever
  writes it.
- **A late week:** if the talk could not be written by Monday 5:00 AM Pacific (the AI server was down, a deploy stopped
  the run), the cron keeps trying until Wednesday 5:00 AM and the talk goes out as soon as it passes, with its push.
  A week still without a talk on Wednesday is reported once in the cron log ("NO TALK went out this week") and by one
  email to you. Only for a week that was meant to have a talk: a new install, or a server with no AI set up, reports
  nothing.
- **Write it now:** *Write next week's Monday Minute now* in the admin writes the same week the cron would. From Monday
  5:00 AM to Wednesday 5:00 AM Pacific, if this week's talk was never written, it writes this week's. With the local
  model it runs in the background inside the web server; how it ended, a failure included, shows under *Recent
  actions* on the admin home page. Only one write runs at a time; a second click is told so. A deploy or restart of the
  web service stops it, and the cron writes the talk on a later run.
- **Safety gate:** a talk that passes its checks publishes on its own only if the current AI setup (reviewer model, RAG
  on or off, strict review on or off) has passed the safety test in the last 90 days: at least 90% of planted mistakes
  caught, no more than about a third of good talks wrongly blocked, at least 20 planted mistakes tested. Otherwise the
  talk is saved as *Waiting for approval* and a person publishes it with *Approve and publish* in the admin. Changing
  the model or turning RAG off means passing the test again. The gate is checked when the talk is written and once
  more at the moment it goes out. If the setup lost its pass in between, the talk waits for approval instead, and you
  get one email once its publish time has passed. A talk that is already out stays out. The bar is set with
  `MONDAY_GATE_MIN_CATCH`, `MONDAY_GATE_MAX_FALSE_BLOCK`, `MONDAY_GATE_MIN_CASES` and `MONDAY_GATE_MAX_AGE_DAYS`;
  `MONDAY_GATE=0` turns it off.
- **Crews:** read it, print it with a paper sign-in sheet, or sign on the phone (finger signatures and/or a group
  photo). Then print, email or save the signed sheet. Every sheet is kept on the phone (*My sign-in sheets*).
- **Thumbs up/down** (one per phone per talk), with reasons on a thumbs down. Three "isn't safe or isn't right"
  reports from three different networks pull the talk and pause its topic until someone reviews it, and you get one
  email. One IPv6 home or phone connection counts as one network, whatever addresses it uses. A report whose network
  cannot be read is kept but is not one of the three. Ratings also steer which topics come next.
- **Pull and Restore in the admin:** *Pull* takes a published talk, or one waiting for approval, out of the app.
  *Restore* puts a pulled talk back only if it has its text and a passed safety check in its check log. A draft the
  checks blocked cannot be pulled or restored.
- **Comments and replies**, screened by AI moderation before they show (in the background with the local model). Held if moderation is down. Two reports hide a
  comment. Anyone can block a commenter on their phone, and people agree to community rules before their first comment.
  The admin can hide or restore any comment. In each cron run waiting comments are screened before the write and may
  use a fifth of the run's AI time; the rest wait for the next run. If the AI cannot give an answer for a comment three
  times, the comment is hidden for you to review in the admin: it never shows unchecked. A comment of only spaces is
  refused.
- **The AI server address:** with `AI_PROVIDER=local`, `LOCAL_AI_URL` must be set and start with `http://` or
  `https://`. If it is blank, the cron, the admin and `manage.py monday_eval` say "The AI server address is not set
  (LOCAL_AI_URL)." and posted comments wait until it is set.
- API: `/api/v2/monday-minute` (list, detail, `/feedback`, `/comments`, `/comments/{id}/report`). Per network and hour:
  60 ratings, 10 comments and 30 comment reports. Each has its own count, so a crew rating the talk on one Wi-Fi does
  not use up that site's comments.

### Back office inside GoHighLevel
`/backoffice/` is an analytics page built to sit inside GoHighLevel:
- **What it shows:** sign-in sheets and crew members signed in (with 12-week charts), supervisors running talks, email
  sign-ups (welcome screen and Settings), invite link taps (iPhone, Android, other), Monday Minute thumbs and comments, OTIS ratings, the most-used talks, and a *Needs your attention* list
  (pulled talks, paused topics, OSHA rule changes, comments waiting, sheets that didn't reach GHL, talks held for
  bracketed notes, new suggestions, new support tickets). Every item links to the right admin page.
- **Where the app is used:** phones active in the last 7 days and in the chosen period, new phones (first-ever opens)
  in the period, iPhone and Android, and the top
  countries, states and cities (see *Where the app is used* below).
- **What it can't show:** screen views. The app doesn't track them.
- **Access:** set `BACKOFFICE_KEY` on the web service to a long random value. The page opens with
  `https://<your-api-domain>/backoffice/?key=<BACKOFFICE_KEY>`, or for anyone signed in to the admin. Only GoHighLevel's
  domains may frame it. If you use a white-label app address, add it with `GHL_APP_DOMAINS=https://app.yourbrand.com`.
- **Install in GoHighLevel:** Agency view → Settings → Custom Menu Links → Create new. Give it a name (Zero Harm) and an
  icon, paste the link above, choose *Open in iFrame*, and show it to agency and account admins only, since the link
  holds the key.
- **Admin from GoHighLevel:** add a second custom menu link to `https://<your-api-domain>/admin/` set to *Open in new
  tab*. That works in every browser. To show the admin inside the GHL frame, set `GHL_EMBED_ADMIN=1`: it needs login
  cookies that work inside a frame, which Safari and some Chrome settings block, so the new-tab link is the default.

### Where the app is used (anonymous daily count)
The back office shows how many phones use the app and roughly where: country, state and city.
- **What the phone sends:** `POST /api/v2/app/open` at most once per day, and only while *Daily usage count* is on in
  the app's settings (on by default). The body is `{"install_id", "platform": "ios"|"android", "app_version", "place"}`.
  `place` (`{"city", "region", "country"}`) is sent only when the phone already knows it from the weather feature, which
  means the person allowed approximate location. The answer is always `{"ok": true}`.
- **What the server keeps:** one row per phone per day (`usage.AppOpen`): the day, the install id as the same salted hash
  Monday Minute uses, platform, app version, city, state, country, and whether the place came from the phone or the
  network. No names, emails or coordinates.
- **What it never keeps:** the network address. When the phone sends no place, the server looks the address up in a city
  database on its own disk to get an approximate place, then drops it. It is not stored and not written to logs.
- **How accurate:** approximate. A phone on a company VPN or a cellular network can show up in another city. A phone
  seen in several places is counted once, in the most recent place known.
- **The city database:** the free [DB-IP](https://db-ip.com) "IP to City Lite" file (CC BY 4.0, so the back office shows
  "IP geolocation by DB-IP"). `python manage.py geo_update` downloads this month's file to `GEOIP_DB_PATH`; the Docker
  build runs it, so each deploy picks up the current month. If the download fails the build still succeeds and places
  from the network are blank until the next build. It adds roughly 130 MB to the image.
- **Limits and clean-up:** 60 requests an hour per network, so one connection can't invent phones and flood the table.
  `python manage.py usage_prune` deletes rows older than `USAGE_KEEP_DAYS`; the cron runs it once an hour.
- **Settings (web and cron):** `USAGE_ENABLED` (default `1`; `0` stores nothing and phones still get a normal answer),
  `GEOIP_DB_PATH` (default `backend/geo/dbip-city-lite.mmdb`, `/app/geo/...` in the image), `USAGE_KEEP_DAYS` (default `400`).
- **Before release:** the privacy policy must mention this count (see `docs/app-store-readiness.md`).

### OSHA regulation library (RAG) and amendment watch
`backend/regs/` keeps the official eCFR text of every OSHA section that Monday Minute and OTIS cite (49 sections).
They're split into paragraphs like 1910.147(d), with appendices kept separate.
- **Seeded** with the exact text the topic bank and OTIS entries were reviewed against (eCFR as of 2026-11-06), so it
  works on the first deploy.
- **Weekly sync** (`python manage.py regs_sync`, run by the cron) re-downloads those sections. If OSHA changed one,
  it records an *OSHA amendment* in the admin, pauses every Monday Minute topic that cites it, and takes every OTIS
  entry that cites it out of OTIS (with the reason). Turn them back on once they're re-reviewed. While a section has
  never been downloaded, the sync runs daily instead of weekly until it is there. *OSHA sections* and *OSHA
  amendments* have no Add button in the admin: the sync writes them (`python manage.py regs_sync --force` runs it now).
- **Monday Minute reviewer:** each review also gets the regulation paragraphs behind the brief and the talk, plus the
  closest real findings from the CSP review of the topic bank. Any OSHA claim the text doesn't support is MUST FIX.
  `MONDAY_RAG=0` turns this off. The writer still sees only the brief.
- **OTIS:** the phones' knowledge base includes the official paragraphs its entries and the Monday Minute facts point
  to (main text, about 250K characters). Plain-language entries rank first, and OTIS cites and links the section.
- **Safety test:** in the admin, select topics under *Monday Minute topics* and choose *Run the safety test*. Each
  topic gets a faithful talk plus copies with planted mistakes (skipping lockout, gloves at rotating parts,
  predicting a load's path, untrained rescue, a made-up OSHA rule, a shortcut, the topic's own never-say line). It
  reports the catch rate, how often good talks are wrongly blocked, and the time per talk, with and without RAG.
  Results are under *Monday Minute safety test runs*. CLI: `python manage.py monday_eval`. On the local CPU model,
  expect hours. Started from the admin, the test runs inside the web server, so a deploy or restart of the web service
  stops it and the hours already spent are lost: do not deploy while it runs. The cron marks a stopped run as failed
  within about 15 minutes, and it can then be started again. Only one test runs at a time; a second start is refused,
  from the admin and from `monday_eval`.

### OTIS on-device AI (API v2, Django Ninja)
OTIS's model runs on the phone with ExecuTorch: MLX or Core ML on iPhone, XNNPACK or Vulkan on Android. The server never runs it.
API v2 (`/api/v2/`, docs at `/api/v2/docs`) tells each phone what to run:
- `POST /api/v2/otis/manifest` takes the platform, memory, app version and the ExecuTorch backends the build links. It returns
  the on/off switch, the model to download (a pinned release, or the library's built-in Qwen3 chosen by memory) and the
  knowledge base version.
- `GET /api/v2/otis/kb` returns the knowledge base with an ETag. Phones send `If-None-Match` and get a 304 when nothing changed.
- `POST /api/v2/otis/feedback` takes "Was this helpful?" ratings, only from people who turn on *Help improve OTIS* in Settings
  (off by default). The question text is sent only if they also turn on *Include my question*. 30 an hour per network.

Two kinds of knowledge base entry:
- **Safety** entries are what OTIS answers safety questions from.
- **App help** entries (`kind: "support"`) are fixes for problems with the app: it closed, OTIS will not download, a
  sheet will not send. The phone shows them word for word. They never go through the on-device model and are never
  mixed into a safety answer. 34 ship today: 28 from migration `talks/0021_seed_support_kb` plus six older ones. Edit,
  add or unpublish them in the console (Knowledge base) or the admin, with no app update. The seed never overwrites
  wording you changed. App help is English only for now: a Spanish question finds the right entry, but the steps
  shown are in English.
- **App help can't name an OSHA section number** such as 1910.147. The admin and the console refuse it, because the
  weekly OSHA sync would treat it as a rule the entry depends on and could switch the entry off.
- **Report this answer:** every finished OTIS reply has this control, whatever *Help improve OTIS* says (Google Play
  asks for a way to flag AI answers). After a confirm it sends that one question and answer to you as a ticket. See
  *Support tickets and crash reports*.

In the admin:
- **OTIS rollout:** turn OTIS off per platform, set a minimum app version, or pause feedback.
- **OTIS model releases:** pin the exact model files (HTTPS links to the `.pte`, `tokenizer.json` and `tokenizer_config.json`)
  per platform, backend and memory tier. Change a release's key and phones offer an "Update OTIS" download. With no active
  release, phones use the built-in model, which downloads from Hugging Face.
- **OTIS feedback:** review the ratings.

The v1 endpoints (`/api/otis/kb/`, `/api/otis/config/`) stay up for app builds already installed.
The OSHA General Industry knowledge base and its safety review: `docs/otis-osha-kb-review.md`.
The app help entries and where each fact was checked in the code: `docs/otis-support-kb-review.md`.

### Support tickets and crash reports
How a problem with the app reaches you and how you answer it (code in `backend/support/`, phone side in `lib/support/`).
- **Three kinds of ticket:** a problem a person reported, an OTIS answer a person flagged, and a crash the app reported
  by itself. Each has a number like `ZH-123` and a status: New, In progress, Fixed or Closed.
- **Where a person reports a problem:** Settings → *Problems with the app* → *Report a problem*; the OTIS chat (typed,
  like "the app keeps closing", or the link on the empty chat); every OTIS screen that cannot chat (off, update needed,
  not set up, downloading, broken); and the app's own error screen. A report made with no signal is saved on the phone
  and sent when the app next comes to the front or *My reports* is opened. Each report carries a key made on the
  phone, so a retry never makes a second ticket.
- **What a problem report sends:** what the person wrote, their email only if they give one, the language (English or
  Spanish), phone model, system version, app version, and the phone's random install id, of which the server keeps
  only a salted hash. Their own words are stored as typed. The OTIS chat is never attached. That hash is the same one
  kept with a sign-up from the phone, so a problem report or a flagged answer can be linked to the person who signed
  in; the store privacy answers say so.
- **OTIS and app problems:** when someone tells OTIS the app is going wrong, OTIS shows the matching app help entry
  word for word and offers *Report this problem* and *That fixed it*. The report steps are in English and Spanish. The
  911 banner still comes first on every message, and an emergency message puts a report on hold.
- **Report this answer:** sends that one OTIS question (up to 500 characters), that one answer (up to 2,000), the model
  name and the same phone facts, only after the person confirms "Send this question and answer to Trainovate so a
  person can review it?". It is the one case where an OTIS question leaves the phone through this system.
- **Crash reports:** the app saves a short report when its own JavaScript hits an error: an uncaught error, an error
  while drawing a screen, an OTIS set-up or answer failure and, in store builds, a promise that fails with nobody
  listening. It is sent the next time the app comes to the front. If the phone itself closes the app (out of memory
  while OTIS loads, say) nothing is recorded, so never tell anyone that every crash is reported.
- **What a crash report holds:** error name, message and stack trace, whether the app could carry on, the screen's
  route (nothing after a `?` or `#`), app version, iPhone or Android, system version, phone model, the time, and the
  install id. The server keeps the id as a salted hash made for crash reports only, which does not match the hash kept
  with a sign-up or a problem report, so a crash cannot be traced to a person. The phone model and system version are
  kept on the single reports and on the crash ticket until they are 90 days old (`SUPPORT_CRASH_KEEP_DAYS`): then the
  single reports are deleted and `support_prune` clears the ticket's copy of the first phone's details. Never anything
  typed, OTIS questions or answers, names, emails, photos or location. The phone scrubs the text before saving it, and the server scrubs it again: emails, phone numbers, long
  numbers, network addresses and everything after the `?` in a web address are taken out. A crash report has no place
  for a person's name, email or typed words, and the server would ignore them if a phone sent them.
- **The switch:** Settings → *About and privacy* → *Crash reports*, on by default. Off stops recording and sending and
  deletes every report waiting on the phone. At most 20 wait on a phone, and the same error is saved once in 10 minutes.
- **One crash, one ticket:** the same error on the same app version and platform is one ticket with a count, however
  many phones send it. The newest 50 single reports per ticket are kept for the detail view; every report is still
  counted. The cron deletes single reports older than `SUPPORT_CRASH_KEEP_DAYS` once an hour (`python manage.py
  support_prune`). Tickets and their counts are not deleted by themselves, and a person's report stays until you delete
  it in the admin.
- **Email to you for a person's report:** one email to `OWNER_ALERT_EMAIL` through GoHighLevel, sent at once, or by the
  cron within about 15 minutes if GoHighLevel was slow or down. At most 10 single-ticket emails an hour; past that the
  cron sends the waiting ones together in one list email (30 per email, oldest first) and nothing is dropped. A report
  you already moved out of New before its email went gets no email.
- **Email to you for crashes:** never one per crash. Each cron run sends at most one email listing crashes that are
  new, or have now been reported 10, 100 or 1,000 times. A crash loop on thousands of phones is one ticket and at most
  four mentions. Mark a crash *Fixed* to stop hearing about it on that app version while it keeps counting. Mark it
  *Closed* and it opens again as New, and is emailed again, if it comes back.
- **The reporter in GoHighLevel:** only when the person gave an email and said it is OK to reply. The contact is
  made or found, the tag `zero-harm-support-ticket` is taken off and put back on (so a *Contact tag added*
  workflow fires for every ticket, not only the first), and a note is added with the ticket number and what they
  wrote. The cron retries for 2 days, 50 a run; *Try GoHighLevel again* in the admin retries by hand. A report with no
  email, and every crash, reaches GoHighLevel only as the email to you.
- **Where you work tickets:** the admin under *Support tickets* (the search box takes `ZH-12`), the console's *Support
  tickets* page, and the *Needs your attention* line in the back office. You can change the status, write a reply (on a
  problem report only) and keep a private note. The private note is never sent to a phone.
- **What the person sees:** under *My reports* in the app, each of that phone's problem reports with its status in
  words (Waiting to send, Received, Being looked at, Fixed, Closed) and your reply. *My reports* is per phone: reports
  usually do not follow a person to a new phone or survive a reinstall. They do follow when the app's data is restored
  from a backup or copied in a phone-to-phone transfer: on iPhone the install id is kept in the app's own storage
  (`lib/install.ts`), which iCloud backup and Quick Start copy by default, and some Android phones copy it in a device
  transfer (section 8 of `docs/google-play-readiness.md`). The new phone then shows the old phone's reports and counts
  as the phone that made the sign-up. Leaving that storage out of iPhone backups is a follow-up. Only problem reports are listed there. A reply on a
  flagged OTIS answer or a crash is a private note the person never sees: the console has no reply box for either and
  says why. A flagged answer carries no email, so there is no way to write back to that person.
- **Limits:** per network and hour, 30 reports, 60 crash reports and 60 *My reports* requests, each counted by itself.
  A body over 32 KB is refused. At most 200 new kinds of crash are saved in any 24 hours; past that only crashes
  already known are counted, and the crash email says so.
- **Settings (web and cron):** `SUPPORT_ENABLED` (default `1`; `0` stores nothing and phones still get a normal
  answer), `SUPPORT_CRASH_KEEP_DAYS` (default `90`), `PUBLIC_URL` (this server's public address, which puts an "Open
  it" link to the admin in ticket emails; blank means no link). Changing any of them restarts the service: see
  *Changing a Railway variable*.
- **Not seen yet:** nothing here has been run on a real phone or against the live GoHighLevel. Two things are assumed:
  that taking the tag off and putting it back makes a *Contact tag added* workflow fire again, and that taking off a
  tag that is not there is answered without a server error.
- **Before release:** the privacy policy and both stores' privacy answers must cover crash reports and problem
  reports (see `docs/app-store-readiness.md` and `docs/google-play-readiness.md`).

Run it locally with OrbStack or Docker Desktop:
```
cd backend
docker compose up --build
docker compose exec web python manage.py createsuperuser
```
Then open http://localhost:8000/admin/. Tests: `docker compose exec web python manage.py test`.

## Railway layout
- **Postgres** database.
- **web** service: this repo, root directory `/backend`, built from the Dockerfile, health check `/api/health/`. It
  runs one gunicorn process with 8 threads. Keep it at one process: the rate-limit counts are in that process's
  memory, so more processes would multiply every limit.
- **cron** service: same repo and root, start command `python manage.py cron`, schedule `*/15 * * * *` (every 15 minutes).
  Each run sends any due push first (the Sunday talk, Monday Minute, Zero Hour, feed items), once only. Then it marks
  a Monday Minute safety test that a deploy or restart stopped as failed, runs queued GHL syncs, retries pending
  sign-in sheets, sign-ups, talk ideas, owner alerts, sign-up removals, removal-request notices and invite-link tags,
  handles support tickets (emails about reports that did not go out the first time, the one email about new and
  growing crashes, and reporters not yet in GoHighLevel), sends the owner's daily summary after 7:00 AM Pacific, runs
  the weekly OSHA sync, and does the Monday Minute step (push, owner notices, screening of held comments, then
  writing). Once an hour it also looks for new Zero Hour files just before the episode push, deletes anonymous
  app-open rows older than `USAGE_KEEP_DAYS`, and deletes single crash reports older than `SUPPORT_CRASH_KEEP_DAYS`.
  If a run takes longer than 15 minutes (a Monday Minute write can), it keeps sending due pushes every 15 minutes
  itself, because Railway skips a scheduled run while the last one is still going. A step that fails is logged and the
  run ends as failed, with one exception: a failed look for new Zero Hour files is printed but does not fail the run.
- **Pushes are sent once:** each scheduled push carries a OneSignal idempotency key. The key stays the same when no
  answer came back or OneSignal answered 429 or 5xx (up to 3 times), so a push OneSignal did take is not delivered
  twice. It changes after a plain refusal (400, 401, 403) or when you send again on purpose, with the admin action or
  `python manage.py send_talk_push --issue N`.

**Changing a Railway variable:** changing a variable restarts the service, so do it when no Monday Minute safety
test is running. Railway applies a variable change by deploying the service again. On the web service that stops a
running safety test and the hours already spent are lost (see *Safety test*). Before you add or change a variable on
web, open *Monday Minute safety test runs* in the admin and check that none is running. This goes for every "set" in
this README and in the store checklists in `docs/`.

Variables (web and cron): `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL=${{Postgres.DATABASE_URL}}`,
`ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `GHL_LOCATION_ID`, `INGEST_KEY` (publishing from
GoHighLevel), `CONSOLE_KEY` (the content console; at least 32 characters, blank turns the console off),
`OWNER_ALERT_EMAIL` (where sign-up alerts, notices, ticket and crash emails and the daily summary go; blank turns them
off, see *Leads and alerts*).
Invite link (web, see *Invite link*): `APP_STORE_URL` and `PLAY_STORE_URL` (blank until the app is approved; the page says "coming soon").
Monday Minute's AI runs on your own **ollama** service by default (see below). Set on web and cron:
`AI_PROVIDER=local`, `LOCAL_AI_URL=http://ollama.railway.internal:11434`, optionally `LOCAL_AI_MODEL` (default `qwen3:8b`),
`LOCAL_AI_REVIEW_MODEL` (a bigger model for the safety review only, e.g. `qwen3:14b`), `LOCAL_AI_THREADS` (set it to the
ollama service's vCPU limit) and `LOCAL_AI_TIMEOUT` (seconds per call, default 1800). To use Claude instead: `AI_PROVIDER=anthropic` and
`ANTHROPIC_API_KEY` (optional `MONDAY_MODEL`, default `claude-opus-5-5`). `MONDAY_MINUTE_ENABLED=0` stops the whole
Monday Minute step: writing, the Monday push and screening of waiting comments. The safety gate is still checked, and
the app keeps serving talks that are out.
Monday Minute timing (leave both unset unless the AI server is slower or faster than expected): `MONDAY_STEP_BUDGET`
(default `1800`: seconds of AI work one cron run may use in all; what is not finished carries on in the next run;
`0` = no ceiling) and `LOCAL_AI_FAST_TIMEOUT` (default `180`: seconds to wait for one short AI answer, such as
screening one comment).
Usage count (optional, see *Where the app is used*): `USAGE_ENABLED` (default `1`), `USAGE_KEEP_DAYS` (default `400`), `GEOIP_DB_PATH`.
Support tickets and crash reports (web and cron, see *Support tickets and crash reports*): `SUPPORT_ENABLED` (default
`1`), `SUPPORT_CRASH_KEEP_DAYS` (default `90`), `PUBLIC_URL` (this server's public address, like
`https://api.example.com`; blank = no admin link in ticket emails).
Who is calling (leave both unset on Railway until the check below says otherwise): `CLIENT_IP_HEADER` (default
`X-Real-IP`: the header your host's proxy fills in with the caller's address; rate limits, lockouts and the place
lookup all count this address; blank skips it) and `NUM_PROXIES` (default `1`, only used when that header is missing:
how many proxies sit in front of the app, to count `X-Forwarded-For` entries from the right; `0` ignores
`X-Forwarded-For`).

- **ollama** service (local AI, CPU only, since Railway has no GPUs): deploy the Docker image `ollama/ollama`.
  Run it in the same region as Postgres (us-west2). Add a volume mounted at `/root/.ollama` so the model downloads once,
  and set the variables `OLLAMA_HOST=[::]:11434` (listen on Railway's private network), `OLLAMA_KEEP_ALIVE=10m` (unload
  when idle, so memory and cost drop between runs) and `OLLAMA_NO_CLOUD=true` (no Ollama cloud models, so nothing leaves
  your servers). On web and cron, `LOCAL_AI_URL=http://${{ollama.RAILWAY_PRIVATE_DOMAIN}}:11434`. Don't give it a public domain: only web and cron talk to it, over the private network. The first cron run pulls
  the model (about 5 GB for `qwen3:8b`). While loaded it uses about 6 GB of memory; a talk takes several minutes on CPU.
Create the admin login once with `railway ssh` → `python manage.py createsuperuser`.

### After a deploy: check the caller address
Every rate limit, the console wrong-key count, the admin sign-in limit, Monday Minute's "three different networks"
rule and the place lookup count the caller's network address. The server reads it from the `X-Real-IP` header first.
Railway's documentation says its edge puts the caller's address there, but **nobody has seen what Railway really sends
this service yet**. Until this check is done the limits are unproven on the live server.
1. After the deploy, open the web log and find the "Caller address:" line. There is one for each layout of proxy
   headers the server sees (at most 8 per restart). Addresses in it are masked (`174.75.x.x`). To write the line on
   demand: `curl -X POST https://<domain>/admin/login/` (it answers 403; that is fine).
2. "equals the FIRST entry" is the healthy one. Then check once that a caller cannot choose the address:
   `curl -X POST -H "X-Real-IP: 203.0.113.99" https://<domain>/admin/login/`. No new WARNING naming `203.0.x.x`
   means all is well.
3. A WARNING ("equals the LAST entry", "is NOT in X-Forwarded-For", or "X-Real-IP is missing") means the limits may be
   counting Railway's edge, or a value the caller chose. Each line names an outcome letter, and the top of
   `backend/zeroharm/net.py` says what to set `CLIENT_IP_HEADER` and `NUM_PROXIES` to for it (often `CLIENT_IP_HEADER`
   blank and `NUM_PROXIES=2`, but follow the table there). Change them on the web service when no safety test is
   running (see *Changing a Railway variable*), let it redeploy and read the new line.
What is at stake until then: if the header holds a shared address, strangers on that address share each limit with
you, and ten wrong admin sign-ins by anyone refuse yours for the hour. If a caller can set the header, the limits can
be dodged.

Other things to do around a deploy:
- Migrations run by themselves at start. Deploy when no Monday Minute safety test is running, because a deploy stops it.
- Set `OWNER_ALERT_EMAIL` (when no safety test is running, as for any variable), or removal requests from second phones, stuck sheets, a missed Monday Minute week, a talk
  waiting for approval, and new tickets and crashes reach nobody by email.
- The GoHighLevel private token needs `contacts.readonly` for the look that stops a note being written twice. Without
  it the log says "would not list the notes" and a rare second note can still be written.
- The first deploy with the app help entries changes the knowledge base version once, so each phone downloads the
  knowledge base one more time.

## Still to do before store submission
- Store screenshots, and for Google Play a 512x512 icon and a 1024x500 feature graphic. The app icon, splash art and
  Android notification icon are the brand mark and are in `assets/images/`.
- Paste the talk text for each issue in the admin, and clear the open pre-send flags in the topic ledger.
- Privacy policy and terms on public pages, and the stores' privacy answers. They must cover crash reports and
  problem reports now. The lists are in `docs/app-store-readiness.md` and `docs/google-play-readiness.md`.
- Set `EXPO_PUBLIC_PRIVACY_URL`, `EXPO_PUBLIC_TERMS_URL` and `EXPO_PUBLIC_SUPPORT_EMAIL` in EAS. Without them the
  app hides the Privacy policy, Terms of use, Contact support and Delete my data buttons.
- Apple Developer account under Trainovate Technologies (D-U-N-S) and a Google Play account as an Organization.
- Firebase for Android push: the `google-services.json` file and the key uploaded to OneSignal.
- A pass on real phones. The error screen, the report form, the crash reporter and the Android build have only been
  checked by automated tests so far.

## Holiday look

From December 1 to December 31 each year the app shows a holiday look on its own: an animated opening screen, string
lights across the Monday and Today tabs, and an evergreen accent. The first season starts early, on November 10, 2026.
On January 1 it goes back to normal. It follows the phone's date, so it works with no signal and needs no app update.

To override it without a new build, set `APP_THEME` on the backend (this restarts the web service; see *Changing a
Railway variable*): `auto` (follow the calendar), `default` (off now) or
`holiday` (on now). The app icon and the very first launch image are part of the build and do not change.

Design: `docs/holiday-splash.png`, `docs/holiday-monday.png`, `docs/holiday-today-dark.png`.

## App Store

See `docs/app-store-readiness.md` for what is done in code and what is still needed from the owner.

## Google Play

See `docs/google-play-readiness.md`: what is done in the repo, what only the owner can do, the proposed Data safety
answers, and the build and submit commands in order. `eas submit` sends the production build to the Internal testing
track (`eas.json`).

## iPhone Simulator

On a Mac with Xcode: `npm install`, then `npx expo run:ios`. Or build in the cloud with
`npx eas-cli@latest build --profile simulator --platform ios` and drag the result onto the Simulator.
