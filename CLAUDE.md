# 동해시 AI 시장실 — 작업 인계 메모 (Claude용)

사용자: 강희(동해시 안전과). **존댓말**, 짧고 바로 해결하는 답을 선호. 만든 결과는 묻지 말고 바로 보여 주기.

## 무엇인가
- 1920×1080 TV용 시장실 대시보드. 사이트: https://gkdlrkdgml-lang.github.io/donghae-office/
- `collect/` 파이썬 수집기 → GitHub Actions(`collect.yml`)가 돌며 `web/data/data.js`를 만들고 Pages로 배포.
  **push만으로는 다시 배포되지 않음** → `gh workflow run collect.yml --ref main` (돌고 있는 실행이 끝난 뒤).
- 화면은 `web/index.html` 한 파일(바닐라 JS). 탭 순서: 한눈에 보기, 행정, 경제, 보건 및 의료, 복지, 관광, 예산, 교통, 환경, 상하수도, 액자.
- 지표 정의: `config/settings.json` indicators(dir: 1 높을수록 좋음, -1 낮을수록 좋음, 0 판정 안 함). 순위는 **좋은 쪽이 1위**.
- 수집 결과 캐시는 `L[key]['at']`, `stale(key, days)`로 다시 받을지 결정.

## 꼭 지킬 규칙
- **정확한 값만.** 가짜·추정 숫자 금지(예측은 「예상치」로 분명히 표시). 자료 없는 메뉴는 숨김.
- **가능한 한 2026년 최신 자료**, API로 자동 수집(수동 입력 지양). 연도·기간을 화면에 정확히 표시.
- 지역을 누르면 그 지역 + 동해·강원 평균 비교. 18개 시·군 비교를 중요하게 봄.
- 흰색·네이비·컬러풀 디자인, 제목은 한 줄. 크게 보기에서 수치가 보이게.
- API 키는 **GitHub Secrets에만**(채팅에 붙이지 않기). 공공데이터포털 키(`DATA_GO_KR_KEY`)는 **Encoding 키** → 코드에서 `urllib.parse.unquote()` 한 뒤 보낼 것(안 그러면 「등록되지 않은 서비스키」).
- 한국 정부 사이트는 작업 환경에서 직접 안 열림 → `collect/probe.py`에 시험 코드를 넣고 `gh workflow run probe.yml` 후 로그를 grep.
- 커밋: `git -c user.name="강희" -c user.email="gkdlrkdgml-lang@users.noreply.github.com" commit ...`

## 주요 자료원(이미 연결됨)
KOSIS(여러 표), 국세통계포털 TASIS(월별 가동·신규 사업자), 행안부 인허가 API(음식점·숙박 개업·폐업),
소상공인 상가정보(분기 목록 → `web/data/stores_snap.json`과 비교해 폐업 계산, 첫 폐업 숫자는 12월 기준 목록이 나오면),
복지로 복지통계, 심평원·NMC 의료기관, 관광자원통계 GW(`B551940`, 유료관광지 월 입장객),
환경부 상·하수도 통계, 지방공기업 경영정보, 기상청 ASOS 일자료, 에어코리아 대기오염통계(7월~만 제공), 국립환경과학원 수질 DB.

## 관리자 입력 — 아이디·비밀번호 방식(2026-11-22 바꿈, Supabase)
- 사용자 요청: 관리자 아이디를 만들어 관리자(약 15명)가 로그인해서 동해시 자료(행정·경제, 기준일별)를 넣게.
- `web/admin.html`: 아이디·비밀번호 로그인 / 가입 신청 → 최고관리자가 승인·분야(행정 admin, 경제 economy) 지정·사용 중지·비밀번호 초기화.
  아이디는 `아이디@dh-office.local`(안 되면 `@dh-office.example.com`) 이메일로 Supabase Auth에 저장. 맨 처음 가입자 = 최고관리자(super).
- Supabase 연결 정보: `web/admin-config.js`(url, anon 공개키). DB 구성: `supabase/setup.sql`(profiles, entries, RLS, admin_set_password).
  Supabase 설정에서 Authentication → Email → 「Confirm email」 꺼야 함.
