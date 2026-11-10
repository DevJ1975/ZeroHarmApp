# Zero Harm: business logic audit and improvement plan

**Date:** 2026-11-10 · **Scope:** the app, the Django backend, the Railway setup, and the rules that decide what crews
see and what gets recorded. Each finding has a severity and a proposed fix. Nothing in the plan is built yet unless it
is listed under "Fixed during this audit".

## Summary

The rules that protect crews are in good shape: talks come from reviewed briefs, unsafe reports pull a talk, a rule
change pauses what depends on it, and everything works offline. The biggest gaps are around the edges:

1. **The production backend has never been deployed and can't start yet.** Required secrets are missing on Railway.
2. **Nothing tells you when the automatic system fails.** A blocked week, a pulled talk or a failed push is silent
   unless someone opens the dashboard.
3. **The local AI model publishes without having passed the safety test.** The test exists but nothing depends on it.
4. **Unlocking Zero Harm Weekly early leaks next week's answer** to this week's crew question.
5. **Sign-in sheets don't record what was taught**, and the records have no retention rule.

## Fixed during this audit

| Area | Problem | Fix |
|---|---|---|
| Deploy | Railway's health check hostname wasn't allowed, so every deploy would fail its health check | Allowed `healthcheck.railway.app` |
| Monday Minute | A short AI outage used up the whole week's attempts | Outages are retried on the next run and nothing is recorded |
| Monday Minute | The home screen showed the oldest talk, not this week's | List ordered explicitly, with a test |
| Abuse | One connection with made-up phone ids could pull any talk | A pull needs reports from three different networks |
| Abuse | Rate limits could be dodged with a forged header | Only the proxy's address is trusted |
| Safety | A pulled talk stayed in the phone's offline copy | The saved copy now matches the server |
| OTIS | Long regulation passages could overflow the phone model's context | Sources are trimmed to the part that matches the question |
| Weak signal | Screens waited up to 10 seconds on the network before showing saved data | Saved copy first, refresh in the background |
| Weak signal | A vote made with no signal was lost | Votes queue and send later |
| Monday Minute (B1) | The AI published without having passed the safety test | Safety gate: talks wait for approval until the current AI setup passes the test |
| Zero Harm Weekly (C1) | Early unlock opened the whole year and leaked "Last week's answer" | Only the next two talks open early, without last week's answer |
| Monday Minute (gate) | A talk marked ready on Wednesday still published if the AI later failed its safety test; a small hand-picked test could open the gate; approving a backlog sent a push per talk | The gate is re-checked before release; only full tests count, with a floor per kind of mistake; one push per approval |
| Measurement (G1) | The app recorded no installs or opens, so the back office couldn't show how many people use it or where | An anonymous once-a-day count per phone (hashed install id, approximate city, state and country, no network address stored) with a switch in the app's settings and `USAGE_ENABLED` on the server. The back office shows "Where the app is used". The privacy policy must mention it before release |
| Zero Harm Weekly | A phone's saved copy kept saying "Ready early" after the send time; unusual answer headings slipped through | The label follows the clock; more heading shapes are caught |

## Findings

### A. Operations (do these before launch)

