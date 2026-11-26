/* AI 비서실장 — 화면 길잡이(2026-11-22)
 * AI 없이 낱말로 찾아 「어디를 보세요」 + 바로 가기. 숫자는 말하지 않고 화면으로 안내만 함.
 */
(function () {
  var G = [
    { m: 'main', t: '한눈에 보기', k: ['한눈', '요약', '전체', '순위', '종합', '현황판', '처음'], say: '동해시가 18개 시·군 중 어디쯤인지 한 화면에 모아 둔 곳입니다.' },
    { m: 'admin', s: '인구 현황', t: '행정 › 인구 현황', k: ['인구', '세대', '주민', '고령', '노령', '출생', '사망', '전입', '전출', '남녀', '생산연령'], say: '동해시 인구·세대·고령 비율과 지난달 대비 증감을 볼 수 있습니다.' },
    { m: 'admin', s: '인구 비교', t: '행정 › 인구 비교', k: ['인구 비교', '시군 비교', '18개', '다른 시', '강릉', '삼척', '속초', '원주', '춘천'], say: '18개 시·군 인구를 나란히 비교한 화면입니다.' },
    { m: 'admin', s: '행정동', t: '행정 › 행정동 3D 지도', k: ['동별', '행정동', '동네', '천곡', '북삼', '묵호', '발한', '송정', '부곡', '3d'], say: '행정동별 인구를 3D 지도로 보여 줍니다.' },
    { m: 'economy', s: '사업자', t: '경제 › 사업자 · 고용', k: ['경제', '사업자', '고용', '일자리', '취업', '실업', '고용률'], say: '사업자 수와 고용률 흐름을 볼 수 있습니다.' },
    { m: 'economy', s: '상가', t: '경제 › 상가 신규·폐업', k: ['상가', '폐업', '창업', '가게', '점포', '자영업'], say: '상가 신규·폐업을 18개 시·군과 비교합니다.' },
    { m: 'economy', s: '음식점', t: '경제 › 음식점·숙박 개업·폐업', k: ['음식점', '식당', '숙박', '모텔', '호텔', '펜션', '개업'], say: '음식점·숙박업 개업과 폐업을 월별로 봅니다.' },
    { m: 'economy', s: '아파트', t: '경제 › 아파트 거래', k: ['아파트', '집값', '부동산', '실거래', '매매', '아파트 가격', '평당', '시세', '거래량'], say: '18개 시·군 아파트 매매 건수와 평당 가격, 동해시 최근 거래를 봅니다.' },
    { m: 'agri', s: '수협 위판', t: '농업 및 수산 › 수협 위판', k: ['위판', '수협', '어획량', '수산물', '오징어', '붉은대게', '대게', '문어', '생선', '경매'], say: '동해시수협 등 강원 8개 수협의 이번 달 위판 금액·물량과 어종별 실적을 볼 수 있습니다.' },
    { m: 'agri', s: '농업 현황', t: '농업 및 수산 › 농업', k: ['농업', '농가', '농민', '경지', '논', '밭', '과수', '사과', '가축', '한우', '친환경', '귀농', '농사'], say: '농가 수·경지면적·고령 경영주·과수·가축을 18개 시·군과 비교해 볼 수 있습니다.' },
    { m: 'agri', s: '수산 현황', t: '농업 및 수산 › 수산', k: ['수산', '어업', '어가', '어민', '어선', '어촌', '물고기', '바다', '고기잡이', '어획'], say: '해수면 어가·어법·잡는 품종·어선 보유를 볼 수 있습니다.' },
    { m: 'port', t: '항만', k: ['항만', '항구', '동해항', '묵호항', '동해.묵호', '물동량', '화물', '선박', '입항', '출항', '입출항', '연안화물', '부두', '해운', '물류', '석회석', '시멘트'], say: '동해·묵호항 입출항 선박과 연안화물을 달마다 보고 전국 항만과 견줍니다.' },
    { m: 'rail', t: '철도', k: ['철도', '기차', '열차', 'ktx', '케이티엑스', 'itx', '무궁화', '누리로', '동해역', '묵호역', '망상해변역', '추암역', '시간표', '정차', '다음 열차', '강릉역'], say: '동해역·묵호역 오늘 시간표와 다음 열차, 강원 역별 정차 열차 수(승객 수 아님)를 봅니다.' },
    { m: 'welfare', t: '보건 및 의료', k: ['병원', '의원', '의사', '의료', '약국', '보건', '응급', '진료'], say: '의료기관 수, 인구 1천 명당 의사 수 등을 볼 수 있습니다.' },
    { m: 'social', t: '복지', k: ['복지', '수급', '기초생활', '장애', '노인', '어르신', '아동', '보육'], say: '수급자·장애인 등 복지 통계를 모아 둔 곳입니다.' },
    { m: 'tour', s: '방문', t: '관광 › 방문 현황', k: ['관광', '관광객', '방문객', '입장객', '여행'], say: '주요 관광지 입장객과 방문 흐름을 볼 수 있습니다.' },
    { m: 'tour', s: '혼잡', t: '관광 › 관광지 혼잡 예측', k: ['혼잡', '붐비', '사람 많', '예측'], say: '관광지별 혼잡 예상치를 보여 줍니다.' },
    { m: 'tour', s: '행사', t: '관광 › 행사·축제', k: ['축제', '행사', '이벤트', '공연'], say: '행사·축제 일정과 정보를 볼 수 있습니다.' },
    { m: 'finance', t: '예산', k: ['예산', '재정', '세입', '세출', '지방세', '살림', '돈'], say: '동해시 예산 규모와 쓰임새, 18개 시·군 비교가 있습니다.' },
    { m: 'land', s: '부지 검토', t: '토지 및 건축 › 부지 검토', k: ['토지', '부지', '땅', '지번', '건축', '건물', '용도지역', '건폐율', '용적률', '맹지', '상수원', '건축물대장'], say: '지번을 넣으면 신호등 판정과 근거 조문, 지도 레이어를 보여 줍니다.' },
    { m: 'land', s: '부지 검토', t: '토지 및 건축 › 3D 보기 · CAD 도면 올리기', k: ['3D', '3d', '입체', '도면', 'CAD', 'cad', 'DXF', 'dxf', '캐드', '설계', '매스'], say: '지번을 검토한 뒤 지도 오른쪽 위 「🏢 3D로 보기」를 누르시고, 3D 창에서 「📐 CAD 도면 올리기(DXF)」로 도면을 올리시면 필지 위에 건물을 세워 건폐율·용적률을 보여 드립니다.' },
    { m: 'land', s: '조례 비교', t: '토지 및 건축 › 조례 비교', k: ['조례', '조례 비교', '도시계획 조례'], say: '18개 시·군 도시계획 조례의 건폐율·용적률을 비교합니다.' },
    { m: 'traffic', s: '자동차', t: '교통 › 자동차 등록', k: ['교통', '자동차', '차량', '등록 대수'], say: '자동차 등록 현황을 볼 수 있습니다.' },
    { m: 'traffic', s: '버스', t: '교통 › 시내버스', k: ['버스', '시내버스', '정류장', '노선'], say: '시내버스 현황과 실시간 버스 위치를 볼 수 있습니다.' },
    { m: 'traffic', s: '택시', t: '교통 › 택시', k: ['택시'], say: '택시 현황을 볼 수 있습니다.' },
    { m: 'traffic', s: '전기차', t: '교통 › 전기차 충전', k: ['전기차', '충전소', '충전기'], say: '전기차 충전 시설 현황입니다.' },
    { m: 'traffic', s: '주차', t: '교통 › 공영주차장', k: ['주차', '주차장'], say: '공영주차장 현황입니다.' },
    { m: 'traffic', s: '교통안전', t: '교통 › 교통안전·도로', k: ['교통사고', '사고', '교통안전', '도로'], say: '교통사고·교통안전 지표를 볼 수 있습니다.' },
    { m: 'env', s: '날씨', t: '환경 › 지금 날씨·대기', k: ['날씨', '기온', '비', '눈', '바람', '미세먼지', '초미세', '공기', '대기'], say: '지금 날씨와 미세먼지를 볼 수 있습니다.' },
    { m: 'env', s: '올해 기상', t: '환경 › 올해 기상', k: ['기상', '강수량', '폭염', '한파'], say: '올해 기상 기록을 정리해 두었습니다.' },
    { m: 'env', s: '수질', t: '환경 › 하천 수질', k: ['수질', '하천', '전천', '오염'], say: '하천 수질 측정값을 볼 수 있습니다.' },
    { m: 'admin', s: '출생·사망', t: '행정 › 출생·사망 월별', k: ['출생', '출산', '신생아', '사망 신고', '자연증감', '월별 사망', '월별 출생', '태어', '저출생'], say: '이번 달과 올해 누계 출생·사망 신고, 18개 시·군 자연증감 순위를 봅니다.' },
    { m: 'welfare', s: '사망 분석', t: '보건 및 의료 › 사망 분석', k: ['사망', '사망률', '사망자', '사망원인', '죽음', '암 사망', '연령표준화', '조사망률', '심장 질환', '뇌혈관', '폐렴', '자살', '사인'], say: '동해시 사망자 수·사망률·사망원인 순위와 강원 시·군 비교를 봅니다.' },
    { m: 'water', s: '수돗물 수질검사', t: '더보기 › 상하수도 › 수돗물 수질검사', k: ['수질', '수돗물', '수질검사', '잔류염소', '탁도', '경도', '정수장', '사문', '쇄운', '이원', '먹는물', '대장균', '더보기'], say: '동해시 정수장 법정 수질검사 결과와 18개 시·군 비교를 봅니다. 메뉴 줄 맨 끝 「더보기」 안에 있습니다.' },
    { m: 'water', s: '요금', t: '더보기 › 상하수도 › 요금', k: ['수도요금', '물값', '상수도 요금', '하수도 요금', '하수도 사용료', '정액요금', '요금 인상', '요금표'], say: '동해시 상·하수도 요금표와 한 달 15톤 예시를 봅니다.' },
    { m: 'water', s: '상하수도 통계', t: '더보기 › 상하수도 › 통계', k: ['상수도', '하수도', '급수', '누수', '상하수', '보급률', '하수처리'], say: '상·하수도 보급률 등 18개 시·군 통계를 봅니다.' },
    { m: 'power', t: '에너지·전력', k: ['전기', '전력', '에너지', '전기요금', '전력 사용'], say: '전력 사용량과 가구 평균 전기요금을 볼 수 있습니다.' },
    { m: 'flow', t: '흘러가기', k: ['흘러가기', '자동', '슬라이드', '돌려', '자동으로'], say: '보고 싶은 화면을 골라 자동으로 넘겨 보는 곳입니다.' },
    { href: 'admin.html', t: '관리자 화면', k: ['관리자', '입력', '가입', '비밀번호', '계정', '로그인', '승인'], say: '자료 입력과 계정 관리는 관리자 화면에서 합니다.' }
  ];
  var QUICK = ['인구는 어디서 봐요?', '예산', '부지 검토', '관광객', '미세먼지', '병원'];

  function norm(t) { return String(t || '').toLowerCase().replace(/\s+/g, ' ').trim(); }
  function find(q) {
    var n = norm(q), sc = [];
    if (!n) return [];
    G.forEach(function (g, i) {
      var s = 0;
      g.k.forEach(function (k) { if (n.indexOf(k) >= 0) s += 10 + k.length; });
      if (g.t && n.indexOf(norm(g.t).split(' ›')[0]) >= 0) s += 3;
      if (s) sc.push({ g: g, s: s, i: i });
    });
    sc.sort(function (a, b) { return b.s - a.s || a.i - b.i; });
    return sc.map(function (x) { return x.g; });
  }
  function allowed(g) {   // 지금 화면에 실제로 있는 메뉴만(자료 없어 숨긴 메뉴 제외)
    if (g.href) return true;
    return !!document.querySelector('#nav [data-id="' + g.m + '"], #nav [data-k="' + g.m + '"]') || menuIds().indexOf(g.m) >= 0;
  }
  function menuIds() { try { return ((window.DONGHAE_DATA || {}).menu || []).map(function (m) { return m.id; }); } catch (e) { return []; } }

  function goTo(g) {
    root.classList.remove('open');
    if (g.href) { location.href = g.href; return; }
    if (location.hash === '#' + g.m) window.dispatchEvent(new HashChangeEvent('hashchange'));
    else location.hash = g.m;
    if (!g.s) return;
    var tries = 0;
    (function pick() {
      var bs = Array.prototype.slice.call(document.querySelectorAll('#view .title .subtabs button, #view .title [data-subtab]'));
      var b = bs.filter(function (x) { return (x.textContent || '').indexOf(g.s) >= 0; })[0];
      if (b) { if (!/\bon\b/.test(b.className)) b.click(); return; }
      if (++tries < 15) setTimeout(pick, 120);
    })();
  }

  // ---------- 화면 ----------
  var css = document.createElement('style');
  css.textContent =
    '#dhAideBtn{position:fixed;right:10px;bottom:4px;z-index:850;display:flex;align-items:flex-end;gap:2px;border:0;background:none;padding:0;cursor:pointer;font-family:inherit}' +
    '#dhAideBtn img{height:150px;display:block;filter:drop-shadow(0 6px 10px rgba(27,58,107,.25));animation:dhBob 3.2s ease-in-out infinite}' +
    '#dhAideBtn .say{position:relative;margin-bottom:80px;background:#fff;border:1.5px solid #C9D8EE;border-radius:16px;padding:9px 14px;text-align:left;box-shadow:0 6px 18px rgba(27,58,107,.18);white-space:nowrap;transition:opacity .4s}' +
    '#dhAideBtn .say:after{content:"";position:absolute;right:-8px;bottom:14px;border:8px solid transparent;border-left-color:#fff;border-right:0}' +
    '#dhAideBtn .say b{display:block;font-size:13px;color:#2F6DB5;letter-spacing:.5px}' +
    '#dhAideBtn .say span{font-size:15px;font-weight:700;color:#1B3A6B;line-height:1.45}#dhAideBtn .say u{text-decoration:none;color:#D9443F}' +
    '#dhAideBtn{pointer-events:none}#dhAideBtn img{pointer-events:auto}' +
    '@media (max-height:600px){#dhAideBtn img{height:84px}#dhAideBtn .say{margin-bottom:40px}}' +
    '#dhAideBtn .say{opacity:0;pointer-events:none}#dhAideBtn.talk .say,#dhAideBtn:hover .say{opacity:1}#dhAideBtn:hover .say{border-color:#2F6DB5}body.dh-noaide #dhAideBtn{display:none}body:not(.dh-noaide) .help{right:100px!important}' +
    '#dhAide{position:fixed;inset:0;z-index:900;display:none;align-items:center;justify-content:center;background:rgba(20,35,60,.35);font-family:"Pretendard","Malgun Gothic",system-ui,sans-serif}' +
    '#dhAide.open{display:flex}' +
    '#dhAide .box{width:760px;max-width:94vw;height:620px;max-height:88vh;background:#fff;border-radius:22px;box-shadow:0 18px 60px rgba(27,58,107,.35);display:flex;overflow:hidden}' +
    '#dhAide .pic{width:230px;flex:none;background:linear-gradient(180deg,#E4EEFB,#F4F7FC);display:flex;align-items:flex-end;justify-content:center;padding-bottom:14px}' +
    '#dhAide .pic img{width:205px;animation:dhBob 3.2s ease-in-out infinite}' +
    '#dhAide .main{flex:1;display:flex;flex-direction:column;min-width:0}' +
    '#dhAide .hd{display:flex;align-items:center;justify-content:space-between;padding:16px 18px 10px;border-bottom:1px solid #E3E9F2}' +
    '#dhAide .hd b{font-size:22px;color:#1B3A6B}#dhAide .hd small{display:block;font-size:13px;color:#6B7686;font-weight:600}' +
    '#dhAide .x{border:0;background:#EEF3F8;color:#38475A;width:36px;height:36px;border-radius:50%;font-size:18px;cursor:pointer}' +
    '#dhAide .log{flex:1;overflow:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px}' +
    '#dhAide .me{align-self:flex-end;background:#1B3A6B;color:#fff;padding:8px 13px;border-radius:14px 14px 4px 14px;font-size:16px;max-width:85%}' +
    '#dhAide .bot{align-self:flex-start;background:#F1F5FB;color:#22324A;padding:10px 13px;border-radius:14px 14px 14px 4px;font-size:16px;line-height:1.5;max-width:92%}' +
    '#dhAide .bot b{color:#1B3A6B}#dhAide .go{display:inline-block;margin-top:7px;border:0;background:#2F6DB5;color:#fff;font:inherit;font-size:15px;font-weight:800;padding:6px 14px;border-radius:999px;cursor:pointer}' +
    '#dhAide .alt{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}#dhAide .alt button,#dhAide .qk button{border:1px solid #C9D8EE;background:#fff;color:#1B3A6B;font:inherit;font-size:14px;font-weight:700;padding:5px 11px;border-radius:999px;cursor:pointer}' +
    '#dhAide .qk{display:flex;flex-wrap:wrap;gap:6px;padding:8px 16px;border-top:1px solid #EEF2F7}' +
    '#dhAide form{display:flex;gap:8px;padding:8px 16px 16px}' +
    '#dhAide input{flex:1;min-width:0;font:inherit;font-size:17px;padding:10px 12px;border:2px solid #C9D2DE;border-radius:12px}' +
    '#dhAide form button{border:0;background:#1B3A6B;color:#fff;font:inherit;font-size:17px;font-weight:800;padding:0 18px;border-radius:12px;cursor:pointer}' +
    '@keyframes dhBob{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}';
  document.head.appendChild(css);

  // 오른쪽 아래에 비서실장(전신) + 말풍선 → 누르면 가운데에 대화창
  var btn = document.createElement('button');
  btn.id = 'dhAideBtn'; btn.type = 'button'; btn.setAttribute('aria-label', 'AI 비서실장 열기');
  btn.innerHTML = '<div class="say"><b>AI 비서실장 이정후</b><span>저를 누르시면 원하시는 화면으로 모시겠습니다</span></div><img src="img/aide.webp" alt="">';
  var root = document.createElement('div');
  root.id = 'dhAide';
  root.innerHTML =
    '<div class="box"><div class="pic"><img src="img/aide.webp" alt="AI 비서실장"></div><div class="main">' +
    '<div class="hd"><div><b>AI 비서실장 이정후</b><small>궁금한 내용을 말씀하시면 볼 화면을 알려 드립니다</small></div><button class="x" type="button" aria-label="닫기">✕</button></div>' +
    '<div class="log"></div><div class="qk"></div>' +
    '<form><input placeholder="예: 인구는 어디서 봐요?" autocomplete="off"><button type="submit">묻기</button></form></div></div>';
  function mount() {
    if (!document.body.contains(btn)) document.body.appendChild(btn);
    if (!document.body.contains(root)) document.body.appendChild(root);
  }
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
  var log = root.querySelector('.log'), inp = root.querySelector('input');
  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function bubble(cls, html) { var d = document.createElement('div'); d.className = cls; d.innerHTML = html; log.appendChild(d); log.scrollTop = log.scrollHeight; return d; }
  function answer(q) {
    bubble('me', esc(q));
    var hits = find(q).filter(allowed);
    if (!hits.length) {
      var d = bubble('bot', '죄송합니다, 어느 화면인지 찾지 못했습니다. 아래 메뉴에서 골라 보세요.<div class="alt"></div>');
      var alt = d.querySelector('.alt');
      G.filter(function (g) { return !g.s && allowed(g); }).forEach(function (g) { var b = document.createElement('button'); b.type = 'button'; b.textContent = g.t; b.onclick = function () { goTo(g); }; alt.appendChild(b); });
      return;
    }
    var g = hits[0], d2 = bubble('bot', '<b>「' + esc(g.t) + '」</b>을(를) 보세요. ' + esc(g.say) + '<br><button class="go" type="button">바로 가기 →</button>' + (hits.length > 1 ? '<div class="alt"></div>' : ''));
    d2.querySelector('.go').onclick = function () { goTo(g); };
    if (hits.length > 1) {
      var a = d2.querySelector('.alt');
      hits.slice(1, 4).forEach(function (h) { var b = document.createElement('button'); b.type = 'button'; b.textContent = h.t; b.onclick = function () { goTo(h); }; a.appendChild(b); });
    }
  }
  var qk = root.querySelector('.qk');
  QUICK.forEach(function (q) { var b = document.createElement('button'); b.type = 'button'; b.textContent = q; b.onclick = function () { answer(q); }; qk.appendChild(b); });
  function open() {
    root.classList.add('open');
    if (!log.children.length) bubble('bot', '안녕하세요, <b>AI 비서실장 이정후</b>입니다. 무엇이 궁금하세요? 보실 화면을 찾아 바로 열어 드릴게요.');
    // 터치 화면(태블릿·휴대폰)은 입력칸을 눌러야 키보드가 올라오게 — 마우스만 있는 PC·TV에서만 바로 입력
    if (window.matchMedia && matchMedia('(pointer: fine)').matches && !('ontouchstart' in window) && !(navigator.maxTouchPoints > 0)) setTimeout(function () { try { inp.focus(); } catch (e) {} }, 50);
  }
  function close() { root.classList.remove('open'); }
  btn.onclick = open;
  root.addEventListener('click', function (e) { if (e.target === root) close(); });
  root.querySelector('.x').onclick = close;
  root.querySelector('form').onsubmit = function (e) { e.preventDefault(); var q = inp.value.trim(); if (!q) return; inp.value = ''; answer(q); };
  root.addEventListener('keydown', function (e) { e.stopPropagation(); if (e.key === 'Escape') close(); });
  // 흘러가기(돌고 있을 때·설정 화면)와 액자 화면에서는 숨김
  function sync() {
    if (!document.body) return;
    var hide = location.hash === '#frame' || location.hash === '#flow' || !!document.getElementById('flowBadge');
    var onMain = !location.hash || location.hash === '#main';   // 한눈에 보기에는 칸 안에 비서실장이 있음
    document.body.classList.toggle('dh-noaide', hide || onMain);
    if (hide) close();
    mount();
  }
  // 말풍선: 처음 6초 + 탭을 옮길 때마다 8초 동안 「다른 시·군 보는 법」 안내(마우스를 올리면 기본 문구)
  var say = btn.querySelector('.say span'), SAY0 = say.innerHTML, talkT = null, lastTab = null;
  var TIP = {
    land: '위쪽 칸에 <u>지번·도로명 주소</u>를 넣고 검토를 누르세요<br>아래 탭에서 18개 시·군 조례도 비교하실 수 있습니다'
  };
  var TIP0 = '<u>왼쪽 순위표·막대의 시·군 이름</u>을 누르시면 그 시·군 자료로 바뀝니다<br>한 번 더 누르시면 동해시로 돌아옵니다 · 제목 옆 둥근 단추로 세부 화면 이동';
  function talk(html, ms) {
    say.innerHTML = html; btn.classList.add('talk');
    clearTimeout(talkT); talkT = setTimeout(function () { btn.classList.remove('talk'); setTimeout(function () { say.innerHTML = SAY0; }, 450); }, ms);
  }
  // 화면(메뉴 + 아래 탭)이 바뀔 때마다: 시·군을 눌러 바꿀 수 있는 화면(data-reg="1")에서만 안내
  function tabTip() {
    var t = (location.hash || '#main').slice(1), v = document.getElementById('view');
    var sub = v && v.querySelector('.title .subtabs button.on, .title [data-subtab].on');
    var key = t + '|' + (sub ? sub.textContent.trim() : '');
    if (key === lastTab) return;
    var first = lastTab === null || Date.now() - T0 < 2000; lastTab = key;
    if (first || document.body.classList.contains('dh-noaide')) return;
    if (t === 'land') { if (/부지/.test(key)) talk(TIP.land, 8000); return; }
    if (v && v.querySelector('[data-reg="1"]')) talk(TIP0, 8000);
    else if (btn.classList.contains('talk') && say.innerHTML !== SAY0) { clearTimeout(talkT); btn.classList.remove('talk'); setTimeout(function () { say.innerHTML = SAY0; }, 450); }
  }
  var tipT = null, T0 = Date.now();
  function watchView() {
    var v = document.getElementById('view');
    if (!v || v._dhTip) return;
    v._dhTip = 1;
    new MutationObserver(function () { clearTimeout(tipT); tipT = setTimeout(tabTip, 250); }).observe(v, { childList: true });
  }
  btn.addEventListener('mouseenter', function () { if (!btn.classList.contains('talk')) say.innerHTML = SAY0; });
  talk(SAY0, 6000);
  window.addEventListener('hashchange', sync); setInterval(function () { sync(); watchView(); }, 700); setTimeout(function () { sync(); watchView(); tabTip(); }, 0);
  window.DHAide = { open: open, close: close, ask: answer };
})();
