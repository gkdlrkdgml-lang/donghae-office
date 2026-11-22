-- 전체 잠금(2026-11-22): 「보기 전용(viewer)」 권한 + 자료 비공개 저장소(dash)
alter table public.profiles drop constraint if exists profiles_role_check;
alter table public.profiles add constraint profiles_role_check check (role in ('pending', 'viewer', 'admin', 'super', 'off'));

insert into storage.buckets (id, name, public)
values ('dash', 'dash', false)
on conflict (id) do update set public = false;

-- 승인된 계정(보기 전용·관리자·최고관리자)만 화면 자료(data/…)를 받을 수 있음. 수집 캐시(cache/…)는 서버만.
drop policy if exists "dash 승인 계정 읽기" on storage.objects;
create policy "dash 승인 계정 읽기" on storage.objects for select to authenticated
  using (bucket_id = 'dash' and (storage.foldername(name))[1] = 'data' and public.my_role() in ('viewer', 'admin', 'super'));
