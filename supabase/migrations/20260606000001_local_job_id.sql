-- Plan 3: link a cloud job to the PC-local backend job driving it.
-- Written by the agent (service role); visible to the owner via existing
-- select policy (a uuid hex is harmless).
alter table public.jobs add column local_job_id text;
