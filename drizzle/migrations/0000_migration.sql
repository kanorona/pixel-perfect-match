create table public.interview_sessions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  title text not null default 'Untitled interview',
  prompt text not null default '',
  duration_minutes int not null default 60,
  status text not null default 'draft' check (status in ('draft','live','ended')),
  candidate_token text not null unique default encode(extensions.gen_random_bytes(18),'hex'),
  candidate_editing_locked boolean not null default false,
  canvas jsonb not null default '{"elements":[]}'::jsonb,
  started_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
grant select, insert, update, delete on public.interview_sessions to authenticated;
grant all on public.interview_sessions to service_role;
alter table public.interview_sessions enable row level security;
create policy "owner select" on public.interview_sessions for select to authenticated using (auth.uid() = owner_id);
create policy "owner insert" on public.interview_sessions for insert to authenticated with check (auth.uid() = owner_id);
create policy "owner update" on public.interview_sessions for update to authenticated using (auth.uid() = owner_id) with check (auth.uid() = owner_id);
create policy "owner delete" on public.interview_sessions for delete to authenticated using (auth.uid() = owner_id);

create or replace function public.touch_updated_at() returns trigger language plpgsql set search_path = public as $$
begin new.updated_at = now(); return new; end $$;
create trigger trg_sessions_touch before update on public.interview_sessions for each row execute function public.touch_updated_at();

-- Candidate access via secret link token
create or replace function public.get_session_by_token(_token text)
returns table(id uuid, title text, prompt text, duration_minutes int, status text, candidate_editing_locked boolean, canvas jsonb, started_at timestamptz)
language sql stable security definer set search_path = public as $$
  select s.id, s.title, s.prompt, s.duration_minutes, s.status, s.candidate_editing_locked, s.canvas, s.started_at
  from public.interview_sessions s where s.candidate_token = _token and length(_token) >= 24
$$;
grant execute on function public.get_session_by_token(text) to anon, authenticated;

create or replace function public.save_canvas_by_token(_token text, _canvas jsonb)
returns boolean language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if pg_column_size(_canvas) > 2000000 then raise exception 'Canvas too large'; end if;
  update public.interview_sessions set canvas = _canvas
   where candidate_token = _token and status = 'live' and not candidate_editing_locked;
  get diagnostics n = row_count;
  return n > 0;
end $$;
grant execute on function public.save_canvas_by_token(text, jsonb) to anon, authenticated;