- 반영: `collect/admin_sync.py`가 service_role 키(GitHub Secret `SUPABASE_SERVICE_KEY`)로 entries를 받아 `manual/admin_input.json`(예전 형식)으로 만듦 →
  `run.py`의 `apply_admin_input()`이 build 때 복사본에만 덮어씀(동해 총인구·세대·남녀, 65세·15~64세 → 고령·생산연령 비율 재계산, 동별, admin_live).
  `.github/workflows/admin_watch.yml`이 10분마다 바뀜(state.json `admin_sig`)을 보고 `collect.yml mode=admin` 실행.
  (2026-11-22 01:50 기준 예약 실행이 아직 한 번도 안 돎 → 다음에 `gh run list -w admin_watch.yml`로 event=schedule 있는지 확인)
- 입력값 적용 규칙: 기준일이 공식 최신 달(인구·동별·인구변동) 또는 고용률 공식 반기 끝날보다 늦을 때만 사용, 아니면 API 값.
  인구는 공식 최신 달 대비(「10월 대비」) + 「지난 입력(날짜)보다」 증감 표시. 인구 증감률(전년 대비) 순위는 공식값 유지(같은 날짜 1년 전 값이 없어서).
- 동해시 로고(왼쪽 위)를 누르면 admin.html로 감(숨은 버튼). 시험: `gh workflow run probe.yml -f only=supabase` (명단·입력 확인).

## 국토·건축 탭(2026-11-22 만듦) — `web/land.js`
- 부지 검토(로그인한 관리자만, admin.html과 같은 Supabase 세션 `dh_admin_auth`): 지번·도로명·PNU → 브이월드(브라우저 JSONP: 지오코더·연속지적·토지이용계획·토지특성·토지임야)
  + 건축물대장은 Supabase Edge Function `land`(supabase/functions/land, 관리자 JWT 확인, DATA_GO_KR_KEY는 Supabase 비밀값) → 신호등 판정·근거 조문·토지이음 링크·1장 브리핑(인쇄).
  브이월드는 GitHub 서버(해외)에서 막힘 → 반드시 브라우저에서 호출. 판정 규칙은 참고자료/신호등 엔진 + 동해시 조례 원문 수치. 사용자 요청: 「도시과 확인 필요」 같은 문구 넣지 말 것(근거·원본을 최대한 보여 주기).
- 검토 이력: Supabase 표 `site_reviews`(supabase/sites.sql). SQL은 `gh workflow run db_sql.yml -f file=…`로 실행(SUPABASE_ACCESS_TOKEN).
- 조례 비교: `collect/landlaw.py`가 18개 시·군 도시계획(군계획) 조례에서 용도지역별 건폐율·용적률 추출(주 1회, LAW_OC). 일부 시·군은 조문 형식이 달라 몇 개 용도지역 값이 빠짐(원주·홍천·화천·인제 상업지역 용적률 등) → 빠진 곳은 비교에서 제외(추정 안 함).
- Edge Function 배포: `supabase/functions/**` 고치고 push하면 deploy_functions.yml이 자동 배포.
- 참고 코드: chrisryugj/archhub-mcp, korean-law-mcp (MIT). 다음 할 일: 국토·건축 현황 통계(노후·내진 미적용 추정·인허가, 18개 시·군 비교).

## 남은 일
- **전력 탭(「에너지·전력」) — 2026-11-21 만듦**: `collect/power.py`(한전 `KEPCO_KEY`, metroCd 51).
  계약종별·가구평균은 시·군 월별 25개월 보관(지난 달은 다시 안 받음), 산업분류는 최신 달만. 지표 pw_total·pw_house·pw_house_bill·pw_yoy·pw_ind_share(모두 dir 0).
  한전 서버가 자주 끊김(TLS timeout) → 한 번에 7분까지만 받고 나머지 달은 다음 실행에서 채움. 신재생(`renewEnergy.do`)은 아직 응답 못 받음 → 되면 추가.
  `gh workflow run probe.yml -f only=kepco`로 한전만 빠르게 점검 가능.
- **전자파(전파진흥원)**: `B552729/kcaApiService_emf/getEmfExposureIndex`, `B552729/KCCEWISLE/{bemf,meas,movebemf,fixbemf}` —
  신청은 승인됐으나 기관 서버가 504(연결실패). 살아나면 환경 탭에 추가.
- 쓰레기(폐기물) 2026년 자료는 공개 API 없음 → 동해시 자원순환 부서 월별 자료를 받으면 붙이기.
- 상수도 2025년 통계는 2027년 1월 공표 예정(자동 반영).
