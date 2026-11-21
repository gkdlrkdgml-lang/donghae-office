// 관리자 화면이 쓰는 Supabase 연결 정보.
// url, anon(publishable) 키는 웹페이지에 들어가도 되는 공개용 값입니다(권한은 DB 규칙이 지킴).
// service_role(비밀) 키는 절대 여기에 넣지 말고 GitHub Secret SUPABASE_SERVICE_KEY 에만 넣습니다.
window.DH_ADMIN = {
  url: 'https://zkdsystvrakicrkckcrd.supabase.co',
  anonKey: 'sb_publishable_EA-Zz_6YVEloxXYANEgZoQ_81RAqrv0'
};
