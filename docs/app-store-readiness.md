# Zero Harm: App Store readiness (iPhone first)

**Date:** 2026-11-10, updated 2026-11-11 for problem reports, crash reports and the sign-up rule. From a read-through of
the app against Apple's review rules. No iPhone build has been run yet, so the items under "Done in code" still need a
check on a real build. The Google Play checklist is in `docs/google-play-readiness.md`.

## Done in code

| Item | What changed |
|---|---|
| Push notifications in a store build | `app.config.js` switches OneSignal to Apple's production service when EAS builds the `production` profile. Development builds are unchanged. |
| Privacy manifest | `ios.privacyManifests` in `app.json` declares the required-reason APIs the app's libraries use, and that the app does no tracking. |
| Unused permission text | Location is "while using the app" and approximate only. The always-on, motion and full-accuracy strings are no longer added. |
| OTIS background download | Added the downloader's config plugin, which the "you can leave this screen" promise depends on. |
| iPad | `supportsTablet` is off for version 1. The app runs on iPad in iPhone size, and no iPad screenshots are needed. |
| Comments (rule 1.2) | Rules are built into the app so the box is never empty; the box says rule-breakers are removed and reports are handled in 24 hours; Block also sends a report. |
| AI and safety notes | OTIS chat shows "AI assistant, can be wrong, call 911"; Weekly talks say they add to training; Settings has an "About and privacy" section, including "not part of OSHA". |
| Flagging an AI answer | Every finished OTIS reply has "Report this answer". After a confirm it sends that one question and answer to Trainovate for a person to review. It does not depend on the "Help improve OTIS" switch. |
| Settings | Privacy policy, Terms of use, Contact support and Delete my data rows appear once their addresses are set (see below). Settings is now reachable from the Monday tab. |
| Wording | Removed the hard-coded "January 3" date, the PDF mention when there is no PDF, and "your first issue arrives Sunday". |
| Simulator | `eas.json` has a `simulator` profile for an iPhone Simulator build. |
| Sign-in is optional (rule 5.1.1) | The welcome screen asks for a name and email and says the app is free, with a "Not now" link. Every feature works without signing in. No password and no email code. |
| Newsletter consent | One line under the button says they will get Zero Harm Weekly by email each week and can unsubscribe anytime. The server stores that line and the time. |
| Removing a sign-up in the app | "Remove my info" on the phone that signed up deletes the sign-up at once (`POST /api/signups/remove/`): the name and email are deleted from the server and the newsletter tags the app added come off in GoHighLevel. Tags the contact had before the app are left alone. On any other phone (a second phone, or after a reinstall) it is a request: the app says "We got your request. A person will remove your info." and the owner carries it out by hand after checking it. A phone can never remove someone else's sign-up. |
| Problem reports | Settings has "Report a problem" and "My reports". A person can also tell OTIS, or use the app's own error screen. The line under Send says exactly what is sent. Reports work with no signal and send later. |
| Crash reports | The app saves a short report when its own code hits an error and sends it later. Settings → About and privacy has a "Crash reports" switch, on by default, with one line on what is and is not sent. Off also deletes reports waiting on the phone. Only errors in the app's JavaScript are caught, not every crash. |

## Only you can do these (in order)

1. **Apple Developer Program** for Trainovate Technologies (needs the D-U-N-S number), then `npx eas-cli@latest init` and create the app record for `ai.trainovate.zeroharm`.
2. **Deploy the backend** on Railway: set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `INGEST_KEY`, `BACKOFFICE_KEY` on web and cron, and `OWNER_ALERT_EMAIL` so reports, crashes and removal requests reach you. It must stay up through review. **Changing a variable restarts the service**, so set them when no Monday Minute safety test is running (see "Changing a Railway variable" in the README). After the deploy, do the caller address check in the README ("After a deploy: check the caller address").
3. **Give the build its public values** in EAS (production environment): `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_ONESIGNAL_APP_ID`, `EXPO_PUBLIC_PRIVACY_URL`, `EXPO_PUBLIC_TERMS_URL`, `EXPO_PUBLIC_SUPPORT_EMAIL`. Without the first two the store build shows an empty app. Without the last three the app hides the Privacy policy, Terms of use, Contact support and Delete my data buttons, which three app help answers point to.
4. **Privacy policy and terms of use** on a public page. The policy must cover everything in the checklist below. The terms need a no-tolerance line for abusive comments. Have a lawyer review both.
5. **A support email** that someone reads daily. Apple expects comment reports to be acted on within 24 hours.
6. **Real content before review:** at least one approved Monday Minute (two or three is better), the text for Zero Harm Weekly issues 1 and 2, one alert and one Learn item. Empty screens are the most common rejection.
7. **Push:** upload an APNs key (.p8) to OneSignal and send a test push to a TestFlight build.
8. **App Store Connect listing:** 6.9-inch iPhone screenshots from the real build, description that says Monday Minute is AI-written and OTIS is an on-device AI assistant (no claim of OSHA compliance), support and privacy URLs, age rating with user-generated content declared, and the App Privacy answers below.
9. **Test on a real iPhone:** the OTIS download (0.5 to 1.3 GB) with the app in the background, crew sign-in, print and share, and the holiday opening screen. Also the new parts, which have only been checked by automated tests: "Report a problem" with and without signal, "My reports", "Report this answer" under an OTIS reply, the "Crash reports" switch, and the app's error screen.
10. **After approval:** set `APP_STORE_URL` (and `PLAY_STORE_URL` once Android is live) on the Railway web service. This restarts the web service, so first check that no Monday Minute safety test is running (see "Changing a Railway variable" in the README). The invite link sent from GoHighLevel (`/get/?c={{contact.id}}`) then sends phones straight to the store, with no app update. Until then it shows "Coming soon".

