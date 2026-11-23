# 동해시 AI 시장실 — 작업 인계 메모 (Claude용)

사용자: 강희(동해시 안전과). **존댓말**, 짧고 바로 해결하는 답을 선호. 만든 결과는 묻지 말고 바로 보여 주기.

## 무엇인가
- 1920×1080 TV용 시장실 대시보드. 사이트: https://gkdlrkdgml-lang.github.io/donghae-office/
- `collect/` 파이썬 수집기 → GitHub Actions(`collect.yml`)가 돌며 `web/data/data.js`를 만들고 Pages로 배포.
  **push만으로는 다시 배포되지 않음** → `gh workflow run collect.yml --ref main` (돌고 있는 실행이 끝난 뒤).
- 화면은 `web/index.html` 한 파일(바닐라 JS). 탭 순서: 한눈에 보기, 행정, 경제, 보건 및 의료, 복지, 관광, 예산, 토지 및 건축, 교통, 농업 및 수산(10번, 사용자 지정), 환경, 상하수도, 에너지·전력, 흘러가기(액자는 2026-11-23 사용자 요청으로 메뉴에서 뺌, 화면 코드는 남음). 메뉴 간격 gap 7px·padding 6px(더 넓히면 1920 폭을 넘음).
- 인쇄(2026-11-23): 위쪽 줄 오른쪽 🖨 단추(#printBtn) → `dhPrint()`가 지금 보이는 탭을 A4 가로 1장(@media print, #stage zoom 0.562, 비서실장·설치 단추 숨김), 파일 이름 「동해시 AI 시장실 탭 아래탭 날짜」. 위쪽 줄이 딱 1920px(header padding 18px, hright gap 9px) — 더 넣으면 넘침.
- 흘러가기(`screenFlow`): 메뉴·아래 탭을 골라 정해진 간격(10초~2분)으로 계속 돌림. 선택·진행은 localStorage `dh_flow`(30분 새로 고침 뒤에도 이어서). 아래 탭은 `.title .subtabs button` 또는 `[data-subtab]` 글자로 찾아 누름. 메뉴·아래 탭을 사람이 누르거나 Esc·스페이스·「멈춤」이면 멈춤.
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

## PWA(2026-11-22)
- `web/manifest.webmanifest`(display fullscreen, 아이콘 img/icon-192·512·mask-512), sw.js(같은 출처만 캐시, CACHE v3). Chrome·Edge에서 설치하면 주소창 없이 전체 화면 → 1920×1080 무대(#stage, 화면에 맞춰 확대·축소)가 꽉 참.
  `web/install.js`(DHInstall): 화면 왼쪽 아래 「⤓ 바탕화면에 설치」 단추(#pwaBtn, 앱으로 열었으면 숨김) + 로그인 창 아래 링크. 사용자 요청: 안내 말고 바로 설치 → 단추는 브라우저가 설치 가능하다고 알려 줄 때(beforeinstallprompt)만 보이고 누르면 바로 설치 창. 아이패드·아이폰만 예외(설치 API가 없어 공유→홈 화면에 추가 안내).

## 전체 로그인 잠금(2026-11-22, 무료 방식)
- 시장실 화면(`index.html`)은 `web/auth.js`가 먼저 로그인 → 승인 계정(role viewer 보기 전용·admin·super)만 열림. 세션은 `dh_admin_auth`(admin.html과 공유), 클라이언트는 `window.DH_SB` 하나.
- 자료는 **GitHub에 없음**: `collect/store.py`가 Supabase 비공개 버킷 `dash`에 `data/data.json.gz`(화면 자료, 승인 계정 읽기)·`cache/*.json.gz`(state·stores_snap, 서버 키만) 올리고 받음. collect.yml이 pull → run → push, Pages 올리기 전 `web/data` 삭제. `web/data/`는 .gitignore.
- 화면은 저장소에서 받아 gzip 풀어 `window.DONGHAE_DATA`; 실패 시 Cache API `dh-data-v1`의 마지막 자료.
- Edge Function `land`도 승인 계정 JWT 필요. 잠금 점검: `gh workflow run probe.yml -f only=lock`(임시 보기 전용 계정 만들어 시험 후 삭제).
- 새 TV·PC는 한 번 로그인. 계정은 admin.html 「관리자 관리」에서 역할 「보기 전용」 지정. 정책 SQL: `supabase/lock.sql`.
- git 예전 기록에는 잠금 전 자료가 남아 있음(사용자가 지우라고 하지 않음).

## 관리자 입력 — 아이디·비밀번호 방식(2026-11-22 바꿈, Supabase)
- 사용자 요청: 관리자 아이디를 만들어 관리자(약 15명)가 로그인해서 동해시 자료(행정·경제, 기준일별)를 넣게.
- `web/admin.html`: 아이디·비밀번호 로그인 / 가입 신청 → 최고관리자가 승인·분야(행정 admin, 경제 economy) 지정·사용 중지·비밀번호 초기화.
  아이디는 `아이디@dh-office.local`(안 되면 `@dh-office.example.com`) 이메일로 Supabase Auth에 저장. 맨 처음 가입자 = 최고관리자(super).
- Supabase 연결 정보: `web/admin-config.js`(url, anon 공개키). DB 구성: `supabase/setup.sql`(profiles, entries, RLS, admin_set_password).
  Supabase 설정에서 Authentication → Email → 「Confirm email」 꺼야 함.
- 반영: `collect/admin_sync.py`가 service_role 키(GitHub Secret `SUPABASE_SERVICE_KEY`)로 entries를 받아 `manual/admin_input.json`(예전 형식)으로 만듦 →
  `run.py`의 `apply_admin_input()`이 build 때 복사본에만 덮어씀(동해 총인구·세대·남녀, 65세·15~64세 → 고령·생산연령 비율 재계산, 동별, admin_live).
  `.github/workflows/admin_watch.yml`이 10분마다 바뀜(state.json `admin_sig`)을 보고 `collect.yml mode=admin` 실행.
  (예약 실행은 GitHub가 10분 간격을 지키지 않음 — 실제 4~7시간.) → 2026-11-23: admin.html 저장·삭제 때 `rebuildNow()` → Supabase 함수 `rebuild`(admin·super JWT, 1분 1회) → GitHub API로 collect.yml mode=admin 실행. GitHub 토큰은 Secret `GH_DISPATCH_TOKEN`(fine-grained, 이 저장소 Actions 읽기·쓰기) → deploy_functions가 Supabase 비밀값으로 넣음. 토큰 없으면 「몇 시간 안에 반영」 안내.
- 입력값 적용 규칙: 기준일이 공식 최신 달(인구·동별·인구변동) 또는 고용률 공식 반기 끝날보다 늦을 때만 사용, 아니면 API 값.
  고용 입력이 공식 반기보다 이르면 고용률·취업자만 버리고 일자리 사업 참여자·일자리 창출(공식 자료 없음)은 그대로 씀.
  동별 입력: 법정동(A.dongs) + 행정동은 dong 데이터 안 `_admm`{행정동:{total, age65}} → A.admm 덮어씀(행정동 3D 지도·행정동 표, 고령 비율 재계산, prev_total=공식 최신 달 값, 입력 안 한 동은 prev_total 비움), A.admm_live={date, official_ym}.
  인구 비교 화면 제목·KPI는 관리자 입력일 때 「동해시는 날짜 기준 관리자 입력」, 「10월보다」「2025년 10월보다」로 표시(지난달·1년 새 대신).
  인구는 공식 최신 달 대비(「10월 대비」) + 「지난 입력(날짜)보다」 증감 표시. 인구 증감률(전년 대비) 순위는 공식값 유지(같은 날짜 1년 전 값이 없어서).
- 인구 입력 칸 「1인가구」(hh1 → A.vital.hsmb.cur[동해].one, prev=공식, hsmb.live=날짜) · 「청년 19~34세」(age19_34, 2026-11-23 사용자 요청) → A.youth.cur.youth(청년층 카드), 15~64세는 선택. admin.html 경고: 15~64세가 총인구 40% 미만·행정동 합계(인구·65세 이상)가 시 전체와 다르면.
- admin.html 맨 위 「지금 시장실 화면에 나오는 동해시 값」(drawNow: 총인구·세대·출생사망·취업자·일자리 사업 참여자·일자리 창출·고용률, 공식/관리자 입력 출처 표시) + 저장된 입력 표에 「시장실 반영」 칸(status: 반영 중 / 공식 자료가 더 최신→공식 값 / 반영 대기 / 더 최근 입력이 반영 중). D.admin_live·D.admin.ym·life.employ.period로 판단. 사용자: 반영된 입력이 없어 헷갈린다고 해서 만듦.
- 동해시 로고(왼쪽 위)를 누르면 admin.html로 감(숨은 버튼). 글자 「동해시 AI 시장실」(#appTitle)을 누르면 새로 고침(F5와 같음). 시험: `gh workflow run probe.yml -f only=supabase` (명단·입력 확인).

## 국토·건축 탭(2026-11-22 만듦) — `web/land.js`
- 부지 검토(로그인 없이 — 사용자가 이력·로그인 불필요하다고 함. 최근 검토는 브라우저 localStorage `dh_land_recent`에만): 지번·도로명·PNU → 브이월드(브라우저 JSONP: 지오코더·연속지적·토지이용계획·토지특성·토지임야)
  + 건축물대장은 Supabase Edge Function `land`(supabase/functions/land, 승인 계정 JWT 필요 + IP당 10분 60회, DATA_GO_KR_KEY는 Supabase 비밀값) → 신호등 판정·근거 조문·토지이음 링크·1장 브리핑(인쇄).
  브이월드는 GitHub 서버(해외)에서 막힘 → 반드시 브라우저에서 호출. 판정 규칙은 참고자료/신호등 엔진 + 동해시 조례 원문 수치. 사용자 요청: 「도시과 확인 필요」 같은 문구 넣지 말 것(근거·원본을 최대한 보여 주기).
- 지도 레이어(2026-11-22): 브이월드 WMS(EPSG:900913, STYLES=레이어명) 켜고 끄기 — 연속지적·도시계획도로(lt_c_upisuq151)·상수원보호(lt_c_um710)·법정동(lt_c_ademd)·시군경계·용도지역·지구단위·산업단지, 일반/항공사진(WMTS Satellite+Hybrid). 선택은 localStorage `dh_land_layers`.
  레이어 이름 출처: UrbanWatcherKr/korean-land-mcp, clazic/vworld(.2ddata_cache). **경제자유구역 레이어는 브이월드에 없음** → 토지이용계획 목록의 「경제자유구역」으로 판정만. 과거 항공사진은 공개 API 없음 → 국토정보플랫폼·카카오맵 링크.
  상수원보호구역은 `near('LT_C_UM710', 필지, 3km)`로 경계까지 거리 계산(안=빨강, 1km 이내=노랑, 그 밖=참고, 없음=초록). 토지이용계획 규칙(RULES)에 공장설립제한·수질보전특별대책·접도·홍수관리·자연공원·백두대간·경자구역 등 추가.
- 검토 이력: 서버 저장 안 함(표 `site_reviews`는 만들어 두었으나 미사용). SQL은 `gh workflow run db_sql.yml -f file=…`로 실행(SUPABASE_ACCESS_TOKEN).
- 예정 용도 판정(2026-11-22): 동해시 조례 별표 1~22(시행령+조례 통합 「건축할 수 있는/없는 건축물」, 한글 파일)를 류주임 **kordoc**(npx, `collect/hwp.py`, 워크플로에 setup-node)으로 읽어 `ordin.regions.동해.uses`에 저장 → land.js `useJudge`가 건축법 시행령 별표 1 호 번호로 판정(있는 목록: 없음=빨강, 조건=노랑 / 없는 목록: 없음=초록, 조건=노랑), 해당 조항 원문 표시. 자연취락지구면 별표 22도 판정.
  세부 용도(SUBS: 건축법 시행령 별표 1의 목 글자+낱말, 「제외」 괄호·「중」 목록·「같은 호 가목부터 라목」 해석) + 바닥면적·층수·도로폭 입력(도로폭 없으면 토지특성 도로접면 광대 25+/중로 12~25/소로 8~12/세로 8 미만으로 판단) → ✔/✖ 표시. 지구단위계획·개발제한구역·특정용도제한·개발진흥지구면 초록을 노랑으로 낮추고 우선 적용 법조 표시. 별표 형식 바뀌면 `uses_v` 올려 다시 읽기. 22개 표 대조: `probe.yml -f only=annex3`.
  남는 조건: 「주거지역으로부터 5m 밖」은 브이월드 LT_C_UQ111(300m 안) 주거지역 경계 거리로 자동(필지 경계 기준, 「주택 밀집지역」은 자동 안 함), 그 밖의 조건은 판정 칸 안 「조건 갖춤/못 갖춤」「해당함/해당 안 함」 단추(qAns, 화면 안에서만 기억)로 사람이 고르면 다시 판정.
  걸침 면적: zoneShares(필지 안 70×70 격자점 × LT_C_UQ111 경계) → 제84조 가중 건폐율·용적률(rule.mixed), 필지 안 주거지역이 100㎡ 이하면 「경계 어긋남 조각일 수 있음」 안내를 단추 옆에. 검토가 끝나면 「판정 근거」 칸을 빨갛게 5번 깜빡이고 「👇 여기를 꼭 확인하세요」(6초).
- 3D 보기(2026-11-22): 지도 오른쪽 위 빨간 「🏢 3D로 보기」 단추(아래 줄에 두면 칸 밖으로 밀려 안 보였음) → `open3D`(MapLibre 4.7.1, `web/vendor/maplibre`, 처음 누를 때만 불러옴). 브이월드 LT_C_SPBD(도로명주소 건물, 250m, size 1000) 지상층수(gro_flo_co 추정 — 실제 속성명 미확인, 없으면 1층으로 표시하고 경고) × 3.3m로 세움, 검토 필지 건물은 빨강·건축물대장 높이(heit). 배경은 브이월드 Base 타일(안 되면 OSM). #stage 밖 body에 붙임(확대·축소 때문에).
  CAD 도면: 3D 창 「📐 CAD 도면 올리기(DXF)」 → `vendor/dxf/dxf-parser.js`(MIT)로 브라우저 안에서만 읽음(서버 저장 안 함). 닫힌 폴리라인 큰 순 12개 중 외곽선 고르기, 단위 $INSUNITS(없으면 크기로 mm/m 추정), 층수·층고·회전·동서/남북 이동 → 파란 건물로 세우고 건축면적·연면적(예상치)·건폐율·용적률(조례 한도 비교, 걸침이면 가중값)·대지 경계 안 여부 표시. 도면 건물이 있으면 기존 빨간 건물은 숨김. DWG는 DXF로 저장해서 올려야 함.
- 조례 비교: `collect/landlaw.py`가 18개 시·군 도시계획(군계획) 조례에서 용도지역별 건폐율·용적률 추출(주 1회, LAW_OC). 일부 시·군은 조문 형식이 달라 몇 개 용도지역 값이 빠짐(원주·홍천·화천·인제 상업지역 용적률 등) → 빠진 곳은 비교에서 제외(추정 안 함).
- Edge Function 배포: `supabase/functions/**` 고치고 push하면 deploy_functions.yml이 자동 배포.
- 참고 코드: chrisryugj/archhub-mcp, korean-law-mcp (MIT). 다음 할 일: 국토·건축 현황 통계(노후·내진 미적용 추정·인허가, 18개 시·군 비교).

## AI 비서실장 이정후(화면 길잡이, 2026-11-22) — `web/guide.js` (화면 이름 표시: 「AI 비서실장 이정후」)
- 사용자 요청: AI 없이 「어디를 보세요」 정도만. 오른쪽 아래 비서실장 전신(150px)+말풍선 「저를 누르시면 원하시는 화면으로 모시겠습니다」(처음 6초만, 마우스 올리면 다시 — 사용자가 계속 떠 있으면 거슬린다 함) → 가운데 대화창(바깥 누르면 닫힘, 바로 가기 누르면 닫힘)(낱말 찾기 표 G → 메뉴·아래 탭 바로 가기). 숫자는 말하지 않음. 흘러가기(#flow 화면·#flowBadge 있을 때)·액자에서는 단추 숨김. 한눈에 보기에서는 오른쪽 아래 「판정 제외」 칸 대신 비서실장 칸(aidePanel, 누르면 대화창)이 있어 떠 있는 캐릭터는 숨김. 로그인 뒤 startApp 다음에 불러옴.
- 화면(메뉴+아래 탭)이 바뀔 때마다 말풍선 8초 — **시·군을 눌러 바꿀 수 있는 화면에서만**(rankList·colChart가 시·군 항목에 `data-reg="1"`, guide.js가 #view MutationObserver로 확인; 사용자: 인구는 「인구 비교」에서만). 문구(2026-11-23): 「왼쪽 순위표·막대의 시·군 이름을 누르면 그 시·군 자료 · 다시 누르면 동해시 · 제목 옆 둥근 단추로 세부 화면」, 토지 탭은 주소 넣고 검토·조례 비교 안내(guide.js TIP/TIP0, tabTip).
- 대화창을 열어도 터치 화면에서는 입력칸 자동 포커스 안 함(키보드가 바로 올라와서, 2026-11-23). 마우스만 있는 PC·TV만 자동 포커스.
- 캐릭터: 시장님 캐릭터(.blend, 블렌더 MCP로 사용자가 만듦)를 바탕으로 둥근 갈색 안경·정장·목걸이 공무원증, 주름 뺌(머리는 시장님 머리 그대로 — 새 머리는 사용자가 어색하다 함).
  그림 `web/img/aide.webp`(전신, 투명), `aide_face.webp`(버튼). 원본 .blend는 사용자에게 보냄(저장소에는 없음).

## 농업 및 수산 탭(2026-11-22) — `collect/agri.py`, index.html `screenAgriTabs`(아래 탭 농업/수산)
- KOSIS(KOSIS_KEY): 2025 농림어업총조사 확정(5년 주기 → prdSe **F**) DT_1AG25102(전·겸업 농가, B=계 / 경영주 연령), DT_1AG25501(가축), DT_1AG25411(과수), DT_1FS25103(해수면 어가), DT_1FS25113(어법), DT_1FS25115(어획 품종), DT_1FS25120(어선);
  해마다: DT_1EA1011(시군 농가·농가인구, 2024까지), DT_1EB002(시군 논밭 경지면적, 2025까지), DT_1YL20121(친환경 인증, 2025까지). 주 1회(stale 'agri' 7). 지표 ag_farms·ag_land·ag_old·ag_eco·fs_hh(dir 0).
- 사용자 요청: 최신 자료를 앞에, 18개 시·군 비교는 뒤(인구처럼). 아래 탭: 수협 위판 · 최신 → 농업 현황 → 수산 현황 → 비교 · 18개 시·군(screenAgriCmp).
- 수협 위판 `collect/wipan.py`: 공공데이터포털 15102792(활용신청 완료 2026-11-22, DATA_GO_KR_KEY) odcloud 달별 파일(swagger infuser.odcloud.kr/oas/docs?namespace=15102792/v1 제목 끝 날짜로 달 찾음),
  cond[산지조합코드::GTE]=305·LTE=312 = 강원 8개 수협(305 강원고성 306 동해시 307 삼척 308 속초 309 양양 310 대포 311 강릉시 312 원덕). 동해 25개월(어종·일별), 나머지 13개월. 지난 달 캐시, 한 번 6분. 위판장명 「동해 위판장」은 경남고성 수협이라 쓰지 않음.
- 농진청 병해충 예찰 `collect/ncpms.py`(GitHub Secret NCPMS_KEY, ncpms.rda.go.kr/npmsAPI/service, serviceType AA003, SVC51 회차 → SVC53 sidoCode=42 강원). **동해는 예찰 조사 지역이 아님** → 이웃 강릉(4215)·삼척(4223) 값을 「농업 현황」 왼쪽 위 칸에(동해 자료 아님 표시). 전국 예측 경보(SVC31)는 위험 단계 뜻이 확인 안 돼 안 씀.
- 15개 탭이라 위쪽 줄 메뉴 글자 14.5px·간격 좁힘, 「최종 갱신」은 두 줄.

## 국내 중계(2026-11-22) — `supabase/functions/kr`
- 해외(GitHub 서버) 접속이 막힌 국내 사이트를 Supabase 함수가 서울 지역(`x-region: ap-northeast-2`)에서 대신 부름. 서비스 키(SUPABASE_SERVICE_KEY)만 허용, 허용 주소만(lofin365 hub·portal 안내 화면·resources/js·데이터셋 안내 POST). `common.kr_get`, settings 소스에 `kr_relay: true`면 바로 해 보고 실패 시 중계.
- 지방재정365(재정자립도 당초 DCFCE·최종 JFIED, 예산 규모): **fyr(회계연도) 필수** → 해마다 따로 받음(당초 내년~2년 전, 최종 올해~2년 전), 못 받은 해만 manual/lofin_*.json. LOFIN_KEY 없으면 LOFIN_KEY_FINAL 사용(key_env_alt). 점검: `probe.yml -f only=lofin`.
- 회계별 세입예산: 지방재정365 hub **ARBGT**(fyr 필수, pfa_amt1 세입총계·2 일반·3 공기업특별·4 기타특별·5 기금, 원 → 백만원) 자동(내년~작년), manual/budget_accounts_*.json은 못 받은 해 대비용.
- 다른 지방재정365 API 찾는 법: data.go.kr 「지방재정365_○○」 페이지 「바로가기」 → pdtaId → 중계로 POST `/lf/pfinDtaOpen/dtst/dtstSvi/retvDtstDtsApi.do`(pdtaId) → 요청주소 hub 코드·인자·출력 항목이 나옴(probe `lofinlist` 참고).

## 시내버스 운수회사(2026-11-23)
- 전국버스업체표준데이터 `api.data.go.kr/openapi/tn_pubr_public_bus_corp_api`(활용신청 완료, DATA_GO_KR_KEY, 응답이 response 없이 {header, body:{items:{item}}}) → `tour.bus_corp` → L['buscorp'](주 1회). 시·군이 직접 올린 곳만(2026-11 강원 5곳: 동해·춘천·강릉·양양·철원). 동해: 강원여객 동해영업소 19대·동해상사고속 동해영업소 18대(시내+마을), 전세 3곳 69대, 2025-12-04 기준.
- 18개 시·군 모두: KOSIS 강원 기본통계 「업종별 운수업체」(211 DT_211002_J004, 2024까지, 시내·마을·시외·전세버스·택시 업체수·대수) → `tour.bus_firms` → L['busfirm'](주 1회). 군 지역 농어촌버스는 이 표에 없음 → 시·군 기본통계 표(SGG_TBL)에서 「농어촌버스」 있는 곳만(2026-11: 평창 2024·인제·양구 2023), 연도 표시. 카드·「버스·택시 운수업체」 표(표준데이터 없는 시·군)·18개 시·군 막대.
- 화면: 교통 › 시내버스 카드 「시내·마을버스 ○대」 + 「운수회사」 표(자료 없는 시·군은 정류장 순위). 사용자 결정: 공영제·민영제·준공영제는 공개 자료가 없어 **표시하지 않음**.

## 남은 일
- **전력 탭(「에너지·전력」) — 2026-11-21 만듦**: `collect/power.py`(한전 `KEPCO_KEY`, metroCd 51).
  계약종별·가구평균은 시·군 월별 25개월 보관(지난 달은 다시 안 받음), 산업분류는 최신 달만. 지표 pw_total·pw_house·pw_house_bill·pw_yoy·pw_ind_share(모두 dir 0).
  한전 서버가 자주 끊김(TLS timeout) → 한 번에 7분까지만 받고 나머지 달은 다음 실행에서 채움. 신재생(`renewEnergy.do`)은 아직 응답 못 받음 → 되면 추가.
  `gh workflow run probe.yml -f only=kepco`로 한전만 빠르게 점검 가능.
- **전자파(전파진흥원)**: `B552729/kcaApiService_emf/getEmfExposureIndex`, `B552729/KCCEWISLE/{bemf,meas,movebemf,fixbemf}` —
  신청은 승인됐으나 기관 서버가 504(연결실패). 살아나면 환경 탭에 추가.
- 쓰레기(폐기물) 2026년 자료는 공개 API 없음 → 동해시 자원순환 부서 월별 자료를 받으면 붙이기.
- 상수도 2025년 통계는 2027년 1월 공표 예정(자동 반영).
