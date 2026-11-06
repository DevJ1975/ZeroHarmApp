-- Zero Harm app: toolbox talks + optional app sign-ups
-- Run with: supabase db push   (then: supabase db reset to load seed.sql locally)

create table if not exists public.toolbox_talks (
  issue            int primary key,                 -- Zero Harm Weekly issue number
  issue_date       date not null,                   -- the Monday the issue is dated
  send_at          timestamptz not null,            -- Sunday 11:59 AM Pacific, the day before
  month_theme      text not null,
  title            text not null,
  story_title      text not null,
  crew_question    text not null,
  body_md          text,                            -- full talk text (Markdown), added before launch
  hero_url         text,                            -- hosted hero photo (Vercel)
  pdf_url          text,                            -- hosted toolbox PDF (Vercel)
  ghl_template_id  text,                            -- matching GoHighLevel email template
  published        boolean not null default true,
  updated_at       timestamptz not null default now()
);

create index if not exists toolbox_talks_send_at_idx on public.toolbox_talks (send_at);

-- The app can only read talks whose Sunday send time has passed.
alter table public.toolbox_talks enable row level security;

drop policy if exists "Released talks are public" on public.toolbox_talks;
create policy "Released talks are public"
  on public.toolbox_talks for select
  to anon, authenticated
  using (published and send_at <= now());

-- Optional "save my history / get the weekly talk" sign-ups.
-- Inserts come only from the app via the anon key; nobody can read them back from the app.
create table if not exists public.app_signups (
  id           uuid primary key default gen_random_uuid(),
  email        text not null,
  first_name   text,
  company      text,
  wants_offers boolean not null default false,       -- separate consent for promotional messages
  source       text not null default 'zero-harm-app',
  synced_to_ghl boolean not null default false,
  created_at   timestamptz not null default now()
);

alter table public.app_signups enable row level security;

drop policy if exists "App can submit sign-ups" on public.app_signups;
create policy "App can submit sign-ups"
  on public.app_signups for insert
  to anon, authenticated
  with check (true);