## Privacy policy checklist

The policy must say, in plain words, that the app collects or sends each of these, why, who handles it and how long it is kept.

- [ ] Email, name and company from the optional sign-in, and the weekly newsletter they lead to.
- [ ] Crew names, finger signatures and crew photos on a sign-in sheet, sent only when "Save sheet to my records" is tapped, and filed in GoHighLevel under the supervisor's email.
- [ ] Comments, replies, ratings, talk ideas, and the display name shown with a comment.
- [ ] The push token, and what OneSignal records by itself.
- [ ] Approximate location for weather.
- [ ] The random install id. The server keeps it only as a scrambled (hashed) form. When the person signs in, that scrambled id is kept with their name and email, so anything else stored under it (problem reports, flagged answers, votes, the usage count) can be matched to them. Crash reports use a different scrambled id that cannot be matched.
- [ ] The anonymous daily usage count: once a day the app tells the server that a phone opened it, with the platform, app version and an approximate city, state and country. The place comes from the phone's approximate location when allowed, otherwise it is worked out from the network address, which is not stored. People can switch the count off in Settings. DB-IP is the source of the network place lookup.
- [ ] **Crash reports.** When the app hits an error it sends the error, where in the app's code it happened, the screen, the time, the app version, the phone model and system version, and a scrambled id made for crash reports only. That id does not match the one kept with a sign-up or a problem report, so a crash report cannot be traced to a person. Never what the person typed, their name, email, photos, location or OTIS chat. On by default, with a switch in Settings; turning it off deletes reports waiting on the phone. Single crash reports, with the phone model and system version, are deleted after 90 days (`SUPPORT_CRASH_KEEP_DAYS`), and the crash ticket's copy of the first phone's model, system version and screen is cleared at the same age; the count of how often an error happened is kept.
- [ ] **Problem reports (support tickets).** What the person writes, their email only if they give one for a reply, the language, the phone model, system version, app version and the install id. It can be linked to the person: it may hold their email, and its install id is the same one kept with a sign-up from that phone. Kept until deleted on request. The person can see the status and the reply in the app, under "My reports".
- [ ] **A flagged OTIS answer.** "Report this answer" sends that one question and that one answer to Trainovate, after the person confirms, with the same phone facts and install id as a problem report, so it can be linked to a sign-up from that phone too. Nothing else from the chat is sent. It is not listed under "My reports", so the person never sees a reply to it.
- [ ] **Tickets reach GoHighLevel.** Every problem report and flagged answer is emailed to Trainovate through GoHighLevel, and so is a summary of crashes. When the person gave an email for a reply, a GoHighLevel contact is made or updated for them with a tag and a note holding what they wrote.
- [ ] **OTIS.** Questions stay on the phone unless the person chooses to send a problem report or flag an answer, or turns on "Help improve OTIS" with "Include my question".
- [ ] **Hugging Face.** OTIS's model files download from Hugging Face (huggingface.co) unless a model release pinned in the admin points somewhere else. Hugging Face sees the phone's network address during the download, and the model library sends it one download-count request.
- [ ] The companies that handle data for the app: OneSignal (push), GoHighLevel (contacts, email, saved sheets, tickets), Railway (hosting), Hugging Face (model download), DB-IP (the city database, which runs on our own server), and the AI that screens comments.
- [ ] How long records are kept, and how to ask for deletion: "Remove my info" in the app, the "Delete my data" email, which now also names problem reports, and a public web page for people who no longer have the app.

## App Privacy answers

