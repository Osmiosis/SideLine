-- Review hardening (Task 2 follow-up): indexes on the hot access paths
-- (user "my jobs", admin/agent state polling, expiry sweep) and a
-- robustness fix to the analytics-only constraint (order-insensitive).

create index jobs_user_id_idx on public.jobs (user_id);
create index jobs_state_idx on public.jobs (state);
create index jobs_expires_at_idx on public.jobs (expires_at) where state = 'ready';

-- '=' was exact order-sensitive array equality; '<@' expresses the intent
-- (only coach_analytics allowed) without wedging future agent updates.
-- jobs_deliverables_valid still enforces non-empty.
alter table public.jobs drop constraint jobs_fullmatch_analytics_only;
alter table public.jobs add constraint jobs_fullmatch_analytics_only check (
  declared_duration_min <= 20 or deliverables <@ array['coach_analytics']::text[]);
