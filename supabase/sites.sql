-- 부지 검토 이력(화면 4: 검토 이력·비교). 로그인한 관리자만 보고 씀.
create table if not exists public.site_reviews (
  id bigserial primary key,
  pnu text not null,
  address text,
  status text check (status in ('GREEN', 'YELLOW', 'RED')),
  target_use text,
  summary jsonb not null default '{}'::jsonb,
  author uuid not null default auth.uid() references auth.users on delete set null,
  author_name text,
  created_at timestamptz not null default now()
);
create index if not exists site_reviews_created_idx on public.site_reviews (created_at desc);
alter table public.site_reviews enable row level security;
drop policy if exists "관리자 조회" on public.site_reviews;
create policy "관리자 조회" on public.site_reviews for select using (public.my_role() in ('admin', 'super'));
drop policy if exists "관리자 저장" on public.site_reviews;
create policy "관리자 저장" on public.site_reviews for insert with check (author = auth.uid() and public.my_role() in ('admin', 'super'));
drop policy if exists "본인 또는 최고관리자 삭제" on public.site_reviews;
create policy "본인 또는 최고관리자 삭제" on public.site_reviews for delete using (author = auth.uid() or public.my_role() = 'super');
grant select, insert, delete on public.site_reviews to authenticated;
grant usage, select on sequence public.site_reviews_id_seq to authenticated;
grant all on public.site_reviews to service_role;