| Data | Linked to the person | Tracking | Purpose |
|---|---|---|---|
| Email address (asked for on the welcome screen, and on a problem report when the person wants a reply; both optional) | Yes | No | App functionality; marketing (the weekly newsletter, offers when turned on); customer support |
| Name (now also asked for on the welcome screen; optional) | Yes | No | App functionality; marketing (the newsletter is addressed to them) |
| Photos (crew photo on a saved sheet) | Yes | No | App functionality |
| Other user content (signed sheets, comments, notes, suggestions, OTIS question if opted in) | Yes | No | App functionality; analytics |
| Customer support (problem reports, and an OTIS question and answer a person flags) | Yes. Each is kept with the phone's scrambled install id, the same one kept with a sign-up's name and email, and a problem report may hold the person's email. | No | App functionality (customer support) |
| Diagnostics: crash data (the error and where in the app's code it happened, with phone model, system version and app version) | No. A crash report is kept under a scrambled id made for crash reports only, which does not match the id of a sign-up or a problem report, and has no name, email or account. The phone model and system version are kept on the single reports and on the crash ticket until they are 90 days old (`SUPPORT_CRASH_KEEP_DAYS`), then cleared. | No | App functionality (finding and fixing bugs) |
| Diagnostics: other diagnostic data (phone model, system version and app version sent with a problem report or a flagged answer) | Yes, for the same reason as Customer support. | No | App functionality (customer support) |
| Device ID (push id, hashed install id) | Yes. The hashed install id is kept with a sign-up's name and email when the person signs in. | No | App functionality |
| Product interaction (thumbs, OTIS ratings, notification opens, the once-a-day app open count) | Yes, until the code changes (see "Still open in code"). Thumbs and the daily count are stored under the same hashed install id that is kept with a sign-up's name and email, so for anyone who signed in they can be matched to them. | No | Analytics; app functionality |
| Coarse location (rounded to about 1 km for weather; city, state and country kept with the once-a-day app open count) | Yes, until the code changes (see "Still open in code"). The weather position is not kept. The city, state and country are kept on the daily count's row, under the same hashed install id as a sign-up. | No | App functionality; analytics |

## Notes for the reviewer (paste into App Store Connect)

- No account is needed. The first screen asks for a name and email for the free weekly newsletter. Tap "Not now" to skip it. Every feature works without signing in, and there is no password.
- A sign-up can be removed in the app, in Settings.
- Monday tab: this week's AI-written talk. Scroll down for thumbs, comments, Report and Block (the ••• on a comment) and the community rules shown before a first post. Comments are screened before they show, and reports are handled within 24 hours at the support address.
- Crew sign-in: Start crew sign-in, type a name, sign, optionally take a group photo, then Print or Share.
- OTIS: an AI assistant that runs on the phone. First use downloads a model over Wi-Fi. Questions stay on the phone unless you choose to send a problem report or flag an answer. Every answer has "Report this answer", which sends that one question and answer to us for review after a confirm.
- Problems with the app: Settings → Report a problem. The screen says exactly what is sent. Crash reports can be switched off in Settings → About and privacy.
- Notifications are off until turned on in Settings. "News and offers" is the only promotional one.
- The app gives general safety awareness. It is not legal, medical or compliance advice.

## Still open in code

- Removing a sign-up (name and email) in the app is done for the phone that signed up. From another phone it is a request the owner carries out by hand: delete the sign-up in the admin and take the newsletter tags off the contact in GoHighLevel. There is no one-click "carry out this removal" in the admin yet, and if `OWNER_ALERT_EMAIL` is blank nobody is told about the request.
- Still an email request: deleting your own comment, saved sign-in sheets and problem reports from the server. "Remove my info" does not touch problem reports. Deleting the GoHighLevel contact itself is also by hand (removal takes the tags off and marks it).
- Two lines in the app still say OTIS questions never leave the phone without naming the exceptions: the OTIS set-up screen ("Your questions never leave it") and Settings → OTIS ("Nothing you ask leaves it unless you turn this on"). They should match the sentence above before review.
- The "No" for crash data under App Privacy holds only once the server keeps crash reports under their own scrambled id and clears the first phone's details on a crash ticket after `SUPPORT_CRASH_KEEP_DAYS` (90 days). Both are in the code now (`crash_hash` in `backend/support/api.py`, and `support_prune`). Check that this is in the server you deploy before you send the form.
- Thumbs (votes) and the once-a-day app open count are stored under the same scrambled install id as a sign-up, so for anyone who signed in they can be matched to a name and email. The daily count's row also holds the city, state and country the phone was in that day. Until they get their own id in code, as crash reports have, answer "Yes" (linked to the person) for both Product interaction and Coarse location, as the table above does. Once they have their own id, both can go back to "No".
- The error screen, the report form and the crash reporter have not been seen on a phone, only in automated tests.
- An alert to you on every comment report (audit item A2), so the 24-hour promise does not depend on checking the dashboard.
- A reason picker on reports, a "Blocked people" list, and blocking agency words in display names (audit B6).
- The sign-in sheet note should say a contact record is created (audit E2). Wording needs the privacy policy first.
