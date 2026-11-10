# Zero Harm roadmap

Merged 2026-11-10 from three reviewed plans: the UI/UX audit and finish plan, the OTIS local-AI and knowledge base plan, and the lead-warmer features plan. Every UX finding was confirmed against the code by a second reviewer. Line numbers refer to the working tree on 2026-11-10.

## Do these first

1. **Railway variables (Jamil, today).** The `web` and `cron` services only have `DATABASE_URL` and `GHL_LOCATION_ID`. Without `DJANGO_SECRET_KEY` the server refuses to start, so every endpoint returns 404 and no push can go out (including Zero Hour EP 4 on Thu Nov 12). Set on **both** services: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `INGEST_KEY`, `ANTHROPIC_API_KEY`, `CONSOLE_KEY` (long random, same value in `console/.env.local`). The cron schedule is already `*/15 * * * *`; only the README is wrong.
2. **Deploy this branch** so the console API, the content-version endpoint and migration `0008_shared_cache_table` are live.
3. Then M0 below.

## Done in this session (uncommitted)

- **Content console** (`console/`, run on your Mac with `npm run dev`): overview, talks with phone preview, Spanish drafting and approval, alerts and resources, Zero Hour huddle cards, OTIS knowledge base, talk ideas, and one-off notifications to a single opt-in group. Backed by `/api/console/` (key-protected, rate-limited) in `backend/talks/console.py`, 58 backend tests passing.
- **Live refresh in the app** (`lib/live.ts`): every push tells phones to refresh, and the app checks `/api/content-version/` when it comes back to the foreground, so Today, alerts, Learn, Zero Hour and OTIS update without a new release.
- **Footage intro** (`components/IntroSplash.tsx`, `assets/video/intro.mp4`, 590 KB, credits in `assets/video/CREDITS.md`).
- **Brand kit** in Claude Design: https://claude.ai/artifact/TULDvzoopkVXU8kjtiqPWr

---

# Finish Zero Harm: roadmap (as of 2026-11-10)

**Status:** The v1 core works: talks, crew sign-in, OTIS, Zero Hour, alerts and weather, and typecheck and lint pass. It cannot be submitted yet. There are no store accounts and no privacy policy, the production env vars are not in EAS, OneSignal is still in `"mode": "development"` (app.json:67), and Inspect and Report are placeholder tabs. A reviewer also has no released talk to open until 2027-01-03. There are about 100 verified UX findings: 8 high, about 50 medium, the rest low. Most are glove-sized tap targets, stalls on weak signal, and English-only safety copy.

I checked the repo (read-only) and confirmed four things:
- The README cron is still `59 18,19 * * 0` (README.md:43).
- `expo-updates`, `expo-localization`, `expo-haptics`, `expo-image`, `expo-network` and `expo-image-manipulator` are not installed.
- The Inspect and Report tabs are live (`app/(tabs)/_layout.tsx:29-30`).
- `supportsTablet` is true (app.json:11).

## Key dates