| # | Severity | Finding | Proposed fix |
|---|---|---|---|
| A1 | Blocker | The Railway web and cron services have no deployment. `DJANGO_SECRET_KEY` is not set, so Django refuses to start. `ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `INGEST_KEY` and `BACKOFFICE_KEY` are also missing, so pushes, GHL sync, publishing from GHL and the back office won't work. | Set the variables on web and cron, connect the services to the repo's main branch, deploy. |
| A2 | High | No alerting. Failures only show in logs or the dashboard. | Send a notice (email through GHL, or a push to an admin tag) when: a week is blocked, a talk is pulled, an OSHA rule changes, a push fails, or the cron hasn't run for an hour. |
| A3 | High | No error monitoring, uptime check or confirmed database backup. | Add an error tracker, an uptime monitor on `/api/health/`, and confirm Railway Postgres backups are on. |
| A4 | Medium | One admin login, no second factor, and the admin is on the public internet. | Add two-factor login for the admin and one account per person. |
| A5 | Medium | No staging environment. Every change goes straight to production. | A second Railway environment with its own database and Ollama server. |
| A6 | Low | Rate limits and caches live in the web process and reset on every deploy. | Fine at this size. Move to a shared cache if you run more than one web process. |
| A7 | Launch | App store items still open: OneSignal in `development` mode in `app.json`, no privacy policy link in the app, store screenshots. | See F1 for the privacy policy contents. |

### B. Monday Minute

| # | Severity | Finding | Proposed fix |
|---|---|---|---|
| B1 | High | The local model has not been qualified. The safety test is there, but a talk publishes whether or not the model can catch planted mistakes. | Add a gate: the weekly run only publishes if the current model has a passing safety test on record (for example 90% of planted mistakes caught). Until it passes, run on Claude or hold talks for approval. |
| B2 | High | When both topic attempts fail, that week has no talk and nobody is told. | Keep a small bank of talks a person has approved in advance, and publish the next one when a week is blocked. Pair with A2. |
| B3 | Medium | Talks publish at 5:00 AM Pacific. That is 8:00 AM Eastern, after most first shifts have started, and Sunday night shifts get last week's talk. | Publish Sunday evening Pacific, or deliver by each phone's own time zone. |
| B4 | Medium | Topic choice doesn't spread categories. Three chemical topics can run back to back. | Skip the category used in the last two weeks unless nothing else is in season. |
| B5 | Medium | Comment moderation runs on the same small model, and its accuracy has never been measured. | Add comment cases to the safety test (names of injured people, insults, "skip the lockout" advice, normal shop talk). Hold the first comment from a new phone until checked. |
| B6 | Low | Display names are free text, so anyone can post as "Safety Manager" or "OSHA". | Block role and agency words in display names. |
| B7 | Low | Notes typed with a thumbs down are only visible inside each talk in the admin. | Show recent notes on the back-office page. |

### C. Zero Harm Weekly

| # | Severity | Finding | Proposed fix |
|---|---|---|---|
| C1 | High | Early unlock opens every talk with text, months ahead. Each issue includes "Last week's answer", so next week's talk gives away the answer to this week's crew question. It also removes the weekly reason to come back. | Unlock only the next one or two talks, and hide "Last week's answer" until the previous issue has gone out. |
| C2 | Medium | If the cron is down for more than a day around a Sunday, that week's push is skipped for good. | Widen the window to three days and alert (A2). |
| C3 | Low | Two Monday programs (Zero Harm Weekly and Monday Minute) compete for the same meeting. Sign-ins and attention are split. | Decide the roles. For example: Monday Minute is the weekly talk, Zero Harm Weekly is the deeper story and the newsletter. Say so on the Today tab. |

### D. Sign-in records

| # | Severity | Finding | Proposed fix |
|---|---|---|---|
| D1 | High | A sign-in sheet shows the talk's title but not what was said. If a talk is later pulled or edited, the record no longer proves what the crew was told. | Print the talk text (or a version stamp) on the signed sheet. |
| D2 | High | No retention rule. Sheets hold names, signatures and sometimes a crew photo. If GHL is down for more than 14 days the PDF stays in the database with no retry and no clean-up. | Set a retention period, keep retrying, and delete sheets that pass the limit. Needs a lawyer's view on how long training records should be kept. |
| D3 | Medium | Saving the same session twice creates two server records, so the dashboard double counts. | Send a unique id per session and update the existing record. |
| D4 | Medium | The head count for a group photo is typed by the supervisor and can't be checked. | Label it on the sheet as "counted by the supervisor" (already there) and report signature counts and photo counts separately. |
| D5 | Low | Sheets kept on the phone are lost if the app is deleted. | Already stated in the app. Consider an "email me a copy" default. |

### E. Sign-ups and GoHighLevel

| # | Severity | Finding | Proposed fix |
|---|---|---|---|
| E1 | Medium | Signing up twice with the same email creates two rows. Counts are inflated. | One row per email, updated on repeat sign-ups. |
| E2 | Medium | Saving a sheet to records creates or updates a GHL contact for the supervisor and tags it. The app says the sheet is sent to Trainovate, but not that a contact record is created. | Say so next to the button, and keep marketing tags tied to the separate offers consent. Needs the privacy policy (F1). |
| E3 | Low | The offers consent is stored as yes or no, without the wording or the time it was given. | Store the time and the consent text version. |

### F. Privacy and legal (need a person)

| # | Finding | Who |
|---|---|---|
| F1 | The privacy policy must cover: email, push token, approximate location for weather, crew names, signatures and photos sent by a supervisor, comments, ratings, and the random install id. | Lawyer |
| F2 | Crew photos and signatures are collected by a supervisor about other people. Check consent wording and state rules on worker images. | Lawyer |
| F3 | Public comments can describe an employer's conditions. Terms should cover user content and removal. | Lawyer |
| F4 | AI-written safety content: the in-app note is there. Terms should say it adds to training and doesn't replace it. | Lawyer |
| F5 | Items already listed in `docs/monday-minute-topic-review.md` (state reporting deadlines, medical privacy, industrial hygiene). | Lawyer, IH |

### G. Measurement

| # | Severity | Finding | Proposed fix |
|---|---|---|---|
| G2 | Low | There is no measure of whether talks lead to newsletter sign-ups or demo requests. | Tag links from the app (already done for the newsletter) and show the counts from GHL on the back-office page. |

## Plan

**Before launch (this week)**
1. A1: set the Railway secrets and deploy web and cron.
2. B1: run the safety test on the local model and add the publish gate. If the model fails, switch `AI_PROVIDER` to `anthropic` or add an approval step.
3. C1: limit early unlock and hide "Last week's answer".
4. A2: alerts for blocked weeks, pulled talks, rule changes and failed pushes.
5. A7 and F1: privacy policy, OneSignal production mode, store assets.

**First month**
6. D1, D3: talk text on signed sheets, one record per session.
7. B2: an approved fallback bank.
8. B3, B4: publish time and category spacing.
9. D2: retention rule and clean-up job, after the lawyer's answer.
10. A3, A4: monitoring, backups check, two-factor admin.
11. E1, E2, E3: sign-up clean-up and consent records.

**Later**
12. B5, B6, B7: moderation tests, display name rules, notes on the dashboard.
13. G2: funnel numbers. (G1, usage counts, is done; see "Fixed during this audit".)
14. A5: staging environment.
15. C3: decide the roles of the two weekly programs.
16. Spanish for Monday Minute and the highest-risk OTIS answers, with a human translator.
