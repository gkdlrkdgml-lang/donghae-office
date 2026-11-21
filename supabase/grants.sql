-- 7) 표 사용 권한(새 프로젝트는 자동으로 안 줌). 실제 허용 범위는 위 RLS 규칙이 정합니다.
grant usage on schema public to authenticated, service_role;
grant select, update on public.profiles to authenticated;
grant select, insert, update on public.entries to authenticated;
grant usage, select on sequence public.entries_id_seq to authenticated;
grant all on public.profiles, public.entries to service_role;
grant usage, select on sequence public.entries_id_seq to service_role;
grant execute on function public.my_role(), public.can_write(text), public.section_scope(text) to authenticated;
