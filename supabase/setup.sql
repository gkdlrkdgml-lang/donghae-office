-- 동해시 AI 시장실 · 관리자 계정/입력 저장소 (Supabase)
-- Supabase → SQL Editor → New query 에 이 파일 전체를 붙여 넣고 Run 을 한 번 누르면 됩니다.
-- 여러 번 실행해도 괜찮습니다(이미 있으면 건너뜀).

create extension if not exists pgcrypto with schema extensions;

-- 1) 관리자 명단: 가입 신청하면 '승인 대기(pending)'로 들어옴
create table if not exists public.profiles (
  id uuid primary key references auth.users on delete cascade,
  login_id text unique not null,
  name text not null,
  dept text,
  role text not null default 'pending' check (role in ('pending', 'admin', 'super', 'off')),
  scopes text[] not null default '{}',     -- 넣을 수 있는 분야: admin(행정), economy(경제)
  created_at timestamptz not null default now()
);

-- 2) 입력값: 저장할 때마다 한 줄씩 쌓임(누가 언제 무엇을 넣었는지 기록)
create table if not exists public.entries (
  id bigserial primary key,
  ref_date date not null,                  -- 기준일
  section text not null check (section in ('pop', 'dong', 'vital', 'employ')),
  data jsonb not null,
  author uuid not null default auth.uid() references auth.users on delete set null,
  author_name text,
  deleted boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists entries_date_idx on public.entries (ref_date, section, created_at desc);

-- 3) 권한 판단 함수
create or replace function public.my_role() returns text
language sql stable security definer set search_path = public as $$
  select role from public.profiles where id = auth.uid()
$$;

create or replace function public.section_scope(sec text) returns text
language sql immutable as $$
  select case when sec in ('pop', 'dong', 'vital') then 'admin' when sec = 'employ' then 'economy' else sec end
$$;

create or replace function public.can_write(sec text) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles p where p.id = auth.uid()
                 and (p.role = 'super' or (p.role = 'admin' and public.section_scope(sec) = any (p.scopes))))
$$;

-- 4) 가입하면 명단에 자동 등록. 맨 처음 가입한 사람은 최고관리자(super)
create or replace function public.on_signup() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, login_id, name, dept, role, scopes)
  values (new.id,
          coalesce(new.raw_user_meta_data ->> 'login_id', split_part(new.email, '@', 1)),
          coalesce(new.raw_user_meta_data ->> 'name', split_part(new.email, '@', 1)),
          new.raw_user_meta_data ->> 'dept',
          case when exists (select 1 from public.profiles where role = 'super') then 'pending' else 'super' end,
          '{}');
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.on_signup();

-- 5) 최고관리자만: 다른 관리자 비밀번호 초기화
create or replace function public.admin_set_password(uid uuid, pw text) returns void
language plpgsql security definer set search_path = public, extensions as $$
begin
  if public.my_role() <> 'super' then raise exception '최고관리자만 할 수 있습니다'; end if;
  if length(pw) < 8 then raise exception '비밀번호는 8자 이상'; end if;
  update auth.users set encrypted_password = extensions.crypt(pw, extensions.gen_salt('bf')), updated_at = now() where id = uid;
end $$;

-- 6) 접근 규칙(RLS)
alter table public.profiles enable row level security;
alter table public.entries enable row level security;

drop policy if exists "본인 또는 최고관리자 조회" on public.profiles;
create policy "본인 또는 최고관리자 조회" on public.profiles for select
  using (id = auth.uid() or public.my_role() = 'super');
drop policy if exists "최고관리자만 수정" on public.profiles;
create policy "최고관리자만 수정" on public.profiles for update
  using (public.my_role() = 'super') with check (public.my_role() = 'super');
drop policy if exists "최고관리자만 삭제" on public.profiles;
create policy "최고관리자만 삭제" on public.profiles for delete
  using (public.my_role() = 'super' and id <> auth.uid());

drop policy if exists "관리자 조회" on public.entries;
create policy "관리자 조회" on public.entries for select
  using (public.my_role() in ('admin', 'super'));
drop policy if exists "권한 있는 분야만 입력" on public.entries;
create policy "권한 있는 분야만 입력" on public.entries for insert
  with check (author = auth.uid() and public.can_write(section));
drop policy if exists "권한 있는 분야만 삭제표시" on public.entries;
create policy "권한 있는 분야만 삭제표시" on public.entries for update
  using (public.can_write(section)) with check (public.can_write(section));

grant execute on function public.admin_set_password(uuid, text) to authenticated;

-- 7) 표 사용 권한(새 프로젝트는 자동으로 안 줌). 실제 허용 범위는 위 RLS 규칙이 정합니다.
grant usage on schema public to authenticated, service_role;
grant select, update on public.profiles to authenticated;
grant select, insert, update on public.entries to authenticated;
grant usage, select on sequence public.entries_id_seq to authenticated;
grant all on public.profiles, public.entries to service_role;
grant usage, select on sequence public.entries_id_seq to service_role;
grant execute on function public.my_role(), public.can_write(text), public.section_scope(text) to authenticated;
