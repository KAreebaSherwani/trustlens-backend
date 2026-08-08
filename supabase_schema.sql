-- Run this once in Supabase → SQL Editor → New query → Run

create table if not exists applications (
  id           text primary key,
  name         text,
  city         text,
  level        text,
  confidence   int,
  status       text,
  case_id      text,
  created_at   timestamptz,
  profile      jsonb,
  risk         jsonb,
  history      jsonb
);

create table if not exists cases (
  case_id         text primary key,
  application_id  text,
  applicant_name  text,
  risk_level      text,
  status          text,
  reason          text,
  created_at      timestamptz,
  history         jsonb
);

-- Demo-friendly: allow the service to read/write. Tighten later if you add auth.
alter table applications enable row level security;
alter table cases        enable row level security;
create policy "allow all applications" on applications for all using (true) with check (true);
create policy "allow all cases"        on cases        for all using (true) with check (true);