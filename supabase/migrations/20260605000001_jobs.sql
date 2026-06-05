-- Online hosting Plan 1: jobs table + admin registry + RLS (spec §3-4).

create table public.jobs (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users (id) on delete cascade,
  sport           text not null check (sport in ('football','basketball')),
  match_name      text not null check (char_length(match_name) between 1 and 120),
  match_date      date,
  declared_duration_min int not null check (declared_duration_min between 1 and 240),
  deliverables    text[] not null,
  state           text not null default 'submitted' check (state in
    ('submitted','approved','quota_waiting','uploading','uploaded','processing',
     'operator_action','ready','expired','rejected','failed')),
  state_detail    text,
  progress        int not null default 0 check (progress between 0 and 100),
  drive_folder_id text,
  drive_file_id   text,
  file_size_bytes bigint,
  results_url     text,
  error_message   text,
  reject_reason   text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  expires_at      timestamptz,
  -- contract: deliverable names are frozen
  constraint jobs_deliverables_valid check (
    deliverables <@ array['coach_analytics','event_highlights','player_highlights']::text[]
    and array_length(deliverables, 1) >= 1),
  -- spec §0.7: full matches (>20 min) are analytics-only at launch
  constraint jobs_fullmatch_analytics_only check (
    declared_duration_min <= 20 or deliverables = array['coach_analytics']::text[])
);

create table public.app_admins (
  user_id uuid primary key references auth.users (id) on delete cascade
);

create or replace function public.is_admin() returns boolean
language sql stable security invoker as
$$ select exists (select 1 from public.app_admins where user_id = auth.uid()) $$;

create or replace function public.touch_updated_at() returns trigger
language plpgsql as
$$ begin new.updated_at = now(); return new; end $$;

create trigger jobs_touch before update on public.jobs
  for each row execute function public.touch_updated_at();

alter table public.jobs enable row level security;
alter table public.app_admins enable row level security;

-- Users read their own jobs; the admin reads all.
create policy jobs_select on public.jobs for select
  using (auth.uid() = user_id or public.is_admin());

-- Users create jobs only for themselves, only in 'submitted'.
create policy jobs_insert on public.jobs for insert
  with check (auth.uid() = user_id and state = 'submitted');

-- NO update/delete policies: all state transitions go through Edge Functions
-- (service role) or the PC agent (service role). Spec §3.

-- Users may check whether THEY are an admin (drives the site's admin view).
create policy app_admins_select_self on public.app_admins for select
  using (auth.uid() = user_id);