| Date | Gate |
|---|---|
| **Thu 2026-11-12 13:00 UTC** | Zero Hour ep 4 release and push. The Railway cron must run `*/15 * * * *` by then. |
| Fri 2026-11-28 | v1.0 code freeze (M0 plus the M1 v1.0 slice) |
| Dec 1–5 | Submit iOS and Android |
| ~Dec 15 | January talk text, Spanish and accuracy review finished |
| **Sun 2027-01-03 19:59 UTC** | First 2027 talk push |
| ~Feb 22 | Submit the first update (U1). Live around Mar 1. |
| Apr 26 | Harness checklist published (issue #18, May 3, falls month) |
| May 1 | Heat planner live |
| Jun 1 | Forklift checklist published (issue #27, Jul 5) |

## Conflicts between the plans, resolved

1. **Inspect and Report:** they are hidden in v1.0 with `href: null`, and the 911/stop-work block moves to Today. Both tabs come back in U1 with Ladder and Near-miss. This avoids Apple 2.1/2.2 rejections for placeholder tabs.
2. **Timing of the first update:** the features plan wanted the first update submitted around Dec 4. That is not possible alongside v1.0: features need about 34 dev days and v1.0 about 20. **v1.0 ships in Dec and U1 in about March.** The "Arrives in the first update" promise is still kept.
3. **When to add native modules:** v1.0 is the first production binary, so adding native modules now costs only a dev-client rebuild. **`expo-updates` and `expo-image-manipulator` go into v1.0.** With expo-updates in v1.0, low-severity UX fixes and hotfixes ship over the air (OTA) in Dec–Jan, and the M3 May/June JS changes ship OTA too. The other native modules (localization, haptics, crypto, network, image) come with U1.
4. **Duplicate sheets:** SigninSheet `client_id` dedupe on the backend goes in now (M0). The client-side in-flight guard goes in v1.0. The generic outbox comes in U1.
5. **Dark-mode red:** do not lighten dark `danger`. Add a `dangerFill` token using palette.stopRed #C1272D in both themes (white on it is 5.8:1).
6. **Alert jurisdiction copy:** keep "federal, Nevada and Las Vegas", because backend models.py:99 only defines those three. Only add years to the "Planned for…" dates. The launch plan's suggested reword is rejected.
7. **Muted text color:** #5B6773 on #ECEEEF measures 4.96:1, which passes AA. Darkening it is optional polish, not a fix.
8. **Corrections to proposed fixes, carried into the plan:**
   - The 911 trigger strips safe phrases before matching. It never vetoes the whole message.
   - Accent stripping uses NFD plus `[̀-ͯ]`, not `\p{Diacritic}`, which Hermes may not support.
   - The header height comes from expo-router's bundled navigation. `@react-navigation/elements` is not installed.
   - `tappable-examples` must use `onPress={() => ask()}`. Otherwise `ask` receives the event object as its argument.
   - The language choice is stored in `expo-sqlite/kv-store`. There is no `lib/storage` module.

---

## M0: Ship-blockers (store submission). Window Nov 10 – Dec 5.

| # | What | Why | Files | Effort | Owner |
|---|---|---|---|---|---|
| M0-1 | **Set the Railway cron to `*/15 * * * *`** and fix the README | cron.py drives the Thursday Zero Hour push, the hourly GHL episode sync, feed pushes and sheet retries. If it runs Sundays only, all of those are broken in production now. | README.md:43, backend/talks/management/commands/cron.py | 0.25d | **Jamil, by Nov 12** (code fixes README) |
| M0-2 | Content for the reviewer: a released "Sample talk" (issue 0) with body, crew question, PDF and approved Spanish, shown on Today until 2027 issue 1. Decide whether it goes in the archive and the OTIS KB. Write App Review notes. | No talk is released until Jan 3, so talk/[issue] and crew sign-in can't be reached during review | backend/talks/models.py, views.py, fixtures/talks_2027.json, app/(tabs)/index.tsx | 1.5d | both |
| M0-3 | Hide Inspect and Report (`href: null`). Trim the tools.tsx ComingSoon cards to one line with a year. Move the stop-work and **Call 911** block onto Today using a shared `Call911Button`. | Placeholder tabs risk rejection. This also covers `report-911-not-tappable` and `placeholder-tabs-dead-ends`. | app/(tabs)/_layout.tsx:29-30, report.tsx, inspect.tsx, tools.tsx, index.tsx | 0.5d | code |
| M0-4 | Production config: EAS env vars `EXPO_PUBLIC_API_URL` and `EXPO_PUBLIC_ONESIGNAL_APP_ID`, `"environment"` in the eas.json profiles, a custom API domain added to `DJANGO_ALLOWED_HOSTS`, a visible error in release builds when `isConfigured()` is false, and a higher HSTS value once HTTPS is confirmed | .env is gitignored, so EAS builds ship with an empty API URL and push, sheets and weather fail silently. A railway.app URL baked into the binary can't be changed later. | eas.json, lib/config.ts, backend/zeroharm/settings.py:96 | 0.5d | both |
| M0-5 | OneSignal production: `mode: "production"`, Notification Service Extension credentials for EAS, APNs .p8 key, FCM v1. On TestFlight, check all 4 tags and where each push opens. | Production push will not work in development mode | app.json:67, lib/push.ts | 1d | both |
| M0-6 | Document every backend env var (INGEST_KEY, ANTHROPIC_API_KEY/MODEL, OTIS_*, DJANGO_*). Set them on **both the web and cron services**. | GHL ingest and Spanish drafting fail without them. C0 runs on cron. | backend/.env.example, README.md | 0.25d | both |
| M0-7 | Real rate limits: switch to DatabaseCache (createcachetable in the Dockerfile CMD), read the last X-Forwarded-For hop, add a spoofed-XFF test | With LocMemCache and 2 workers each worker counts separately, and a spoofed first XFF entry bypasses every limit on endpoints that create GHL contacts | backend/zeroharm/settings.py:67, talks/views.py, Dockerfile, tests.py | 0.5d | code |
| M0-8 | SigninSheet `client_id` with dedupe (migration 0008). The app sends a per-install id plus session_id. | A resend after a timeout creates duplicate sheets and GHL notes. `flush-race-duplicate` depends on this. | backend/talks/models.py, views.py, tests.py, lib/sheets.ts | 0.5d | code |
| M0-9 | Privacy policy hosted at a stable URL. In Settings, an "About and privacy" section: Privacy, Terms, Support, version, "Request deletion of my data", and "Delete sign-in sheets on this phone" (new delete functions in lib/signins.ts). Link the policy from the sign-in and sign-up copy. | Both stores require it. Sheets send names, signatures and photos to GHL. | app/settings.tsx, app/signin/[session].tsx, lib/signins.ts, lib/db.ts, backend views/urls | 2d | both (Jamil: legal wording) |
| M0-10 | Apple App Privacy, Play Data safety, and a check of the privacy manifest in the TestFlight archive | Required for submission | app.json | 0.5d | Jamil |
| M0-11 | Android: `blockedPermissions` for READ/WRITE_EXTERNAL_STORAGE and ACCESS_FINE_LOCATION. Either declare the dataSync foreground service (with a video) or test the download with it blocked. Remove the duplicate `expo-build-properties` entry. Run `npx expo-doctor`. | Avoids Play policy holds | app.json | 0.75d | both |
| M0-12 | Apple and Play **organization** accounts (D-U-N-S), the App Store Connect and Play apps, a Play service account kept out of git, and `submit.production` in eas.json | Verification can take 1–3 weeks. **Start this week.** | eas.json, .gitignore | 2d | both (Jamil starts) |
| M0-13 | Add `expo-updates` (runtimeVersion policy appVersion) and `expo-image-manipulator` with `npx expo install`, then build a new dev client. Read the SDK 58 docs first. | Enables OTA patches Dec–Jan and the photo-size fix | package.json, app.json | 0.5d | code |
| M0-14 | App tests: jest-expo. Cover `looksUrgent` in English and Spanish, including the new false-positive and Spanish cases; the TRIR/DART math; the talk block parser (moved to lib/markdown.ts); and `flushSheets` with a mocked db and api. Write a manual airplane-mode checklist. Decide on crash reporting. | There are no app tests on the safety-critical paths | package.json, lib/otis/safety.ts, lib/sheets.ts, app/(tabs)/tools.tsx | 1.5d | code |
| M0-15 | Store listing: decide on iPad, take screenshots (Today with the sample talk, sign-in, huddle card, OTIS with the 911 rail, TRIR, the Spanish toggle), EN/ES copy, age rating, IARC with an 18+ target audience | Required | app.json, assets/images | 2.5d | Jamil |
| M0-16 | Test OTIS on a 6 GB iPhone and a 4 GB Android phone: download, first answer, a 10-turn chat, backgrounding. Add the increased-memory entitlement if needed. Rewrite the stale README sections. | An out-of-memory crash would be a likely rejection | app/otis.tsx, app.json, README.md | 1d | both |
| **C0** | Claude: a shared `claude.py` client (structured outputs, stop_reason handling, fallbacks), an `AiJob` queue run by cron, an `AiRun` cost log, and `AI_MONTHLY_BUDGET_USD`. Stopgap until it lands: raise gunicorn `--timeout` or draft one talk at a time. | The admin "Draft Spanish" action runs up to 120 s inside a request, and gunicorn kills workers at 30 s | backend/requirements.txt, talks/claude.py (new), models.py, admin.py, cron.py, settings.py, tests.py | 2d | both |
| **C1** | Claude: harden translate.py. Use the schema, check citations, headings, numbers and length ratio, refuse a blank body, never overwrite reviewed Spanish, and make `_approve_spanish` call save() so the KB version moves. | The January Spanish drafts must be reviewed by mid-Dec | backend/talks/translate.py, models.py, admin.py, views.py | 1.5d | code |

M0 effort: about 12 code days (including C0 and C1) and about 9 days of Jamil's time.

---

## M1: UX pass (verified findings)

There are three release slices. Severity tags are H, M and L.
- **v1.0** (Nov 10–28, about 12 code days): all high findings and the core medium ones.
- **OTA** (Dec 8 – Jan 29, about 7 days): JS-only fixes shipped with EAS Update as v1.0.x.
- **U1**: items that need a new native module, backend fields, or translated content.

**Cut order if behind on Nov 24:** move the medium items in D, E and H to OTA. Never cut A, B-high or C.

### A. Emergency and 911 (v1.0, 1.5d)
- `911-double-tap-keyboard` (H), app/otis.tsx:164: add `keyboardShouldPersistTaps="handled"` and a keyboardDismissMode. Call `Keyboard.dismiss()` when looksUrgent.
- `urgent-card-english-only` (H), otis.tsx:189: add `Msg.lang` and render from a `URGENT[lang]` table.
- `danger-on-dark` (M), WeatherBar.tsx:70, otis.tsx:258, zero-hour/[n].tsx:88, theme.ts:40: use a `dangerFill` token set to stopRed in both themes.
- `report-911-not-tappable` (M), report.tsx:12: handled by M0-3. Also add tap-to-call to the Zero Hour emergency block.
- `tel-no-fallback` (L), otis.tsx:190: try/catch plus a localized alert, inside the shared Call911Button.
- `urgent-false-positives` (L), lib/otis/safety.ts:9: strip safe phrases (don't veto), add Spanish patterns, add jest cases in both directions.

### B. Weak signal and offline (v1.0 core 3d, OTA 1d, U1 0.5d)
- **v1.0:**
  - `alert-detail-waits-on-network` (H), lib/feed.ts:48, lib/talks.ts:55, alert/[id].tsx:16-19: read the cache by id first and refresh in the background. Return ok|offline|missing and show a Retry button.
  - `save-no-feedback-during-gettalk` (M), signin/[session].tsx:102,125: call setBusy first, load the talk once cache-first, show messages instead of silent returns.
  - `kb-empty-first-run` (M), otis.tsx:113 and kb.ts:13-25: cache-first `loadKb`, track kbState, answer "OTIS needs a signal one time" when the KB is empty.
  - `episode-open-blocks-on-network` (M), zero-hour/[n].tsx:15, and `episode-null-dead-end` (M), :18: memoize episodes with in-flight dedupe, return `{ep, offline}`, add Try again.
  - `offline-status-buried` (M), index.tsx:100, feed.ts:35, alerts.tsx:16: add `listFeedWithStatus` so learn.tsx and getFeedItem don't break, put the offline banner at the top, add a `refreshControl` prop on Screen.
  - `talk-pending-dead-end` (M), talk/[issue].tsx:111: show the PDF hint only when pdf_url exists, label the spinner.
  - `weather-error-hides-bar` (M), WeatherBar.tsx:27, and `weather-never-refreshes` (M), :14: status-typed result, try/catch around the position calls, busy state, last reading in kv-store with its age, useFocusEffect plus an AppState listener.
  - `video-no-error-state` (M), zero-hour/[n].tsx:47: handle statusChange (check the SDK 58 payload shape).
  - `settings-error-conflated` (M), settings.tsx:35.
  - `suggest-no-offline-queue` (M), suggest.tsx:39: in v1.0, give `!isConfigured()` its own message. The queue itself comes in U1 with the generic outbox.
- **OTA:**
  - `focus-refetch-writes` (L), talks.ts:24
  - `refetch-on-every-focus` (L), learn.tsx:17
  - `offline-empty-misleading` (L), zero-hour/index.tsx:17
  - `archive-offline-and-search-ux` (L), archive.tsx:19
  - `storage-parse-unsafe` (L), profile.ts:9, push.ts:40
  - `splash-stuck-on-font-error` (L), _layout.tsx:30
  - `default-error-boundary` (L), _layout.tsx:14
- **U1:** `thumbnails-not-cached-offline` (L), EpisodeCard.tsx:17, using expo-image.

### C. Crew sign-in reliability (v1.0, 4d)
- `flush-race-duplicate` (M), lib/sheets.ts:34: module-level in-flight guard. Save sends only its own row with about a 20 s timeout. Send the client_id from M0-8.
- `queued-sheet-never-retried` and `outbox-flush-only-cold-start` (M), signin:113, _layout.tsx:34-37: flush on AppState 'active' with `.catch`, show "Waiting to send" through `isQueued()`. The reconnect listener (expo-network) comes in U1.
- `talk-start-duplicate-sessions` (M), talk/[issue].tsx:52: busy guard, `findOpenSession`, "Continue sign-in (N signed)", prefill the supervisor name.
- `no-undo-signature` (M), lib/signins.ts:33: `deleteSignin` with confirmation, 44 pt rows.
- `remove-photo-no-confirm` (M), signin:161: add a confirmation.
- `empty-signature-silent` (M), signin:172: add `onEmpty`, announce the save, refocus the name field.
- `held-on-utc-date` (M), sheets.ts:23 and pdf.ts:18,42: build held_on from local date parts, print local times.
- `photo-full-res-base64` (M), signin:63: resize so the long edge is 1600 px at compress 0.6, select explicit columns, add `listSigninNames`.
- `talk-start-buried` (M), talk/[issue].tsx:133: add a `footer` prop to Screen, or a "Run the talk" card near the top.
- `pdf-pagination` (M), pdf.ts:26: thead, avoid row breaks, table before the photo, "Conducted by" line.
- **OTA:**
  - `save-disabled-no-reason` (L), signin:205
  - `status-not-announced` (L), signin:207
  - `signature-pad-a11y` (L), signin:171 (labels only)
  - `pdf-backgrounds-dropped` (L), pdf.ts:31

### D. Gloves and glare (v1.0 1.5d, OTA 1d)
- **v1.0:**
  - `small-text-links` (H), index.tsx:39,75,85,118,119 and WeatherBar.tsx:68-69: a shared `LinkRow` (Link asChild, Pressable, minHeight 44, hitSlop 8). Settings becomes a 44 pt gear icon.
  - `keyboard-covers-form` and `screen-keyboard-covers-fields` (H), ui.tsx:29: `automaticallyAdjustKeyboardInsets` and a dismiss mode, an iOS Done accessory for number pads (tools.tsx:26-28, signin:155), Tools results above the inputs. Check Android edge-to-edge.
  - `no-press-feedback` and `episodecard-no-press-feedback` (M), feed.tsx:15,34, index.tsx:53,91,106, WeatherBar.tsx:24,52, EpisodeCard.tsx:11: a shared `Tap` with pressed opacity 0.7 or android_ripple, plus a `touch.min` token (`no-reduce-motion-or-touch-token`, theme.ts:58).
  - `learn-link-dark-mode-and-target` (M), learn.tsx:29
  - `source-targets-small` (M), otis.tsx:255
  - `tappable-examples` (M), otis.tsx:184
  - `field-border-contrast` (M), ui.tsx:90: `fieldBorder` token, light #7A8590 and dark #6B7884, width 1.5.
- **OTA:**
  - `archive-chip-target` (L), archive.tsx:73
  - `suggest-chip-target-role` (L), suggest.tsx:105
  - `switch-low-contrast-small-target` (L), settings.tsx:64
  - `yellow-primary-low-edge-contrast` (L), ui.tsx:69 (ink border now, haptics in U1)
  - `disabled-button-unreadable` (L), ui.tsx:70
  - `tab-active-state-color-only` (L), (tabs)/_layout.tsx:23
  - `input-single-line` (L), otis.tsx:218
  - `kav-hardcoded-offset` (L), otis.tsx:163

### E. Screen readers and large text (v1.0 1.5d, OTA 0.5d)
- **v1.0:**
  - `field-label-not-associated` and `field-label-not-linked` (H), ui.tsx:87-88: default `accessibilityLabel` to the label, hide the visible label from screen readers, add hint and error props, label at 15 pt bodyBold in t.text, `autoCorrect={false}` on name fields.
  - `button-busy-silent` (M), ui.tsx:73
  - `nested-pressable-placard` (M), index.tsx:53
  - `weather-a11y-label-incomplete` (M), WeatherBar.tsx:41
  - `no-announce-answer` (M), otis.tsx:199
- **OTA:**
  - Header roles (L): ui.tsx:36,102 and signin:146. Add a role on Heading and a new `SectionTitle`.
  - `alertcard-label-drops-context` (L), feed.tsx:17
  - `spinners-unlabeled` (L)
  - `send-a11y-mismatch` (L), otis.tsx:231
  - `dynamic-type-clipping` (L), index.tsx:135
  - `no-font-scale-caps` (L), ui.tsx:109 (display type only)
  - `tools-results-a11y-nan` (L), tools.tsx:18
  - `checkbox-glyph-not-interactive` (L), zero-hour/[n].tsx:28

### F. OTIS setup and chat (v1.0 1d, OTA 0.5d, U1 1.5d)
- **v1.0:**
  - `download-progress-scale` (H), otis.tsx:174: the value is 0–100, so clamp it as pct, fix the bar width, add a progressbar role.
  - `setup-marked-before-download` (M), :86: add a Try again button and stop showing the raw error.
  - `leave-screen-copy-wrong` (M), :178: new copy plus `useKeepAwake` in a child component.
  - `sources-on-refusal` (M), :143
  - `no-stop-generation` (M), :223
- **OTA** (after the C3b baseline for the prompt and KB changes):
  - `autoscroll-hijack` (L), :166
  - `per-token-rerender` (L), :141
  - `intro-flash` (L), :52
  - `heading-not-shared` (L), :245
  - `tokenizer-keeps-periods` (L), kb.ts:39
  - `spanish-detect-weak` (L), prompt.ts:27
- **U1:**
  - `newchat-reloads-model` (L), :95
  - `kb-reindex-every-query` (L), kb.ts:47
  - A cellular-data check before the download (expo-network)

### G. Spanish (v1.0 2.5d, U1 about 5d)
- **v1.0 foundation:** `english-only-chrome` and `no-spanish-group` (M), _layout.tsx:49 and suggest.tsx:64. Add `lib/i18n.ts` (en/es), a `useLang` hook backed by kv-store `lang`, a Settings switch, and have the talk toggle read and write the same value. Auto-detection with expo-localization comes in U1.
- **v1.0 crew-facing and safety-facing strings:**
  - `signin-english-only` (M), signin:142, with `lang` passed through as a route param
  - `talk-labels-english` (M), talk:134
  - `today-english-only` (M), index.tsx:59
  - `ui-english-only` (M), otis.tsx:72 (setup screen and errors)
  - `archive-spanish-search` (M), archive.tsx:26
  - `zero-hour-english-only` (H): the static labels and LEGAL text only
- **U1:**
  - `zero-hour-english-only` (H, L): Episode `_es` fields plus spanish_status (backend), drafted through the C1 pipeline
  - `pdf-language` (L), pdf.ts:39, with a `lang` column on sessions
  - The remaining Settings, Tools and Suggest strings
- Jamil needs a native speaker to review every string, especially the 911 and stop-work copy.

### H. Dead ends and copy (v1.0 0.5d, OTA 1.5d)
- **v1.0:**
  - `placeholder-tabs-dead-ends` (M): handled by M0-3
  - `cold-heat-chip-dead-end` (M), WeatherBar.tsx:54: link only when the theme has released talks. The full fix (route to /heat) comes in M3.
  - `settings-permission-stale` (M), settings.tsx:19: `getPermission()` on mount and on 'active'
  - `no-captions-loud-dock` (M), zero-hour/[n].tsx:67: change the copy now. WebVTT or a transcript comes in U1, if the video has no burned-in captions (Jamil checks).
- **OTA:**
  - `nws-alert-chip-no-detail` (M), WeatherBar.tsx:46
  - `alert-empty-dead-ends` (L), alerts.tsx:17
  - `settings-modal-no-close` (L), settings.tsx:74
  - `not-found-link-tiny-target` (L), +not-found.tsx:11
  - `effective-date-tense` (L), alert/[id].tsx:27
  - `alert-body-markdown-raw` (L), alert/[id].tsx:21
  - `suggest-contact-flag-stale` (L), suggest.tsx:45
  - `suggest-guidance-in-placeholder` (L), suggest.tsx:72
  - `tools-jargon-and-scaling` (L), tools.tsx:32
  - `settings-copy-geography` (L), settings.tsx:77
  - `copy-audio-vs-watch` (L), zero-hour/index.tsx:15
  - `pdf-buried-and-online-only` (L), zero-hour/[n].tsx:96 (move the button now, offline cache in U1)

### I. Theme and visuals (v1.0 0.5d, OTA 0.5d)
- **v1.0:** `nav-theme-not-from-tokens` (M), _layout.tsx:46
- **OTA:**
  - `root-bg-yellow-and-splash-mismatch` (L), app.json:100,50,59
  - `hardcoded-show-colors` (L), EpisodeCard.tsx:32
  - `compact-thumb-crop` (L), EpisodeCard.tsx:34
  - `screen-no-max-width-tablet` (L), ui.tsx:26, only if iPad stays
- **U1 or defer:** `zero-hour-list-not-virtualized` (L), zero-hour/index.tsx:18

---

## Claude work, scheduled

| # | What | Window | Why then | Files | Effort | Owner |
|---|---|---|---|---|---|---|
| C0, C1 | Job queue and translate hardening | M0, by Dec 1 | January Spanish drafts. The request timeout bug. | see M0 | 3.5d | code / both |
| C2 | Pre-publish accuracy review: citations checked against eCFR in code, an unsafe-advice rubric, Spanish back-translation. Fable 5.2 if the org's retention allows, otherwise Opus 5.5. | Dec 1–12 | Must run on January talks before they send. Fallback: a CSP reviews manually. | talks/review.py (new), models.py, admin.py, ghl_sync.py | 3d | both |
| C3a | KbEntry status (draft/approved/retired), `body_es`, `otis_kb` serving approved entries only, Episode updated_at in the KB version, a drafting form with verbatim source quotes | Dec 8 – Jan 15 | Must land before any machine-drafted KB entry. Ship the migration and the filter together. | models.py, views.py, admin.py, kb_author.py | 2d | both |
| C4 | Zero Hour huddle-card drafts from the card PDF, written into `Episode.draft` only, never the live fields | Dec 8 – Jan 15 | Episodes arrive weekly with needs_details. Watch for release_at passing before approval. | zero_hour.py, models.py, admin.py | 1.5d | code |
| C3b | Bilingual OTIS eval: about 200 synthetic cases, deterministic graders plus an Opus judge via Batches, release gates | Jan (U1) | Baseline needed before the OTA and U1 changes to kb.ts and prompt.ts. Real user questions are never used. | backend/otis_eval/ (new) | 3d | both |
| C5 | Weekly regulatory-alert drafts (Sonnet 5.5 plus web search on allowed domains). An ingest guard so an `ai_draft` can't unpublish a live alert or send a push. | Jan–Feb (U1) | Needs C0. The guard ships with it. | views.py, models.py, admin.py, cron.py, reg_watch.py | 2.5d | both |
| C6 | Near-miss triage on Haiku 5.5 after a regex PII pass, with a manual path on refusal | Feb, after F3 | Blocked on the recipient and retention decision | triage.py, models.py, views.py, admin.py | 2d | both |

---

## M2: First update (U1). Build Jan 4 – Feb 19, submit ~Feb 22, live ~Mar 1.

| # | What | Why | Files | Effort | Owner |
|---|---|---|---|---|---|
| F0 | Foundations: a generic outbox with `client_id`, backoff, flush on 'active' and on reconnect, and `pendingCount()` (this replaces sheet_outbox and adds a suggestions queue); `pdfShell`; photos saved as files (lib/photos.ts); expo-localization, expo-haptics, expo-crypto, expo-network and expo-image; camera and photo permission text that covers inspections and near-miss | Every new feature needs offline sends, a PDF, photos and Spanish | lib/db.ts, lib/outbox.ts, lib/pdf.ts, lib/photos.ts, lib/i18n.ts, app.json, backend models and views | 4d | code |
| F1 | A data-driven checklist engine: ChecklistTemplate and ChecklistItem in the admin, `/api/checklists/`, SQLite cache plus a bundled copy, inspections that snapshot their template, `deriveResult`, one item per screen with 64 pt Pass/Fail/N/A, a DANGER tag-out placard, an inspection PDF, InspectionRecord synced to GHL with a `zero-harm-tagout` tag | Lets Harness and Forklift ship as content later | backend talks/*, lib/checklists.ts, lib/inspections.ts, app/(tabs)/inspect.tsx, app/inspect/*, app/inspection/* | 6d | code |
| F2 | Ladder check (29 CFR 1910.23(b)(9)-(10)). Bring the Inspect tab back. | Promised for the first update | fixtures/checklists.json, inspect.tsx | 1.5d | both |
| F3 | Near-miss report: 4 steps, anonymous by default, no GPS, the 911 rail, sent through the outbox, a PDF, NearMissReport synced to GHL (to the recipient's contact only), a purge after 90 days. Bring the Report tab back. | Promised. **Blocked on choosing the recipient.** | app/(tabs)/report.tsx, lib/nearmiss.ts, backend | 5d | both |
| F4 | "Is it recordable?": a deterministic 1904 decision tree with a citation at every node, 30+ jest cases, on the phone only, a worksheet PDF | Promised. Too high-stakes for an LLM or admin-editable data. | lib/recordable/*, app/recordable.tsx, tools.tsx | 5d | both (Jamil: recordkeeping-pro review) |
| M1-U1 | The UX items tagged U1 above (Zero Hour `_es` fields, pdf-language, expo-image thumbnails, captions or transcript, new-chat model reload, KB index, reconnect flush, cellular check, haptics, offline card PDF) | Need native modules, backend fields or content | see M1 | 5d | code |
| F9 | Release: deploy the Railway migrations first, update the privacy labels and policy, set up GHL workflows for the tagout, near-miss and inspection tags, update the README, build and submit | Review and compliance | app.json, eas.json, README.md | 1.5d | Jamil |
| C3b, C5, C6 | See the Claude table | | | 7.5d | both |

U1 is about 40 code days against roughly 35 working days. **Cut line:** if F4 slips, it can ship OTA in March because it is JS-only with no backend. F3 cannot ship OTA, because it needs the new permission strings in a binary.

## M3: Spring. Mar – Jun 1, mostly admin content plus OTA.

| # | What | Target | Files | Effort | Owner |
|---|---|---|---|---|---|
| F6 | Harness and lanyard check (1910.140(c)(18), Z359), published as admin content. Optional per-item images shipped OTA. | Apr 26 | fixtures/checklists.json, admin.py | 1.5d | both |
| F7 | Heat stress planner: `/api/heat-plan/` with 12 hourly periods, deterministic `planShift`, manual entry, a bilingual PDF. The WeatherBar heat chip now opens `/heat`, which finishes `cold-heat-chip-dead-end`. Check the federal and Nevada heat rules first. | May 1 (OTA) | backend weather.py, views.py, lib/heat.ts, app/heat.tsx, WeatherBar.tsx | 5d | code |
| F8 | Forklift pre-shift check (1910.178(q)(7)) with electric and LPG variants, hour meter, truck chips, optional per-truck history | Jun 1 | fixtures, integrations.py, inspect.tsx | 2d | both |
| C2, C4 | Keep running: reviews at least 7 days before each send_at, episode drafts | weekly | | — | Jamil reviews |

---

## UX fix table (every verified finding, highest severity first)

Duplicates of the same root cause are merged and list every id. "Ship" is v1.0, OTA or U1.

| id | Screen | Sev | Issue | Fix | Eff | Ship |
|---|---|---|---|---|---|---|
| alert-detail-waits-on-network | Alert detail, Talk | H | getFeedItem and getTalk go to the network before the cache. Up to a 10 s spinner, and offline with a cold cache it wrongly says "isn't available". | Read the cache by id first, refresh in the background, return ok/offline/missing, add Retry | S | v1.0 |
| small-text-links | Today, WeatherBar | H | Text links are about 20 pt tall, the weather pill 36 pt, the chips about 30 pt | Link asChild with Pressable, minHeight 44, hitSlop 8. Pill and chips at minHeight 44. | S | v1.0 |
| field-label-not-associated, field-label-not-linked | All forms (Field) | H | The label isn't tied to the TextInput, so screen readers read only the placeholder or nothing | accessibilityLabel defaults to the label, hide the visible label, hint and error props, 15 pt label | S | v1.0 |
| keyboard-covers-form, screen-keyboard-covers-fields | Suggest, Settings, Sign-in, Tools | H | The keyboard covers the lower fields and Save. Number pads have no Done. | automaticallyAdjustKeyboardInsets and a dismiss mode, iOS Done accessory, Tools results above the inputs, check Android | S–M | v1.0 |
| download-progress-scale | OTIS | H | Progress runs 0–100, but the screen treats it as 0–1. The bar looks full and the text says "Starting" during the whole 1.3 GB download. | Clamp pct to 0–100, use it for text and width, progressbar role | S | v1.0 |
| 911-double-tap-keyboard | OTIS | H | The first tap on Call 911 only dismisses the keyboard | keyboardShouldPersistTaps "handled", Keyboard.dismiss() when urgent | S | v1.0 |
| urgent-card-english-only | OTIS | H | The 911 rail is English even for Spanish questions | Msg.lang and an URGENT[lang] table | S | v1.0 |
| zero-hour-english-only | Zero Hour, Learn | H | The huddle card, labels and LEGAL text are English only. The Episode model has no `_es` fields. | v1.0: L map for static labels. U1: `_es` fields plus spanish_status, approved only, the talk toggle. | L | v1.0/U1 |
| dark-danger-chip-contrast, urgent-dark-contrast, emergency-contrast-dark, danger-ok-small-text-contrast | WeatherBar, OTIS, Zero Hour (dark) | M | White on dark t.danger #E5585D is about 3.6:1, which fails AA | dangerFill token set to stopRed #C1272D in both themes. Don't lighten. | S | v1.0 |
| cold-heat-chip-dead-end | Today | M | The heat or cold chip opens an archive that is empty for most of the year | Link only when the theme has released talks, otherwise an advice chip or OTIS. /heat in M3. | S | v1.0 |
| nested-pressable-placard | Today | M | A Pressable wraps a Button, so the crew question is never read | Make the placard a View with one Button, or include the question in the outer label | S | v1.0 |
| no-press-feedback, episodecard-no-press-feedback | Today, feed, WeatherBar, EpisodeCard | M | No pressed state, so people tap twice and navigation pushes twice | Shared Tap with opacity 0.7 or android_ripple | S | v1.0 |
| offline-status-buried | Today, Alerts | M | The offline note is below the fold. Alerts says "No alerts yet" when offline. No pull-to-refresh. | listFeedWithStatus, top banner, refreshControl on Screen | M | v1.0 |
| weather-error-hides-bar | WeatherBar | M | Every failure is treated as "denied", so the bar disappears. No busy state, unhandled throws, memory-only cache. | Status-typed result, try/catch, busy state, last reading in kv-store with its age | M | v1.0 |
| weather-never-refreshes | WeatherBar | M | Loads only on mount, so the 6 AM reading stays all shift | useFocusEffect and AppState 'active', re-check permission | S | v1.0 |
| weather-a11y-label-incomplete | WeatherBar, Today links | M | The label drops "feels like". The NWS chip is unlabeled. "→" is read aloud. | Build the label from parts, label the NWS chip, explicit labels without the arrow | S | v1.0 |
| nws-alert-chip-no-detail | WeatherBar | M | Only alerts[0].event is shown. No headline, no timing, unsorted. | Sort by severity, tappable 44 pt chip that opens the headline, "+N more" | S | OTA |
| today-english-only | Today | M | The placard and labels are English. The language choice doesn't persist. | Shared lib/i18n, persisted lang, show `talk.es` when chosen | M | v1.0 |
| signin-english-only | Sign-in | M | Every sign-in string is English. Lang isn't passed from the talk screen. | Shared dictionary, `lang` route param, crew strings first, EN/ES toggle | M | v1.0 |
| held-on-utc-date | Sign-in, PDF | M | held_on uses the UTC date, so evening shifts file under the next day | Build held_on from local date parts. Local times in the PDF. | S | v1.0 |
| flush-race-duplicate | Sign-in outbox | M | Two flushes can POST the same row twice. Save waits on every queued row. | In-flight guard, Save sends only its row, client_id with server dedupe | M | v1.0 |
| queued-sheet-never-retried, outbox-flush-only-cold-start | Sign-in, root layout | M | Retries happen only on cold start or the next Save. The queue isn't visible. | AppState 'active' flush with .catch, "Waiting to send" via isQueued, reconnect listener in U1 | M | v1.0/U1 |
| save-no-feedback-during-gettalk | Sign-in | M | Save and Share wait up to 10 s on getTalk before showing busy. Silent returns. | setBusy first, cache-first talk loaded once, error messages, sharePdf returns false | S | v1.0 |
| talk-start-duplicate-sessions | Talk | M | A double tap or coming back creates a new session and strands signatures. Blank supervisor on the PDF. | Busy guard, findOpenSession and Continue, prefill from profile, omit empty PDF fields | M | v1.0 |
| no-undo-signature | Sign-in | M | A wrong signature can't be removed | deleteSignin, 44 pt rows with a confirmed Remove, hidden after save | S | v1.0 |
| remove-photo-no-confirm | Sign-in | M | One tap deletes the photo and the head count | Alert confirmation, less prominent Remove | S | v1.0 |
| empty-signature-silent | Sign-in | M | A blank pad does nothing. Success isn't visible. | onEmpty alert, announce, inline "Saved", refocus the name field | S | v1.0 |
| photo-full-res-base64 | Sign-in | M | A 12–48 MP base64 photo in SQLite, re-read on every focus, a heavy upload | expo-image-manipulator to a 1600 px long edge at 0.6, explicit columns, listSigninNames | M | v1.0 |
| pdf-pagination | Sign-in PDF | M | Header doesn't repeat, rows split, the photo pushes signatures to page 2, no attestation line | thead, avoid row breaks, table before the photo (max 420 px), "Conducted by" line | S | v1.0 |
| talk-start-buried | Talk | M | Start crew sign-in is at the very bottom. The reminder card interrupts and is English. | Footer prop on Screen or a top "Run the talk" card, move the reminder, translate it | M | v1.0 |
| talk-labels-english | Talk | M | Field labels, reminder and not-found are English. Lang resets each visit. | Add keys to L, persist in kv-store `talkLang`/`lang` | S | v1.0 |
| talk-pending-dead-end | Talk | M | Points to a PDF button that may not exist. Unlabeled 10 s spinner. | Conditional hint, cache-first load, offline line, labeled spinner | M | v1.0 |
| archive-spanish-search | Archive | M | Search ignores `es` fields and accents. UI is English. | Search `es` fields, NFD plus `[̀-ͯ]` stripping, shared dictionary | S | v1.0 |
| kb-empty-first-run | OTIS | M | Empty or loading KB gives a false "I don't have that" | Cache-first loadKb, kbState, "needs signal once" reply, .catch | S | v1.0 |
| no-announce-answer | OTIS | M | Answers and the 911 card arrive silently for screen readers | Spinner label, announceForAccessibility, assertive live region on urgent | S | v1.0 |
| ui-english-only | OTIS | M | The setup, error and hint copy are English | L table, app lang default, "Puede preguntar en español." | M | v1.0 |
| setup-marked-before-download | OTIS | M | Marked as set up before downloading. Raw error, no retry. | Try again button, console.warn the error, cellular check in U1 | S | v1.0 |
| leave-screen-copy-wrong | OTIS | M | Says the download continues if you leave. It actually aborts. | Honest copy, useKeepAwake in a child component | S | v1.0 |
| source-targets-small | OTIS | M | Source rows about 24 pt tall, no affordance or hint | minHeight 44 row, "Open ›", 16 pt, label and hint | S | v1.0 |
| sources-on-refusal | OTIS | M | A refusal still lists 4 sources. Uncited sources are shown. | Detect refusal in both languages, then [] or the cited sources only | S | v1.0 |
| no-stop-generation | OTIS | M | No way to stop a long answer | Send becomes Stop and calls llm.stop, keep the partial text | S | v1.0 |
| tappable-examples | OTIS | M | Example questions are plain text | Chips call ask(text), wired as `() => ask()` | S | v1.0 |
| episode-open-blocks-on-network | Zero Hour | M | The episode waits on the network before using the cache | Cache-first plus in-memory memo, background refresh | S | v1.0 |
| episode-null-dead-end | Zero Hour | M | "Isn't out yet" shown when actually offline. No retry. | `{ep, offline}`, "No signal" with Try again | S | v1.0 |
| no-captions-loud-dock | Zero Hour | M | Audio-only guidance, no captions or transcript | Copy now. Burned-in captions or WebVTT plus a transcript field in U1. | M | v1.0/U1 |
| learn-link-dark-mode-and-target | Learn | M | Near-invisible in dark mode, about 20 pt target | LinkRow with t.text and fonts.bodyBold, minHeight 48 | S | v1.0 |
| video-no-error-state | Zero Hour | M | A black square when offline or the URL is broken | Handle statusChange loading and error, Retry | S | v1.0 |
| report-911-not-tappable | Report | M | 911 is muted text with nothing to tap | Call911Button block on Today (M0-3) | S | v1.0 |
| placeholder-tabs-dead-ends | Tabs | M | Inspect and Report are placeholders, a 2.1 rejection risk | Hide with href:null for v1.0, restore in U1, add years to dates | M | v1.0 |
| field-border-contrast | All forms | M | Border about 1.5:1, fails 1.4.11 | fieldBorder token #7A8590 / #6B7884, width 1.5 | S | v1.0 |
| suggest-no-offline-queue | Suggest | M | Ideas are lost offline. The config error says "no connection". | Outbox queue in U1. Separate !isConfigured message in v1.0. | M | v1.0/U1 |
| settings-error-conflated | Settings | M | One "error" covers invalid email, config and network. Not announced. Re-POSTs. | Split the states, t.danger plus announce, reset on edit, use validEmail | S | v1.0 |
| settings-permission-stale | Settings | M | Switches ignore the real OS permission. The banner is stale on return. | getPermission() on mount and on 'active' | S | v1.0 |
| english-only-chrome, no-spanish-group | Stack titles, 404, Tools, Settings, Suggest | M | No app-level language setting | lib/i18n.ts with useLang (kv-store) and a Settings switch. expo-localization in U1. | M–L | v1.0/U1 |
| nav-theme-not-from-tokens | All stack headers | M | Stock navigation theme: mismatched header band, blue back chevron | Build the nav theme from tokens, headerTintColor and headerStyle | S | v1.0 |
| button-busy-silent | Button | M | Busy state announced as an unlabeled dimmed button | accessibilityLabel and state.busy, keep the label next to the spinner | S | v1.0 |
| focus-refetch-writes | Today | L | Refetches on every focus, up to 52 INSERTs outside a transaction, no .catch | withTransactionAsync, 5 min staleness, .catch to [] | S | OTA |
| alertcard-label-drops-context | Feed | L | The label hides jurisdiction, date and summary | Build the label from all of them, plus a hint | S | OTA |
| no-header-roles, heading-no-header-role, section-titles-not-headers | Heading, ComingSoon, Today, Sign-in, Talk, Settings, Tools, Suggest, Alert | L | No header roles for rotor or heading navigation | accessibilityRole header on Heading and ComingSoon, new SectionTitle | S | OTA |
| dynamic-type-clipping | Today | L | rowNum width 28 clips two-digit numbers | minWidth 28, band flexWrap | S | OTA |
| alert-body-markdown-raw | Alert detail | L | Literal ** and headings rendered as body text | lib/markdown.ts parser with bullets, header roles | S | OTA |
| effective-date-tense | Alert detail | L | Always "Takes effect" | "In effect since" or "Takes effect" callout (T12:00) | S | OTA |
| alert-empty-dead-ends | Alerts, Today | L | "Turn on in Settings" with no control | ComingSoon action prop, "See all alerts" button. Keep the jurisdiction copy. | S | OTA |
| signature-pad-a11y | Sign-in | L | Unlabeled WebView, ambiguous "Clear" | Label the pad, rename to "Clear signature". Attestation flag later. | M | OTA |
| status-not-announced | Sign-in | L | Save result and count change silently, no status color | `{kind, text}` in a t.ok/t.danger box, live region and announce | S | OTA |
| save-disabled-no-reason | Sign-in | L | Faded button with no reason. Re-save duplicates. Privacy note sits after Save. | Hint text, "Saved ✓ · Save again" with confirmation, move the notice up | S | OTA |
| pdf-backgrounds-dropped | Sign-in PDF | L | Print may drop the band and header fills | print-color-adjust:exact, border fallback | S | OTA |
| pdf-language | Sign-in PDF | L | Always English, no record of the language used | `lang` column, labels from the dictionary, "Language: Español" | M | U1 |
| archive-chip-target | Archive | L | 40 pt chips, button role, hidden overflow | 44 pt, radiogroup/radio, wrap or a peeking edge | S | OTA |
| archive-offline-and-search-ux | Archive | L | Drops the offline flag, misleading empty state, autocorrect on | Keep the flag, offline copy, autoCorrect off, Android clear control, count live region | S | OTA |
| per-token-rerender | OTIS | L | Re-renders and animated scroll on every token | Throttle to about 80 ms, memoized Bubble, non-animated scroll while streaming | M | OTA |
| autoscroll-hijack | OTIS | L | Scrolling up gets pulled back down. Ignores Reduce Motion. | Track atBottom, honor reduce motion | S | OTA |
| send-a11y-mismatch | OTIS | L | Label says "Send" but the button says "Ask". No disabled state. | Matching label, accessibilityState, dim New chat when busy | S | OTA |
| input-single-line | OTIS | L | Long questions scroll out of view | multiline, submitBehavior, maxHeight 120 | S | OTA |
| kav-hardcoded-offset | OTIS | L | Hard-coded offset 90, nothing on Android | Header height from expo-router (check the SDK 58 export), padding on both platforms | S | OTA |
| intro-flash | OTIS | L | Intro flashes for returning users. Unlabeled 10 s spinner. | Read OK_KEY first, background config refresh, labeled centered spinner | S | OTA |
| newchat-reloads-model | OTIS | L | New chat reloads a 0.5–1.3 GB model | Keep the hook mounted and reset messages, or explain the pause | M | U1 |
| kb-reindex-every-query | OTIS KB | L | Re-tokenizes the whole KB on every question | buildIndex once, useMemo | M | U1 |
| tokenizer-keeps-periods | OTIS KB | L | "ppe." and "gas." miss matches | Trim periods from tokens | S | OTA |
| spanish-detect-weak | OTIS | L | Unaccented Spanish is detected as English | Count function words (2 or more), app language as tiebreak | S | OTA |
| urgent-false-positives | OTIS rail | L | Training questions trigger 911. Real Spanish phrasing is missed. | Strip safe phrases (no veto), add Spanish patterns, tests | S | v1.0 |
| heading-not-shared | OTIS | L | Local h1 style, duplicated card, bare disabled state | Shared Heading and ComingSoon with a Learn button | S | OTA |
| tel-no-fallback | OTIS | L | tel:911 fails silently on devices that can't call | try/catch plus a localized alert | S | v1.0 |
| checkbox-glyph-not-interactive | Zero Hour | L | ☐ looks tappable. Two focus stops per row. | Use •, one accessible row | S | OTA |
| zero-hour-list-not-virtualized | Zero Hour list | L | .map() over full-size square thumbnails | FlatList in a flex:1 container (not Screen scroll={false}) | M | U1 |
| thumbnails-not-cached-offline | EpisodeCard | L | No offline copy of thumbnails, empty box | expo-image with disk cache, local placeholder | S | U1 |
| refetch-on-every-focus | Learn, Zero Hour | L | Duplicate fetches, unguarded JSON.parse, list spinner can hang | Memo with TTL and in-flight dedupe, try/catch, .catch | S | OTA |
| offline-empty-misleading | Zero Hour list | L | Offline with no cache says "New episodes every Thursday" | "No signal" message with Try again | S | OTA |
| spinners-unlabeled | Zero Hour, Learn | L | Unlabeled spinners, layout shift on Learn | accessibilityLabel, reserve the space | S | OTA |
| hardcoded-show-colors | EpisodeCard, Zero Hour | L | Show colors hard-coded, no separation in dark mode | Move them to theme tokens | S | OTA |
| compact-thumb-crop | EpisodeCard | L | 16:9 crop of square art | Horizontal compact layout with a square thumbnail | S | OTA |
| copy-audio-vs-watch | Zero Hour | L | "Audio dramas… Watch" contradicts itself. "EP 03" is read badly. | Fix the copy, title "Zero Hour, episode N" | S | OTA |
| pdf-buried-and-online-only | Zero Hour | L | PDF button at the bottom, needs signal, title not a header | Move it up, header role. Offline cache in U1 (expo-sharing). | M | OTA/U1 |
| switch-low-contrast-small-target | Settings, Suggest | L | On and off look alike in glare, only the switch is tappable | Whole row as a switch role, off-track color, On/Off label | S | OTA |
| suggest-contact-flag-stale | Suggest | L | may_contact true with no email | `contact && email`, hint text, trim fields | S | OTA |
| settings-modal-no-close | Settings | L | No close button in the modal | headerRight "Done" with hitSlop 12 | S | OTA |
| tools-results-a11y-nan | Tools | L | Shows "NaN", "en dash" read aloud, value and label separate | rate() returns null, grouped labels, DART > recordables note | S | OTA |
| tools-jargon-and-scaling | Tools | L | Bare acronyms, comma in placeholder, 40 pt values don't shrink | Expand TRIR/DART, placeholder 410000, adjustsFontSizeToFit | S | OTA |
| suggest-chip-target-role | Suggest | L | 40 pt chips, no group | 44 pt, radiogroup/radio checked, shared Label | S | OTA |
| suggest-guidance-in-placeholder | Suggest | L | Privacy note only in the placeholder. Theme not reset. | Field `hint` prop, setTheme('') | S | OTA |
| tab-active-state-color-only | Tabs | L | Active tab shown only by tint | .fill symbols when focused, 13 pt label | S | OTA |
| storage-parse-unsafe | Profile, Push prefs | L | Unguarded JSON.parse, no defaults merge | try/catch, `{...EMPTY, ...parsed}`, .catch | S | OTA |
| settings-copy-geography | Settings, Tools, Inspect | L | Dates without a year, "Pacific" time | Add years, local send time. Keep the jurisdictions. | S | OTA |
| splash-stuck-on-font-error | Root | L | A font error replaces the app with a developer screen | Hide the splash on loaded or error, fall back to system fonts | S | OTA |
| no-font-scale-caps | Heading, Button | L | 30 pt heading reaches about 93 pt | maxFontSizeMultiplier 1.5 on display type, 2.0 on buttons only | S | OTA |
| disabled-button-unreadable | Button, OTIS Send | L | Opacity 0.4 leaves the label at about 2:1 | Muted fill with a readable label, hint prop | S | OTA |
| screen-no-max-width-tablet | Screen (iPad) | L | Lines stretch about 1000 pt or more | maxWidth 680, centered (if iPad stays) | S | OTA |
| not-found-link-tiny-target | 404 | L | Tiny unstyled link out | Button "Go to Today" with router.replace('/'), Spanish | S | OTA |
| default-error-boundary | Root | L | Stock developer error screen | Custom bilingual boundary: "sheets are safe", Retry, Today | S | OTA |
| root-bg-yellow-and-splash-mismatch | app.json | L | Yellow flash on Android dark, navy splash doesn't match | Neutral root color, dark splash #141B22 | S | OTA |
| yellow-primary-low-edge-contrast | Button | L | Button edge 1.4:1 in light mode | Ink border in light mode. Haptics in U1. | S | OTA |
| no-reduce-motion-or-touch-token | theme.ts | L | No touch-target token, so sizes drift | `touch.min` 44 plus the Tap wrapper. Skip reduce-motion. | M | v1.0 |

---

## Only Jamil can do these

- [ ] **By Nov 12:** set the Railway cron service to `*/15 * * * *` and confirm a run in the logs.
- [ ] **This week:** start Apple Developer and Google Play **organization** enrollment under the Trainovate D-U-N-S number.
- [ ] Create the App Store Connect app and the Play app for `ai.trainovate.zeroharm`, and confirm the name "Zero Harm" is available.
- [ ] Choose the API custom domain. Set up DNS, the Railway domain and `DJANGO_ALLOWED_HOSTS`.
- [ ] Set the EAS env vars (production and preview), and the Railway vars on **web and cron**, including `ANTHROPIC_API_KEY` and `INGEST_KEY`.
- [ ] Upload the APNs .p8 key and the FCM v1 service account to OneSignal.
- [ ] Write or approve the sample talk content and the App Review notes.
- [ ] Paste the talk text for issues 1–8 and clear needs_review. Get the Spanish reviewed by **mid-Dec**.
- [ ] Get the privacy policy legally reviewed (signatures and photos sent to GHL, BIPA-type questions). Host it. Set up a support email.
- [ ] App Privacy and Play Data safety forms, age rating and IARC, export compliance.
- [ ] Store copy in EN and ES, screenshots, the 1024x500 feature graphic.
- [ ] Record the Play foreground-service (dataSync) declaration video, unless it is blocked.
- [ ] Test on devices: a 6 GB iPhone, a 4 GB Android phone, gloves, direct sun, dark mode, airplane mode.
- [ ] Check whether the Zero Hour 720p files have burned-in captions.
- [ ] Name a native Spanish reviewer for app strings, talks, KB entries and the 911 copy, and give them an admin login.
- [ ] Name a CSP or recordkeeping professional to sign off on the ladder, harness and forklift checklists and the 1904 tree.
- [ ] Confirm the Anthropic org's data retention (ZDR vs 30-day) and CMEK use, and set the AI monthly budget.
- [ ] Approve the list of Nevada and Las Vegas source domains for reg-watch.
- [ ] Create GHL workflows for the `zero-harm-tagout`, `zero-harm-near-miss` and `zero-harm-inspection` tags.
- [ ] Make the decisions listed under open questions below.

## Risks

- **Review has nothing to test** before Jan 3, and placeholder tabs could cause rejection. M0-2 and M0-3 address both.
- **Silent production failure:** an empty `EXPO_PUBLIC_API_URL` in EAS builds turns off push, sheets, weather and the feed with no visible error (M0-4).
- **Cron may be Sunday-only right now:** Thursday pushes, the episode sync and sheet retries may already not be running.
- **Account verification plus the late-December App Store slowdown** could push v1.0 past Jan 3.
- **Not enough code time:** M0 plus the v1.0 slice is about 24 code days in about 3 weeks, and U1 is about 40 days in about 35 working days. The cut lines are defined above. Over-scoping first goes to OTA.
- **Spoofable rate limits** on unauthenticated endpoints that create GHL contacts (M0-7).
- **Duplicate sheets and GHL notes** until M0-8 and the in-flight guard ship.
- **OTIS memory pressure** on 6 GB iPhones and 4 GB Android phones, and a 1.3 GB download over cellular.
- **Play foreground-service and permission review** holds.
- **Crew PII:** photos and signatures are sent to GHL. Near-miss reports later add injury details.
- **Content is on the critical path:** 0 of 52 talks have body_md, and Spanish approval is still pending.
- **Regulatory liability:** the recordable tree and checklists need professional sign-off. Heat rules may change before spring.
- **Admin/API path bugs:** the ingest upsert can unpublish a live alert (C5 guard). KbEntry is published by default (C3a). Late approval of a needs_details episode can send its push late or not at all.
- **OTA policy:** new features still go through store review. OTA is only for fixes and admin-driven content and UI tweaks.
- **Template drift:** the checklist cache and the bundled JSON can diverge from the admin. The template snapshot in each inspection protects old records.

## Open questions

1. Is the Railway cron set to `*/15` or the README's Sunday schedule right now?
2. Keep iPad in v1? If yes: iPad screenshots plus `screen-no-max-width-tablet`. If no: set `supportsTablet: false`.
3. Hide Inspect and Report for v1, or ship a minimal near-miss report in time for review? This plan hides them.
4. Who receives near-miss reports: a supervisor email entered once, the profile email, a company code routed in GHL, or a shared PDF only? How long is the unredacted original kept?
5. Should inspections and near-miss reports go to GHL by default, or only on "Save to my records" like sheets do?
6. Where are the privacy and support pages hosted (Trainovate site or a Django `/privacy/` page), and who reviews them legally?
7. How do supervisors get saved sheets back later? The app promises they can download them.
8. Crash reporting: store consoles only, or Sentry (an extra Diagnostics disclosure)?
9. Should a "block" accuracy review hold a talk out of `released()`, or only warn in the admin?
10. Translate talks as soon as the GHL year sync runs, or only after the English is reviewed?
11. Is there a script or transcript for each Zero Hour episode besides the card PDF?
12. Heat-day pushes would need region tags, which conflicts with the "nothing stored" weather promise. Do you want them?
13. Is the on-screen DANGER placard plus the PDF enough, or do you want a printable QR tag-out label?
14. Should the first-run default language be English, or should the app ask the user on first launch? (expo-localization auto-detect arrives in U1.)

---

# Section A: OTIS local AI and knowledge base plan

Line numbers are from the uncommitted working tree as of 2026-11-10, and several files are still changing: `app/otis.tsx`, `lib/push.ts`, `backend/talks/console.py`, `lib/live.ts`. Check citations again after the next commit. Owners: **code** (implementation), **Jamil**, **CSP** (the credentialed safety reviewer), **bilingual reviewer**, **counsel**.

## A1. Current state

**Runtime**
- OTIS runs Qwen3 on the device through react-native-executorch 0.10.7.
  - Model choice: QWEN3_1_7B when `Device.totalMemory` is at least 6 GiB, otherwise QWEN3_0_6B (`app/otis.tsx:32-35`). The cutoff is hard-coded at `backend/talks/views.py:278`.
  - It always loads `.DEFAULT` with temperature 0.2 and maxNewTokens 320 (`app/otis.tsx:101-104`).
- `DEFAULT` depends on the platform. `rne-build-config.json` turns MLX on and Core ML off, and Qwen3 has no Core ML or Vulkan export (`node_modules/react-native-executorch/src/models.ts:88-91, 119-157, 2652-2656`).
  - Physical iPhones get MLX_INT4.
  - Android and the iOS simulator get XNNPACK_8DA4W.
- The hard-coded size labels "1.3 GB" and "510 MB" (`app/otis.tsx:23`) have never been checked against the real files.
- **Bug, setup progress:** the hook reports 0-100 (`useResourceDownload.ts:62,68`), but the screen treats it as 0-1 (`app/otis.tsx:176-178`). The label changes to "Starting OTIS…" at 1%, and the bar looks full.
- **Bug, saved model:** the model key is saved when the setup button is tapped, before any download (`app/otis.tsx:87`). It is never re-checked against the server.
- **Bug, chat history:** every turn's SOURCES block stays in the KV cache (`llmChatSession.ts:244-262`). The only limit is a hint after 6 turns (`app/otis.tsx:215-217`). When the cache fills, the user sees the generic "could not answer" error (`app/otis.tsx:146-147`). New chat remounts the session and reloads the whole model (`app/otis.tsx:96`).
- **Telemetry:** `setTelemetryEnabled(false)` (`app/otis.tsx:17`) does not stop the Hugging Face download-counter HEAD request (`src/fetcher/telemetry.ts:50-62`; `fetcher.ts:266`). That request carries no question text, but it contradicts the comment at `:17`.
  - Confirmed: question text is never sent over the network (`app/otis.tsx:126-144`).

**Retrieval**
- BM25 over every passage, re-tokenized on every query (`lib/otis/kb.ts:43-68`).
- **Bug, tokenizer:** it splits on `[^a-z0-9.]` (`kb.ts:39`), so "lock." keeps its period. The prefix rule only applies to words over 4 letters (`kb.ts:55`), so short words at the end of a sentence (lock., heat., fire.) never match.
- **Bug, standard numbers:** the same prefix rule turns "1910.147" into "1910.14", which also matches 1910.146 and 1910.141.
- Fixed settings: cutoff 0.5 (`kb.ts:64`), k=4.
- Spanish questions search Spanish and English passages by keyword only (`kb.ts:46`).

**KB loading**
- The app fetches the full KB on every chat mount and ignores the response's `version` field (`kb.ts:12-27`; `app/otis.tsx:113-115`).
- With no cache and no signal, the KB is empty and every question gets the NOT_COVERED reply.
- A refresh path already exists: `console.content_version()` (`backend/talks/console.py:204`), served at `/api/content-version/` (`urls.py:20`) and polled by `lib/live.ts` (60 s throttle, `live.ts:16`). It is wired into OTIS at `app/otis.tsx:116`.

**Backend `otis_kb`** (`views.py:256-268`)
- KbEntry rows are always labelled `"lang": "en"` (`views.py:259`).
- Talk sections have no size limit (`views.py:234-253`). A crew-question passage is always emitted (`views.py:249`), so a talk with an empty body is represented only by its question.
- Episode passages (`views.py:343-352`) have no tags, and they leave out `Episode.references`, so standard citations never reach the model.
- The `version` field (`views.py:267`) is unused.

**KbEntry model** (`models.py:196-212`)
- Fields: title, body, source, tags (CharField 200), published (default True, `:203`).
- There is no language, citation, reviewer or status field.

**Two write paths with no review step**
- Django admin (`admin.py:133-137`).
- The new console API (`console.py:466` KB_CHECKS including `published`; POST at `:481`, PATCH at `:493`). It is protected by one shared `CONSOLE_KEY`.

**KB content today (from the fixtures; production not checked)**
- 8 seeded entries, all English, none citing a CFR paragraph (`0005_seed_otis_kb.py:4-39`): 1 emergency, 1 stop/ask, 6 app or product.
- 3 released Zero Hour episodes, giving 15 passages: EP1 LOTO, EP2 Trench, EP3 Confined Space. EP4 Fall Protection releases 2026-11-12 (`fixtures/zero_hour.json`; `tests.py:264`).
- 52 talks for 2027, all unreleased until 2027-01-03, none with `body_md` (`fixtures/talks_2027.json`).
- Production may differ, because `ghl_sync.sync_year` writes `body_md` (`ghl_sync.py:66`) and the console can create KB rows. **Check the console overview counts first** (`console.py:245`).

**Prompt and 911 rail**
- The prompt passes only each source's title and text to the model (`prompt.ts:18`). `source` is never shown to the model.
- The 911 rail is regex only (`lib/otis/safety.ts:5-15`) and runs only inside `ask()` (`app/otis.tsx:131`). The input box is disabled while OTIS loads (`:225`).
- Even when the rail fires, retrieval and the model still run.
- The banner text is a fixed string (`app/otis.tsx:189-193`).
- Probe of the rail: it missed 12 phrasings, including "someone is hurt", "no puede respirar", "chemical splash in his eyes", "arc flash just happened" and "forklift tipped over and he's under it".
- It fires on normal Fire Prevention questions such as "fire extinguisher inspection", "fire prevention plan" and "smoke break" (`safety.ts:9`).

**Tests and CI**
- There is no JS test runner and no `.github/` directory. The repo is on GitHub.
- `kb.ts` cannot be imported in plain Node because of its imports at `kb.ts:1-3`.
- The project uses npm (`package-lock.json`).

## A2. Target architecture

```text
 AUTHORING (Railway / Django)                          PHONE (Expo SDK 58, all on-device)
 ───────────────────────────                           ──────────────────────────────────
 eCFR versioner API ──► KbDraftJob (cron queue)         ┌──────────────────────────────┐
   (gzip, server-side)   claude.py (anthropic SDK)      │ 911 rail (regex, EN/ES)      │◄─ runs first, always,
                         structured JSON drafts         │  pinned banner, works before │   even before setup
                              │                         │  model/KB exist              │
                              ▼                         └──────────────┬───────────────┘
 quote verifier (verbatim vs eCFR) ──► KbEntry          question ──────┤
                                       status=draft                    ▼
 Admin + Console (same gate) ──► lint ──► CSP approve   ┌──────────────────────────────┐
   EN approve ──► bilingual approve (ES twin)           │ Retrieval: BM25 (fixed tok.) │
                              │                         │ + optional multilingual      │
                              ▼                         │ embeddings (RRF + MMR)       │
 otis_kb: approved, effective, lang-true,              └──────────────┬───────────────┘
   chunked 80-180 words, stable ids, citation line                    │ top-k passages
 content_version() (console.py:204) ◄── same filter                   ▼
         │                                               model ready? ──no──► Extractive answer
         │  poll on foreground (lib/live.ts)                  │yes            (verbatim + [n])
         ▼                                                    ▼
 GET /api/otis/kb/ ──► kv-store cache ──► fallback:     OtisSession (bounded context,
                        bundled seed (assets/otis/        SYSTEM prefilled once,
                        kb-seed.json, export date)        last Q&A + new sources)
                                                              │
 Model manifest (/api/otis/config/) ──► tier by RAM          ▼
   self-hosted CDN .pte + tokenizer, pinned URLs        Verifier: citations valid, refusal
   Wi-Fi gate, size check, cleanup                        detected, grounding overlap,
                                                          banned-advice ──fail──► Extractive

 EVAL (off-device, never user data): questions.vN.jsonl ─► rank.ts recall@4 + rail grader (CI)
   ─► Mac Qwen3 runner (same .pte) ─► Claude judge (calibrated) ─► report + release gates
   ─► dev-build device sampler (local JSONL, shared manually)
```

## A3. Milestones

These come from three plans merged into one, with every verifier correction applied. The order follows the critical path: the publish gate and review workflow must exist before Wave 0 content (due 2026-12-18), and the retrieval fixes must land before the standards-heavy waves.

| ID | What | Why | Key files | Effort | Owner |
|---|---|---|---|---|---|
| **O1** | **Quick fixes.** Fix progress units (0-100) at `otis.tsx:176-178`. Replace the size labels at `:23` with the real file sizes (HEAD request now, manifest later). Save the model key only after a successful load, not at `:87`. Change the existing catch message at `:146-147` to show the extractive answer (it already catches errors). Fix the telemetry comment at `:17`. Remove the duplicate `expo-build-properties` at `app.json:86`. | Every user sees wrong setup progress. A changed model never reaches a phone that already saved one. | `app/otis.tsx`, `app.json` | 0.5 d | code |
| **O2** | **Harden the 911 rail** (outside the model). Add a reviewed EN/ES phrase list: choking, allerg/anaphyl, hurt, injured, herido, lastimado, "no puede respirar", quem/burn, cut off, splash, leak, arc flash, tipped over, golpe de calor, aplastad. Overdose is already there (`safety.ts:10`). Match without accents. Also check the model's output. Show the banner before setup and while downloading or after a failure. When the rail fires, decide whether to skip retrieval. Build a test table of at least 100 phrasings. Track false positives (fire, smoke) but do not remove patterns without CSP sign-off. | The regex is the only part that cannot be talked out of the rule, and it misses common phrasings. | `lib/otis/safety.ts`, `app/otis.tsx`, `eval/otis/rail.test.mts` | 2 d | code + CSP |
| **O3** | **Test foundation.** Move `STOP`/`words`/`search` (`kb.ts:29-68`) into a pure `lib/otis/rank.ts`, with `kb.ts` re-exporting it. Use `node:test` with `.mts` files. Add `allowImportingTsExtensions` to `tsconfig.json`; tsc 6.0.3 throws TS5097 without it. Add `@types/node` explicitly (`npx expo install @types/node -- --save-dev`). Do not add `"type":"module"`. Add `.github/workflows/otis-eval.yml` to run the Node tests, `python manage.py test talks`, `npx expo lint` and `npx tsc --noEmit`. If component tests are wanted, use `npx expo install jest-expo jest @types/jest --dev` (SDK 58 needs Jest 30). | Retrieval and rail regressions should fail CI. | `lib/otis/rank.ts`, `lib/otis/kb.ts`, `tsconfig.json`, `package.json`, `.github/workflows/` | 1 d | code |
| **O4** | **KbEntry schema and publish gate** (migration 0008; latest is 0007).<br>• New fields: `lang`, `translation_of` (FK to self), `citation`, `standard` (indexed), `hazard`, `audience`, `jurisdiction` (reuse `FeedItem.JURISDICTIONS`, `models.py:99`), `theme_month`, `source_url`, `status`, `author` and `approved_by` (FKs to User), `reviewed_on`, `effective_date`, `next_review`, `slug`, plus provenance fields (`source_quotes`, `quotes_verified`, `ecfr_amendment_date`, `drafted_by_model`). `tags` becomes a TextField.<br>• `status` values: draft, in_review, approved, retired, and `legacy_unreviewed` for the 8 seed rows.<br>• `otis_kb` serves only approved rows, plus legacy rows until O5 sign-off. It emits the real `lang` and appends "Rule: …" to the text.<br>• Core and emergency entries are exempt from `next_review` expiry.<br>• Apply the same filter in `content_version()` (`console.py:204`) and the overview count (`:245`).<br>• Gate the console: POST and PATCH (`console.py:481-500`) cannot set approved or published, and `KB_CHECKS` (`:466`) widens tags beyond `text(200)`.<br>• In search, drop an English twin when its Spanish twin is present (twins otherwise fill 2 of the 4 slots, `kb.ts:46,60`).<br>• Tests. | Drafts must never go live: `published` defaults to True (`models.py:203`) and the console can publish directly. Spanish KB entries have nowhere to go today. | `backend/talks/models.py`, `views.py`, `console.py`, `migrations/0008_*`, `tests.py`, `lib/otis/rank.ts` | 2.5 d | code |
| **O5** | **Review workflow and linter**, enforced the same way in admin and console.<br>• Actions: Submit, Approve (needs the `approve_kbentry` permission, author ≠ approver, `quotes_verified` for drafted rows), Retire.<br>• Any content edit resets the entry to draft.<br>• For new theme-month entries only, English is held until Spanish is approved. This does not apply to the live 911 entry.<br>• "Due for review" filter, with reminders through GHL or OneSignal (`integrations.py`). There is no EMAIL config in settings.<br>• "Draft Spanish" needs a generalized translate function, because `draft_spanish` only handles talks (`translate.py:18,38-43`).<br>• `kb_lint.py` blocks: "know where it goes" wording; gloves near rotating parts unless the text says to take them off; substitute PPE; outcome percentages; promises about reporting; certification claims; missing "Stop the job and tell your supervisor." on imminent-danger hazards; numbers not backed by a citation.<br>• CSP signs off the 8 seed rows (after fixing the stop-work wording at `0005:14-17` and the offline claim at `0005:11`). | A safety assistant that answers only from the KB needs a named approver and an audit trail. | `backend/talks/admin.py`, `console.py`, `kb_lint.py`, `translate.py`, `tests.py` | 4 d | code + CSP |
| **O6** | **Retrieval fixes before the KB grows.**<br>• Tokenizer: keep a period only between digits (`kb.ts:39`).<br>• No prefix matching on tokens that contain digits (`kb.ts:55`).<br>• Light EN/ES stemmer.<br>• Build the index once per KB version (`kb.ts:47-50`).<br>• Emit the crew-question passage only when the talk has body sections, or retitle it "Crew discussion question (not an answer)" (`views.py:249`).<br>• Add episode tags and `references` (`views.py:343-352`).<br>• Chunks of 80-180 words with a context prefix.<br>• Chunk ids from heading slugs; today's ids are position-based and shift when sections change (`views.py:249-252`). | Sentence-final words and neighbouring standards (1910.146 vs .147) are retrieved wrongly. Ship this before the standards-heavy waves. | `lib/otis/rank.ts`, `backend/talks/views.py`, `models.py` | 1.5 d | code |
| **O7** | **KB sync, bundled seed and extractive mode.**<br>• Reuse `content_version`/`lib/live.ts` and compare versions in JSON. Whether RN fetch passes a 304 through on iOS is untested.<br>• Stop refetching on every mount (`otis.tsx:113-115`).<br>• Fallback order: server, then cache, then bundled seed. Never return `[]`.<br>• `manage.py export_otis_kb` writes released content only to `assets/otis/kb-seed.json`, with an export date. The server version overrides the seed.<br>• Extractive mode shows the top 1-2 passages word for word, labelled "From the Zero Harm knowledge base", with [n] chips.<br>• New intro copy and "Knowledge base updated <date>".<br>• Test in airplane mode: fresh install offline, and fresh install with signal then offline. | "Works with no signal" is false on a first launch with no signal today. | `lib/otis/kb.ts`, `lib/otis/extractive.ts`, `app/otis.tsx`, `backend/talks/management/commands/export_otis_kb.py`, `eas.json` | 3 d | code |
| **O8** | **Answer verification.**<br>• Parse [n] citations. Reject answers with none or with an out-of-range number.<br>• Detect NOT_COVERED with a loose, normalized match. It may come after "Call 911 now." (`prompt.ts:8`).<br>• Show only the sources the answer cites, renumbered.<br>• Grounding overlap check; the bar starts as a guess (about 60%) and is tuned in O10.<br>• Banned-advice check (bypass phrases next to LOTO, guard, permit or PPE words), approved by CSP.<br>• On failure, show the extractive answer.<br>• Lower maxNewTokens to about 200. No stopRegex: im_end is already a stop token (`llmChatSession.ts:153,199`), and a "last citation" regex would fire on the first [n]. | Uncited or invented answers currently show all 4 source chips (`otis.tsx:139-143, 200-209`). | `lib/otis/verify.ts`, `prompt.ts`, `app/otis.tsx` | 2 d | code + CSP |
| **O9** | **Eval set and deterministic graders.**<br>• `eval/otis/questions.v1.jsonl`, about 300 items: in-KB 120 (EN 70 / ES 50), out-of-KB 40, urgent 40, unsafe bait 40, short phrasing 30, app help and follow-ups 30. A further 20% goes in `holdout.v1.jsonl`.<br>• Each item has expected source ids, `expect_911` and `expect_refusal`.<br>• Plus 3-5 golden questions per KB entry.<br>• Retrieval run against `kb.snapshot.json` (recall@4, MRR, empty-result rate), split by language and category. A missing id fails the run loudly.<br>• Rail grader (recall and false positives).<br>• Humans write the labels. Claude may only suggest paraphrases. | Model, prompt, threshold and KB changes need evidence. | `eval/otis/*`, `lib/otis/rank.ts` | 4 d | both |
| **O10** | **Generation eval, device bench and release gates.**<br>• **Spike first:** loading the app's `.pte` files with ExecuTorch Python on macOS arm64 is unverified. Fallback is mlx-lm or a Qwen3 GGUF at Q8_0.<br>• Copy the app exactly: SYSTEM and userTurn from `prompt.ts`, /no_think, temperature 0.2, k=4, full history with no truncation, 3 samples per item.<br>• Claude judge (`claude-opus-5-5`, structured output, explicit effort). Calibrate on about 60 CSP-labelled answers; refusals and max_tokens count as ungraded.<br>• Dev-only route under `app/`, not `src/app`. It needs a `__DEV__`/env guard because route files ship in production bundles. It runs the bundled set and exports JSONL via expo-sharing, with no upload.<br>• Keep the `sendMessage` stats that `otis.tsx:141` throws away: TTFT, tokens/s, prefill, KV `usageRatio`.<br>• Device matrix: iPhones under and over 6 GB, a 4 GB budget Android, a mid-range Android, a flagship. | Small quantized models must clear the bars on the phones workers actually carry. | `eval/otis/run_qwen.py`, `judge.py`, `rubric.md`, `report.ts`, `app/(dev)/otis-eval.tsx` | 6.5 d | both |
| **O11** | **Session redesign.**<br>• An `OtisSession` built on `createLLMRunner` and `createChatPreprocessor`: prefill SYSTEM once, then `reset(pos0)` and a compact turn (last Q&A pair with no sources, about 80 tokens, plus new sources and the question).<br>• Run `runner.generate` through `wrapAsync`, because it is synchronous (`llmRunner.ts:137-141`).<br>• Alternative: `resetOnTurn: true` with history trimmed inside the session. Do not remount: that reloads the whole model (`useModel.ts:32,66`).<br>• Read `maxSeqLen` from `getKVCacheState()`. Fit sources to the budget, at most 3 on 0.6B.<br>• Follow-up keyword carry-over for retrieval only.<br>• `llm.stop()` on blur or background.<br>• Stop New chat reloading the model. | Context fills after a few turns, and New chat reloads about 1 GB. | `lib/otis/session.ts`, `app/otis.tsx` | 3 d | code |
| **O12** | **Spanish handling.**<br>• A scored language detector, replacing the regex at `prompt.ts:26-27`.<br>• An OTIS EN/ES toggle; `lib/profile.ts:4` has no language field and is the supervisor's profile.<br>• "Fuente en inglés" note when the sources are English.<br>• Never machine-translate safety text in extractive mode.<br>• Translate all OTIS UI strings.<br>• Compare against LLAMA3_2_1B/3B in O10. | Spanish questions mostly get the NOT_COVERED reply. | `lib/otis/lang.ts`, `prompt.ts`, `app/otis.tsx` | 2 d | both |
| **O13** | **On-device embeddings and hybrid retrieval** (needs a native rebuild).<br>• List `backends` explicitly in `package.json` instead of the `textEmbeddings` feature, which links Core ML (`download-libs.js:148`).<br>• Pin `PARAPHRASE_MULTILINGUAL_MINILM_L12_V2.XNNPACK_8DA4W`.<br>• Embed changed hashes only while the LLM is idle, or on a separate worklet runtime, because both share `defaultWorkletRuntime` (`core/runtime.ts:25,54-56`).<br>• Store vectors as SQLite BLOBs. Combine with RRF (k=60) plus MMR. Tune the floors in O9/O10.<br>• Build only if O9 shows paraphrase or cross-language gaps. | BM25 misses paraphrases and Spanish-to-English matches. The registry has no reranker. | `lib/otis/embed.ts`, `rank.ts`, `package.json` | 3.5 d | code |
| **O14** | **Model manifest, tiering, self-hosting and download UX.**<br>• `/api/otis/config/` returns tiers with explicit variants and URLs, bytes and sha256. Proposed tiers, tuned by O10: under 3.5 GiB extractive only; 3.5-5.4 GiB 0.6B; 5.4 GiB and up 1.7B; optional larger model at 7.5 GiB and up.<br>• Drop one tier after a crash.<br>• Self-host files on a CDN at fixed versioned paths. This also stops the HF counter, which only fires for huggingface.co (`telemetry.ts:38-40,54`).<br>• Check sizes; `react-native-blob-util` `fs.hash` sha256 on a 1 GB file is untested.<br>• Delete only files no manifest model still references; all Qwen3 sizes share one tokenizer (`models.ts:1798-1839`).<br>• `npx expo install expo-network` for a Wi-Fi gate, with "Download now on cellular" as the second option.<br>• **Register** the background-downloader config plugin in `app.json` (required). Whether `setConfig({allowsCellularAccess})` applies to RNE tasks is untested.<br>• Check free space with `Paths.availableDiskSpace` (at least 2× the model).<br>• `preventLoad` until the user agrees; pause and cancel buttons. | Upgrading the library or switching variants triggers a silent download of more than 1 GB. The cutoff is guessed. Downloads can run on cellular. | `lib/otis/models.ts`, `lib/otis/download.ts`, `app/otis.tsx`, `app.json`, `backend/talks/views.py`, `settings.py` | 6.5 d | both |
| **O15** | **Claude-assisted drafting pipeline** (after O4 and O5).<br>• Pin `anthropic` in `requirements.txt` to an exact release (look it up on PyPI). Add `backend/talks/claude.py`: one client, typed errors, `stop_reason` handling (refusal, max_tokens, pause_turn), and record `response.model`.<br>• Queued `KbDraftJob` run by cron (`cron.py:26-34`).<br>• **No web_fetch:** the eCFR page sends non-browser clients to `unblock.federalregister.gov`. Instead, fetch `/api/versioner/v1/full/{date}/title-29.xml?part=1910&section=…` server-side with `Accept-Encoding: gzip`, using `titles.json` `up_to_date_as_of` as the date, and pass the text in the user turn.<br>• Structured JSON (no minLength/maximum). Drafts land as status=draft.<br>• `ecfr.py` checks every quote word for word. A weekly amendment check (`versions/title-29.json?section=`) flips changed entries back to in_review.<br>• Move `translate.py` and `console.talk_spanish_draft` (`console.py:324`) onto the queue. Synchronous Claude calls risk gunicorn's 30 s default timeout (`Dockerfile:25` sets none; check Railway `GUNICORN_CMD_ARGS`). | It speeds up drafting and keeps provenance that code can verify. A human still approves everything. | `backend/talks/claude.py`, `kb_author.py`, `ecfr.py`, `management/commands/draft_kb.py`, `cron.py`, `admin.py` | 4.5 d | code |

Total engineering is about 46.5 days, not counting content.

**Suggested order:** O1 → O2 → O3 → O4 → O5 (minimum needed for Wave 0) → O6 → O7 → O8 → O9 → O15 → O10 → O11 → O12 → O14 → O13 (only if O9/O10 show the need).

## A4. KB content calendar

First send per theme comes from `talks_2027.json`. Each approval date is the Friday 16 days before that send. Heat is moved earlier: the two-week Friday would be 05-21, but the deadline is 04-30 for Las Vegas. Counts are English entries, each with a Spanish twin approved by the bilingual reviewer. Every CFR paragraph needs CSP sign-off.

| Wave | Theme (talks) | First send | Approve by | EN entries |
|---|---|---|---|---|
| W0 | Core, emergency and stop-work 8 · app help 10 (privacy entry may say questions never leave the phone, but must **not** claim no analytics, because of the HF HEAD request during download) · first aid/eyewash 5 · LOTO 12 · confined space 6 · fall basics 4 · general-industry note for trench/roofing 2 | Jan Hazardous Energy (4) 2027-01-03 | Core, emergency, confined space by 2026-12-04; **everything by 2026-12-18** | **47** |
| W1 | Chemicals (4): HazCom 10. Recordkeeping (1904, supervisor audience) 6 | 01-31 | 2027-01-15 | 16 |
| W2 | Machine Guarding (5) | 02-28 | 02-12 | 10 |
| W3 | Respiratory & Eye (4): respiratory 8 + PPE/hearing 10 | 04-04 | 03-19 | 18 |
| W4 | Falls (5): walking-working surfaces 10 + 2 fall protection | 05-02 | 04-16 | 12 |
| W5 | Heat (4) 10, plus Nevada/Las Vegas 6 | 06-06 | 04-30 | 16 |
| W6 | Forklifts (4) | 07-04 | 06-18 | 12 |
| W7 | Electrical (5) | 08-01 | 07-16 | 10 |
| W8 | Emergency Action (4) | 09-05 | 08-20 | 8 |
| W9 | Fire Prevention (4) | 10-03 | 09-17 | 8 |
| W10 | Lifting & Driving (5), labelled Good practice | 10-31 | 10-15 | 8 |
| W11 | Winter Safety (4) | 12-05 | 11-19 | 6 |

The total is about 171 English entries (169 by category plus 2 construction-redirect notes), and about 342 with Spanish. Planned effort is 6 + 24 + 2 days. **The verifier judged this too low** for drafting, two reviews and Spanish.

**Content claims to confirm**
- **Confirm with CSP:**
  - 1910.147(e)(3), (d)(5), (f)(3), (f)(4)
  - 1910.28(b)(1)(i)
  - 1910.178(l)(6), (q)(7), (n)(7), (m)(5)
  - 1910.134(e), (f), App. B-1, App. D
  - 1910.151(b), (c); eyewash "15 minutes" is ANSI Z358.1, so label it Good practice
  - 1910.215(a)(4) 1/8 in. and (b)(9) 1/4 in.
  - 1910.140(c)(18), (c)(21)
  - 1910.303(g)(1) and GFCI scope
  - 1910.157(g), 1910.38(a)
  - 1904.32(b)(6), 1904.39 (8 h / 24 h)
  - CO PEL 50 ppm (Table Z-1)
- **Confirm with counsel or CSP:**
  - Status of the federal heat standard
  - Nevada heat-illness rule
  - Nevada OSHA State Plan scope
  - NRS 618.383 thresholds
  - Nevada complaint contacts and retaliation deadlines

## A5. Authoring and human review workflow

1. **Draft.** A KbDraftJob (O15) for one eCFR section, or a hand-written entry in admin or console. Status is draft. Spanish starts as a draft.
2. **Automated checks.** The quote verifier (O15) and the `kb_lint` guardrails (O5). A blocking error stops approval.
3. **CSP review** against a checklist:
   - The requirement is stated without being weakened.
   - "OSHA rule" vs "Good practice" label is correct.
   - The entry ends with "Follow your site's written procedure."
   - Imminent-danger entries end with "Stop the job and tell your supervisor."
   - No certification, outcome-figure or reporting-promise language.
4. **Approve English.** The approver must not be the author (FKs to User). This sets `reviewed_on` and `next_review`: +12 months, or +6 months for Nevada or heat.
5. **Spanish.** "Draft Spanish", then the bilingual reviewer checks how strong the obligation reads ("debe" vs "puede"), not just fluency. Approve. For new theme-month entries, English publishes only after Spanish.
6. **Eval gate.** Run O9 retrieval on each wave. Run O10 on the device for 0.6B and 1.7B before publishing a wave.
7. **Publish.** `otis_kb` and `content_version` pick it up, and phones refresh on foreground.
8. **Maintain.** Weekly due-for-review reminders through GHL or OneSignal. eCFR amendment detection flips entries back to in_review. Any edit resets to draft.

**Spanish stop-work wording.** "Pare el trabajo y avísele a su supervisor" is a proposal. Confirm with the bilingual reviewer; the existing register is usted (`otis.tsx:28`, `translate.py:7`).

## A6. Eval harness and pass bars

All bars are proposed. Confirm with Jamil and CSP.

| Gate | Bar | Runs |
|---|---|---|
| 911 rail recall on the labelled urgent set | 100%, and no regression on any previously passing item | Every PR (deterministic) |
| Rail false positives | Reported as a warning only | Every PR |
| Retrieval recall@4 (golden questions) | At least 90%. Fail if it drops more than 2 points overall or more than 5 points in any language slice, measured against the baseline. Report-only until a baseline exists. | Every PR |
| Critical failures (gave permission to skip a step; missed "Call 911" first line on an urgent item) | 0 | lib/otis changes, release, and weekly after approvals |
| Faithfulness | 1.7B at least 90%; 0.6B at least 85% | Same |
| Correct NOT_COVERED on out-of-KB questions | At least 95% | Same |
| Judge calibration against CSP labels | Outcome at least 90%; faithful at least 85% | Whenever the rubric changes |
| Device vs Mac agreement | Outcome at least 90%; faithfulness within 5 points, otherwise Mac numbers are advisory for that platform | Each release candidate (60-item subset) |
| Performance at the chosen tier | TTFT under 2.5 s; at least 8 tok/s; no OOM in 20 runs | O10 device bench |

**Cost estimates** (measure on the first runs):
- Drafting with `claude-fable-5-2` at $8/$40 per MTok: about $0.6-1.5 per section before thinking overhead.
- Judging with `claude-opus-5-5` at $4/$20: about $22-28 per 600 answers at standard rates, about $11-14 with Batch (but server-side fallbacks are rejected on Batch), and about $65-83 with 3 samples per item.
- Fable 5.2 needs 30-day retention (not ZDR), and structured outputs need no CMEK. Confirm with the Anthropic org admin.

## A7. Risks

- **The Wave 0 schedule is tight.** 47 English plus 47 Spanish entries by 2026-12-18 (about 5.5 weeks, over the holidays). No CSP or bilingual reviewer is named in the repo.
- **Small models drift from the sources.** They can drop "not", merge passages, echo a crew question, or answer poorly in Spanish. The rail and the O8 checks must sit outside the model.
- **Drafts can leak today.** Until O4 ships, `published` defaults to True and the console can publish directly.
- **Bundled seed.** It can leak unreleased content if the export is not limited to released items. It also freezes content: an entry later unpublished as wrong would still be served offline until the server version overrides it.
- **Privacy promise.** The HF counter HEAD request fires during model download until O14 self-hosts. Any eval or performance data must be shared manually and never auto-uploaded.
- **Unexpected re-downloads.** The cache is keyed by URL (`fetcher.ts:58-62`), so a new URL means a download of more than 1 GB. Old files are never deleted.
- **Native rebuilds.** Embeddings, expo-network, the downloader plugin and the entitlement need new EAS builds and store releases, not OTA updates.
- **Memory.** Running the LLM and the embedder together on 4 GB phones may get the app killed. The package has no memory-pressure or thermal handling.
- **Experimental APIs.** `llmRunner` and the KV APIs are marked `@experimental` (`llmRunner.ts:10-14`), so a custom session may break on an upgrade.
- **Citation drift.** Expiry hides stale entries, which can leave gaps. Core entries are exempt.
- **Construction content.** EP2 and EP4 are construction topics. Without 1910 companion entries, OTIS may give 6 ft thresholds to warehouse workers.
- **Slang.** BM25 depends on tags, so the tag discipline is load-bearing until O13.

## A8. Open questions

1. Who is the CSP who signs `approved_by`, and who is the bilingual reviewer? What turnaround can they commit to for 2026-12-18?
2. What does production actually hold today (talk bodies, KB rows)? Check the console overview.
3. Will the 2027 talk bodies arrive through GHL sync before 2027-01-03?
4. Spanish as separate rows linked by `translation_of`, or `body_es` on one row?
5. Is Spanish parity a hard gate for every new entry, or only for theme-month and imminent-danger entries?
6. Where to host the models (R2/S3 plus a CDN), and who pays for bandwidth? Is redistribution of Qwen3 and the Software Mansion exports allowed? Confirm with counsel.
7. Extractive-only OTIS under about 3.5 GiB, or still offer 0.6B? Allow an optional larger model on 8 GB phones?
8. Keep follow-up memory (last exchange), or treat each question on its own?
9. Should the rail skip retrieval and the model when it fires? Accept the false positives in fire, heat and emergency months?
10. Is the extra embedder download acceptable, or only when Spanish is detected?
11. Is the iOS increased-memory-limit entitlement available through `app.json` in SDK 58? Confirm with the Expo docs and Apple. What does `Device.totalMemory` report on real 6 GB and 8 GB phones? Measure it.
12. Should supervisor-audience entries (1904, Nevada thresholds) be shown to everyone? The app has no role field.
13. Does Nevada or Las Vegas content belong in OTIS at all? Confirm with counsel.

---

# Section B: Lead-warmer features milestone

**Scope.** The relayed request ("lets add the abive") could not be resolved from this step. **Confirm that "the above" means this lead-warmer list.**

**Prerequisite gaps** (from the code):
- `sync_signup_to_ghl` always tags `zero-harm-weekly` (`integrations.py:64`).
- The push "offers" switch doubles as email consent (`settings.tsx:47`).
- There is no GHL opportunity helper (`ghl.py:48-88`).
- There is no email backend (`settings.py:99-110`).
- Every "emailed PDF" therefore works the same way: upload to GHL Media, set a tag and a custom field, and a GHL workflow sends the email. This is the sign-in sheet pattern (`integrations.py:122-147`).

**Proposed GHL pipeline "Zero Harm app leads".** Jamil creates it, and the IDs go in Railway env vars (`GHL_PIPELINE_APP_LEADS`, `GHL_STAGE_*`). Stages:
1. Downloaded a tool
2. Asked a safety pro
3. Team interest
4. Team trial
5. Team customer

| ID | Feature and what it does | Lead hook (tags / stage) | Consent and guardrail copy (verbatim) | Backend + app work | Effort | Pairs with |
|---|---|---|---|---|---|---|
| **P0** | **Shared plumbing.** `LeadCapture` model plus `POST /api/leads/`: rate-limited, `%PDF` check (`views.py:216`), `ghl.upload_media`, upsert. Generic SQLite `outbox` plus `flushOutbox()`, called next to `flushSheets()` (`_layout.tsx:38`). Cron retry. New `ghl.set_custom_field` and `ghl.upsert_opportunity`. Separate push consent from email consent. Fix the README cron schedule (`README.md:43`) to match the 15-minute cron (`cron.py:14`). | `zero-harm-app` + `zero-harm-<magnet>`. Add `zero-harm-weekly` / `zero-harm-offers-optin` **only** if the user checked them. | Optional switches are unchecked by default: "Also send me Zero Harm Weekly", "News and offers". | `backend/talks/{models,views,urls,ghl,integrations,admin}.py`, `cron.py`, `lib/db.ts`, `lib/outbox.ts`, `app/_layout.tsx` | 2.5 d | O7 outbox pattern |
| **F1** | **OSHA 300A year-end worksheet PDF** plus posting and e-submission reminders.<br>• Fields G-M with a G+H+I+J = M1-M6 check, and TRIR/DART (`tools.tsx:18`). Stored on the device only.<br>• "Worksheet" PDF that does not copy the official form layout (reviewer's call).<br>• `RecordkeepingYear` rows served only when `counsel_reviewed`. Who must submit electronically is never computed in the app.<br>• `ReminderPush` cron with dates taken from that row. Proposed: 01-25, 02-01, 02-22, 03-01, 04-30. | `zero-harm-300a`, custom field `300a_pdf_url`, stage 1 | Screen and every PDF page: "This is a worksheet to check your numbers. A company executive must certify the 300A, and the totals must match your OSHA 300 log."<br>Fallback: "Check osha.gov for whether your establishment must submit electronically"<br>Settings row: "Recordkeeping reminders (300A posting and submission dates)" | `app/tools/osha-300a.tsx` plus a `Stack.Screen` title in `app/_layout.tsx`. `lib/pdf.ts`, `lib/db.ts`. `recordkeeping` tag added in `push.ts:16-17, :88, :98`, `settings.tsx:12` and `BROADCAST_TAGS`. Add the route to `FIXED_ROUTES` (`push.ts:63`); route support already exists (`push.ts:38-39`). Backend models, endpoint, admin action, tests. Drop calculator prefill, because that state is ephemeral (`tools.tsx:12-14`). | 5 d | A4 W1 recordkeeping entries. O4 KB entry. **Ship by about 2027-01-15.** |
| **F2** | **Training due-date calendar** with reminders that link to courses. Templates served from `TrainingInterval` rows (reviewed only, never hard-coded). Items stored on the device. | No tag by default. Optional email copy: `zero-harm-training-calendar`, stage 1 | "Reminder based on what you entered. Check your written program for your actual dates." | `app/tools/training.tsx`, `lib/training.ts`, `lib/db.ts`, `settings.tsx`, backend model and endpoint. Recommended: local reminders via `npx expo install expo-notifications` (dev build; coexistence with OneSignal ^5.5.16 on iOS is untested; `app.json` OneSignal plugin is in `mode: development`). | 4.5 d | W0 LOTO annual inspection, W1 HazCom initial assignment, W3 fit test, W6 forklift 3-year evaluation |
| **F3** | **Zero Harm Team tier** (first paid upsell). Email + 6-digit code login, Company/Membership, a shared sign-in history list, CSV and PDF-index export with counts only and no crew names. Everything free today stays free. | `zero-harm-team-interest` (stages 3, then 4, then 5), plus `zero-harm-team-owner` / `-supervisor` | History screen, CSV header and export: "Toolbox talk attendance. This is not certification of training required by an OSHA standard."<br>In-app: "Your company admin can add you" (no prices or purchase buttons) | Accounts backend, auth endpoints, transactional email (**not GHL** for login codes), `expo-secure-store`, Settings > Team with "Delete my account", FK links on SigninSheet (`views.py:198-225`), privacy policy updates (`README.md:53`). | 14 d | None. Schedule after F1. |
| **F4** | **"Ask a safety pro"** on NOT_COVERED. Only on the no-sources branch (`otis.tsx:133-136`) or a detected NOT_COVERED answer. Never on the urgent path, which needs an explicit short-circuit because it does not exist today (`otis.tsx:131-145`). Editable last question only. Unchecked opt-in "Send my question to Trainovate". Server-side urgent screen. Queued in the outbox when offline. Admin "Draft KB entry from answer" (unpublished). Optionally scrub names with `usePrivacyFilter` (exported at `src/index.ts:56`; untested). | `zero-harm-ask-pro` (never weekly), stage 2, GHL workflow alerts Jamil | Above Send: "This sends your question and email to Trainovate. Leave out names and details about injured people."<br>New onboarding (`otis.tsx:78`): "OTIS runs entirely on this phone. Your questions never leave it unless you choose Ask a safety pro, and OTIS works with no signal once it is set up."<br>Server reply for urgent questions: "If someone is hurt, call 911" | `app/otis-ask.tsx`, `app/otis.tsx`, backend `ProQuestion` model, endpoint, admin, data migration for the "What OTIS is" seed (`0005:9-13`). Update App Privacy answers. | 2.5 d | O2 (urgent short-circuit), O8 (NOT_COVERED detection), O5 (review loop), O7 (copy) |
| **F5** | **Inspection-readiness gap check.** 10-15 yes/no/NA questions from reviewed `GapQuestion` rows. Output is a list of gaps only: no score, percentage, grade or "ready". "Share PDF only" is the default. | `zero-harm-gap-check` plus `zero-harm-gap-<topic>`, stage 1 | No-gaps result: "These questions cover only a few common topics. They do not show that your site meets OSHA rules."<br>Email consent: "This sends your email and the list of gaps to Trainovate so we can email the report." | `app/inspect/gap-check.tsx`, `lib/gapcheck.ts`, `lib/pdf.ts`, backend model and endpoint, test asserting no "%" in output | 4 d | Content waves, O5 review flags |
| **F6** | **Nevada / Las Vegas rule pack.** FeedItem gets `citation`, `needs_review`, `reviewed_by/at`. Nevada and Las Vegas ingests are forced to `needs_review=True` (`views.py:171-172`), and a GHL re-send does not clear it. `released()` and the cron query (`cron.py:20-21`) filter it out. The console feed, feed_item and feed_push endpoints (`console.py:338-400`) must respect the same gate. | No tag on read. Optional `zero-harm-nevada-pack` | Existing not-legal-advice line (`alert/[id].tsx:33-35`). Admin action: "Mark reviewed against NRS 618 / Nevada OSHA" | `backend/talks/{models,views,admin,console}.py`, `cron.py`, `app/alerts.tsx`, `lib/feed.ts`, tests | 2 d | W5 Nevada entries. O4 jurisdiction field. |
| **Q1** | **Share-this-talk link** (`src=share`). Button near the PDF button (`talk/[issue].tsx:119-121`). RN `Share` takes `url` on iOS only; on Android put the URL in `message` (`Share.js:64,110`). A `/t/<issue>/` landing page serves released talks only. Universal links later. | `zero-harm-share-visitor`, stage 1 only on signup | Share message: `${title} — free 5-minute toolbox talk` | `app/talk/[issue].tsx`, `backend/talks/views.py`, `backend/zeroharm/urls.py` | 1.5 d | None |
| **Q2** | **Monthly theme kits behind an email gate.** FeedItem `email_gate` and `month_theme`. ResourceCard (`components/feed.tsx:30-48`) opens `app/kit/[id].tsx`. January and February kits first. | `zero-harm-kit` + `zero-harm-kit-<slug>`, stage 1 | Unchecked: "Also send me Zero Harm Weekly", "News and offers". No certificates in kit content. | `components/feed.tsx`, `app/kit/[id].tsx`, `app/talk/[issue].tsx`, backend `KIND_WORDS` (`views.py:121-122`) | 1.5 d | A4 calendar, month by month |
| **Q3** | **GHS pictogram explainer**, bilingual and offline. Content bundled in `lib/ghs.ts`. EN/ES toggle (`talk/[issue].tsx:83-97`). The environment pictogram is shown as "not required by OSHA". | None. Optional `zero-harm-ghs-poster` | "Read the label and SDS, ask your supervisor" line (exact wording for CSP to approve) | `app/tools/ghs.tsx`, `lib/ghs.ts`, `assets/images/ghs/*`. Matching EN/ES KB entries need O4 `lang`. | 2.5 d | W1 Chemicals, O4 |

Section B total is about 42.5 days, of which F3 is 14.

**Do-not-build list** (X1, 0.5 d, enforced by a backend banned-phrase test on the Team export, the 300A worksheet and the gap report, and added to the reviewer checklist):
- No "days since last injury" counter or widget.
- No certificate, "certified", "completion certificate" or "trained" badge for talks, Zero Hour or quizzes.
- No "% compliant", score or readiness grade on the gap check.
- No promises on the Report tab about what happens after a near-miss report (`report.tsx:8-12` must stay neutral).
- No login codes through GHL. No crew names in the Team export. No prices or purchase links in the app until counsel clears it.

**What Jamil must decide or get reviewed**

*Decide*
1. Confirm "the above" means this lead-warmer list.
2. Create the GHL pipeline and stages, and the tag-triggered workflows that email the media URL.
3. Training reminders: local `expo-notifications`, where dates stay on the phone (recommended), or OneSignal time-based tags?
4. Team tier: pricing, sales motion (GHL invoice only), seats, trial length, and whether owners see supervisor emails. Choose a transactional email provider.
5. Share host: a GHL funnel page or a Django `/t/<issue>/` page? Universal links now or later?
6. Nevada pack as its own `rule_card` kind or as grouped alerts?
7. Confirm the Railway cron really runs every 15 minutes. Date-based pushes depend on it.
8. Name the CSP and counsel, with turnaround times before the January 2027 300A window.

*Get reviewed*
- **Confirm with counsel:**
  - 1904.32(b)(3)-(6) (certification and Feb 1-Apr 30 posting).
  - 1904.41(c) March 2 deadline (2027-03-02 is a Tuesday).
  - ITA applicability: 250+ employees in any industry required to keep records; 20-249 in Appendix A; 100+ in Appendix B for 300/301 data under the **July 2023 final rule, effective 2024**.
  - Whether Nevada OSHA employers submit through federal ITA.
  - Whether to copy the official 300A form layout.
- **Confirm with counsel:**
  - Apple 5.1.1(v) account deletion; 4.8 applies only to third-party login; 3.1.1/3.1.3 B2B unlock without IAP and the post-Epic US link rules.
  - Google Play account-deletion requirement.
  - Storing gap lists and injury counts in GHL.
  - Retention and deletion policy for Ask-a-pro questions.
  - GHS artwork licensing.
- **Confirm with CSP:**
  - Training intervals: 1910.178(l)(4)(iii) every 3 years; 1910.147(c)(6)(i) annual; 1910.134(f)(2) annual; 1910.1200(h)(1) "initial assignment", plus the 2024 HazCom compliance dates.
  - The current OSHA top-10 general-industry list for gap questions (exclude 1926).
  - Each gap question's citation and wording.
  - 1910.1200 App. C pictograms.
  - Every Nevada card against NRS/NAC 618, including the Nevada heat rule (reportedly R131-24).
- **Confirm with the GHL operator:**
  - Opportunity upsert path and scopes for the private-integration token.
  - Setting custom fields through the upsert payload.
  - Whether Media Storage URLs stay public and do not expire.
- **Privacy:** update the privacy policy and App Privacy labels for every feature that sends data off the phone. Keep the OTIS copy consistent with O7 and F4.
- **Rate limits:** the signup limit of 5 per IP per hour (`views.py:42-46`) may block a whole crew on shared plant Wi-Fi. Decide whether to raise it for `/api/leads/`.

Nothing was edited. The two Bash calls only re-read current line numbers in `/Users/jamiljones/dev/ZeroHarmApp/backend/talks/console.py`, `/Users/jamiljones/dev/ZeroHarmApp/app/otis.tsx`, `/Users/jamiljones/dev/ZeroHarmApp/lib/push.ts`, `/Users/jamiljones/dev/ZeroHarmApp/lib/otis/kb.ts`, `/Users/jamiljones/dev/ZeroHarmApp/backend/talks/views.py` and `/Users/jamiljones/dev/ZeroHarmApp/backend/talks/urls.py`, and confirmed `usePrivacyFilter` and `QWEN3_4B` exist in `/Users/jamiljones/dev/ZeroHarmApp/node_modules/react-native-executorch/src/`.
