/* 동해시 AI 시장실 · 국토·건축 탭
 * - 부지 검토(로그인 없이): 지번·주소 → 브이월드(토지이용계획·토지특성·토지대장) + 건축물대장(Supabase 중계)
 *   → 신호등 판정(초록·노랑·빨강) + 쉬운 설명 + 근거 조문 + 원본 바로가기 + 1장 브리핑
 * - 조례 비교(공개): 강원 18개 시·군 도시계획 조례의 용도지역별 건폐율·용적률
 * 판정 규칙은 참고자료 「지휘부 의사결정 신호등 판정 엔진」을 동해시 조례 원문 수치로 바꿔 구현.
 * 건축물대장·조례 조회 방식 참고: chrisryugj/archhub-mcp, chrisryugj/korean-law-mcp (MIT License)
 */
window.DHLand = (function () {
  var H = null;            // index.html이 넘겨주는 도구(el, panel, view, render, D ...)
  var sb = null, session = null, profile = null, authChecked = false;
  var qAns = {}, tab = 'site', cur = null, busy = false, cmpZone = null, cmpKind = 'far', useSel = '', useSub = '', inArea = null, inFloor = null, inRoad = null;
  var LV = { GREEN: { c: '#2E8B57', bg: '#E2F3E9', t: '추진 가능' }, YELLOW: { c: '#D99A00', bg: '#FFF4D6', t: '조건부 가능 · 검토 필요' }, RED: { c: '#D9534F', bg: '#FDE7E4', t: '추진 곤란 · 중대 제약' }, INFO: { c: '#1F6FD1', bg: '#E4EEFB', t: '참고' } };
  // 예정 용도 → 「건축법 시행령」 별표 1의 호 번호
  var USE_HO = { '단독주택': '1', '공동주택': '2', '제1종근린생활시설': '3', '제2종근린생활시설': '4', '문화및집회시설': '5', '종교시설': '6', '판매시설': '7', '운수시설': '8', '의료시설': '9', '교육연구시설': '10', '노유자시설': '11', '수련시설': '12', '운동시설': '13', '업무시설': '14', '숙박시설': '15', '위락시설': '16', '공장': '17', '창고시설': '18', '위험물저장및처리시설': '19', '자동차관련시설': '20', '주차장': '20', '동물및식물관련시설': '21', '자원순환관련시설': '22', '방송통신시설': '24', '발전시설': '25', '묘지관련시설': '26', '관광휴게시설': '27', '장례시설': '28', '야영장시설': '29' };
  var USES = [''].concat(Object.keys(USE_HO));
  // 세부 용도: 「건축법 시행령」 별표 1의 목(가·나·다…)과 찾을 낱말
  var SUBS = {
    '단독주택': [['단독주택', '가'], ['다중주택', '나'], ['다가구주택', '다'], ['공관', '라']],
    '공동주택': [['아파트', '가'], ['연립주택', '나'], ['다세대주택', '다'], ['기숙사', '라']],
    '제1종근린생활시설': [['소매점', '가'], ['휴게음식점·제과점', '나', ['휴게음식점', '제과점']], ['이용원·미용원·목욕장·세탁소', '다', ['이용원', '미용원', '목욕장', '세탁소']], ['의원·치과의원·한의원', '라', ['의원']], ['탁구장·체육도장', '마', ['탁구장', '체육도장']], ['지역자치센터·파출소 등 공공업무', '바'], ['마을회관·공중화장실 등', '사'], ['변전소·정수장 등', '아'], ['금융업소·사무소(30㎡ 미만)', '자', ['금융업소', '사무소']], ['전기자동차 충전소', '차', ['전기자동차']]],
    '제2종근린생활시설': [['공연장', '가'], ['종교집회장', '나'], ['자동차영업소', '다'], ['서점', '라'], ['총포판매소', '마'], ['사진관·표구점', '바', ['사진관', '표구점']], ['청소년게임·PC방 등', '사', ['게임', '복합유통게임']], ['휴게음식점·제과점', '아', ['휴게음식점', '제과점']], ['일반음식점', '자'], ['장의사·동물병원·동물미용실', '차', ['장의사', '동물병원', '동물미용']], ['학원·교습소·직업훈련소', '카', ['학원', '교습소', '직업훈련소']], ['독서실·기원', '타', ['독서실', '기원']], ['테니스장·체력단련장 등', '파', ['테니스장', '체력단련장', '골프연습장', '당구장']], ['금융업소·사무소·부동산중개사무소', '하', ['금융업소', '사무소', '부동산중개']], ['다중생활시설(고시원)', '거', ['다중생활시설', '고시원']], ['제조업소·수리점', '너', ['제조업소', '수리점']], ['단란주점', '더'], ['안마시술소·노래연습장', '러', ['안마시술소', '노래연습장']]],
    '문화및집회시설': [['공연장', '가'], ['집회장', '나'], ['관람장', '다'], ['전시장(박물관·미술관 등)', '라', ['전시장', '박물관', '미술관']], ['동·식물원', '마', ['동ㆍ식물원', '동·식물원', '식물원', '동물원']]],
    '판매시설': [['도매시장', '가'], ['소매시장', '나'], ['상점', '다']],
    '의료시설': [['병원', '가', ['병원']], ['격리병원', '나']],
    '교육연구시설': [['학교', '가', ['학교', '초등학교', '중학교', '고등학교']], ['교육원', '나'], ['직업훈련소', '다'], ['학원', '라'], ['연구소', '마'], ['도서관', '바']],
    '수련시설': [['청소년수련관 등', '가', ['생활권 수련시설', '청소년수련']], ['유스호스텔', '다']],
    '운동시설': [['체육관', '나'], ['운동장', '다'], ['골프연습장', '가']],
    '업무시설': [['공공업무시설', '가'], ['오피스텔', '나'], ['금융업소·사무소', '나', ['금융업소', '사무소']]],
    '숙박시설': [['일반숙박시설', '가'], ['생활숙박시설', '가'], ['관광숙박시설', '나'], ['다중생활시설', '다']],
    '위험물저장및처리시설': [['주유소', '가'], ['액화석유가스 충전소', '나', ['액화석유가스']], ['고압가스 충전소', '라', ['고압가스']], ['수소연료공급시설', '', ['수소']]],
    '자동차관련시설': [['주차장', '가'], ['세차장', '나'], ['폐차장', '다'], ['검사장', '라'], ['매매장', '마'], ['정비공장', '바'], ['운전학원·정비학원', '사', ['운전학원', '정비학원']], ['차고·주기장', '아', ['차고', '주기장']], ['전기자동차 충전소', '자', ['충전소']]],
    '동물및식물관련시설': [['축사', '가'], ['가축시설', '나'], ['도축장', '다'], ['도계장', '라'], ['작물 재배사', '마', ['재배사']], ['종묘배양시설', '바'], ['화초·분재 온실', '사', ['온실']]]
  };
  var MOK = '가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허';
  function nz(t) { return String(t || '').replace(/\s+/g, ''); }
  // 「같은 호 가목부터 라목까지」「나목 및 다목」「라목」 → 목 글자들
  function moks(t) {
    var r = [], re = /([가-힣])목\s*(?:부터|에서)\s*([가-힣])목/g, m;
    while ((m = re.exec(t))) { var i = MOK.indexOf(m[1]), j = MOK.indexOf(m[2]); if (i >= 0 && j >= i) r = r.concat(MOK.slice(i, j + 1).split('')); }
    (t.replace(re, '').match(/([가-힣])목/g) || []).forEach(function (x) { r.push(x[0]); });
    return r;
  }
  // 숫자 조건(바닥면적·도로 너비·층수)
  function numChecks(t, inp) {
    var out = [], m, re;
    re = /바닥면적의\s*합계가\s*([\d,.]+)\s*(만|천)?\s*제곱미터\s*(미만|이하|이상|초과)/g;
    while ((m = re.exec(t))) { var v = parseFloat(m[1].replace(/,/g, '')) * (m[2] === '만' ? 10000 : m[2] === '천' ? 1000 : 1); out.push({ k: 'area', v: v, op: m[3], txt: '바닥면적 ' + fmt(v) + '㎡ ' + m[3] }); }
    re = /너비\s*([\d.]+)\s*미터\s*이상의\s*도로/g;
    while ((m = re.exec(t))) out.push({ k: 'road', v: +m[1], op: '이상', txt: '도로 너비 ' + m[1] + 'm 이상' });
    re = /(\d+)\s*층\s*(이하|초과|미만)/g;
    while ((m = re.exec(t))) out.push({ k: 'floor', v: +m[1], op: m[2], txt: m[1] + '층 ' + m[2] });
    return out.map(function (c) {
      var x = inp[c.k], ok = null, how = '';
      if (c.k === 'road' && x == null && inp.roadRange) { var R = inp.roadRange; ok = R[0] >= c.v ? true : R[1] != null && R[1] <= c.v ? false : null; how = ' (도로접면 「' + inp.roadNm + '」 기준)'; }
      else if (x != null) { ok = c.op === '미만' ? x < c.v : c.op === '이하' ? x <= c.v : c.op === '이상' ? x >= c.v : x > c.v; how = ' (입력 ' + fmt(x) + ')'; }
      c.ok = ok; c.how = how; return c;
    });
  }
  // 「(아파트를 제외한다)」처럼 용도만 빼는 괄호(위치·거리 조건이 붙은 예외는 아님)
  function pureEx(x) { return /(을|를|은|는)\s*제외한다\s*[)\]]$/.test(x) && !/로서|따라|밖|거리|경우|지역에|대지에|해당하는/.test(x); }
  function useJudge(zoneNm, use, sub, inp) {
    var o = ordMe(), T = ((o && o.uses) || []).filter(function (u) { return u.zone === nz(zoneNm); })[0];
    if (!T) return null;
    var ho = USE_HO[use], S = sub && (SUBS[use] || []).filter(function (x) { return x[0] === sub; })[0];
    var kws = S ? (S[2] || [S[0]]) : use === '주차장' ? ['주차장'] : null;
    var hit = [], checks = [], exempt = false;
    T.items.forEach(function (it) {
      var full = it.t + ' ' + it.subs.join(' ');
      var mine = it.ho.indexOf(ho) >= 0 || (!it.ho.length && (use === '공장' && /공장/.test(it.t)));
      var all = !it.ho.length && /모든\s*건축물/.test(it.t);
      if (!mine && !all) return;
      var body = full.replace(/^「건축법 시행령」\s*별표\s*1?\s*제\d+호(의\d+)?의\s*/, '');
      if (mine && kws) {
        // 괄호 안 「…제외」에 세부 용도가 있으면 이 항목에서 빠짐
        var ex = (body.match(/[(\[][^()\[\]]*제외[^()\[\]]*[)\]]/g) || []).filter(pureEx).join(' ');
        if (kws.some(function (k) { return nz(ex).indexOf(nz(k)) >= 0; })) return;
        var lim = /\s중\s|\s중$|에\s*해당하는\s*것|같은\s*호\s*[가-힣]목/.test(body.replace(/[(\[][^()\[\]]*[)\]]/g, ''));
        if (lim) {
          var inName = kws.some(function (k) { return nz(body.replace(/[(\[][^()\[\]]*제외[^()\[\]]*[)\]]/g, function (x) { return pureEx(x) ? '' : x; })).indexOf(nz(k)) >= 0; });
          var inMok = S && S[1] && moks(body).indexOf(S[1]) >= 0;
          if (!inName && !inMok) return;
        }
      }
      var nc = all ? numChecks(it.t.replace(/을\s*초과하는/, ' 초과'), inp).map(function (x) { x.txt = '금지 조건 ' + x.txt; return x; }) : numChecks(body, inp);
      var rest = body.replace(/바닥면적의\s*합계가\s*[\d,.]+\s*(만|천)?\s*제곱미터\s*(미만|이하|이상|초과)인?\s*(것|경우)?/g, '').replace(/너비\s*[\d.]+\s*미터\s*이상의\s*도로에?\s*접한\s*대지에\s*건축하는\s*것에\s*한한다/g, '');
      rest = rest.replace(/[가-힣]+의\s*경우\s*(?=\))/g, '');
      if (kws) {
        rest = rest.replace(/[(\[][^()\[\]]*제외[^()\[\]]*[)\]]/g, function (x) { return pureEx(x) ? '' : x; });
        var seg = rest.split(/것과\s*/).filter(function (x) { return kws.some(function (k) { return nz(x).indexOf(nz(k)) >= 0; }); });
        if (seg.length) rest = seg[seg.length - 1];
      }
      var c = it.subs.length > 0 || /\s중\s|제외|한한다|한정|미만|이하|이상|다만|경우|기준에\s*해당|지역에\s*설치|별표\s*\d+\s*[가-힣]목/.test(rest);
      if (kws && !it.subs.length && /\s중\s/.test(rest) && !/제외|한한다|한정|미만|이하|이상|다만|경우|기준에\s*해당|지역에\s*설치|별표\s*\d+\s*[가-힣]목/.test(rest.split(/\s중\s/)[1] || '')) c = false;
      if (!all && nc.some(function (x) { return x.ok == null; })) c = true;
      // 「주거지역으로부터 5미터 밖」: 브이월드 용도지역 경계로 거리 계산(필지 경계 기준이라 건물은 이보다 멀거나 같음)
      if (c && /주거지역으로\s*부터\s*5\s*미터\s*밖|주택\s*밀집지역으로\s*부터\s*5\s*미터\s*밖/.test(full) && inp.resDist != null) {
        var mil = /주택\s*밀집/.test(full), okd = inp.resDist >= 5 && !mil;
        checks.push({ ok: mil ? (inp.resDist >= 5 ? true : false) : okd, txt: '가장 가까운 주거지역 경계까지 약 ' + fmt(Math.round(inp.resDist)) + 'm' + (inp.resDist >= 300 ? ' 이상' : ''),
          how: mil ? ' (조문 기준은 「주택 밀집지역」이라 아래에서 직접 고르세요)' : okd ? ' (5m 밖 → 금지 대상에서 빠짐)' : ' (5m 안 · 공원·녹지·지형지물로 차단되면 빠짐)' });
        if (okd && T.kind === 'cannot') { exempt = true; return; }
      }
      var qid = nz(zoneNm) + '|' + use + '|' + (sub || '') + '|' + it.k, ans = (inp.ans || {})[qid];
      if (all) { if (nc.length && nc.every(function (x) { return x.ok === false; })) return; c = !nc.length || nc.some(function (x) { return x.ok == null; }); }
      checks = checks.concat(nc);
      hit.push({ it: it, all: all, nc: nc, c: c, qid: qid, ans: c ? ans : undefined });
    });
    // 머리말(층수 제한 등)
    var noteChecks = T.kind === 'can' ? numChecks(T.note || '', inp) : [];
    var mineHits = hit.filter(function (h) { return !h.all; }), allHits = hit.filter(function (h) { return h.all; });
    var failNum = mineHits.some(function (h) { return h.nc.some(function (x) { return x.ok === false; }); }) || noteChecks.some(function (x) { return x.ok === false; });
    var lvl, msg;
    if (T.kind === 'can') {
      var okH = mineHits.filter(function (h) { return !h.c || h.ans === true; }), openH = mineHits.filter(function (h) { return h.c && h.ans == null; });
      if (!mineHits.length) { lvl = 'RED'; msg = '건축할 수 없습니다(허용 목록에 없음)'; }
      else if (failNum) { lvl = 'RED'; msg = '입력한 규모·도로 조건으로는 건축할 수 없습니다'; }
      else if (okH.length) { lvl = 'GREEN'; msg = mineHits.some(function (h) { return h.ans === true; }) ? '조건을 갖추어 건축할 수 있습니다' : '건축할 수 있습니다'; }
      else if (!openH.length) { lvl = 'RED'; msg = '조건을 갖추지 못해 건축할 수 없습니다'; }
      else { lvl = 'YELLOW'; msg = '조건을 갖추면 건축할 수 있습니다'; }
    } else {
      var banH = hit.filter(function (h) { return !h.c || h.ans === true; }), openC = hit.filter(function (h) { return h.c && h.ans == null; });
      if (banH.some(function (h) { return !h.all; })) { lvl = 'RED'; msg = '건축할 수 없습니다'; }
      else if (banH.length) { lvl = 'RED'; msg = '층수 조건으로 건축할 수 없습니다'; }
      else if (!openC.length) { lvl = 'GREEN'; msg = hit.length ? '금지 조건에 해당하지 않아 건축할 수 있습니다' : exempt ? '금지 대상에서 빠져 건축할 수 있습니다' : '건축할 수 있습니다(금지 목록에 없음)'; }
      else { lvl = 'YELLOW'; msg = '아래 조건에 해당하면 건축할 수 없습니다'; }
    }
    var txt = hit.map(function (h) { return h.it.k + '. ' + h.it.t + (h.it.subs.length ? ' ' + h.it.subs.join(' ') : ''); });
    var seen = {}, ck = checks.concat(noteChecks).filter(function (c) { return c.ok != null; }).map(function (c) { return (c.ok ? '✔ ' : '✖ ') + c.txt + c.how; }).filter(function (x) { return seen[x] ? false : (seen[x] = 1); });
    var qs = hit.filter(function (h) { return h.c; }).map(function (h) { return { id: h.qid, kind: T.kind, all: h.all, ans: h.ans, text: h.it.k + '. ' + h.it.t + (h.it.subs.length ? ' ' + h.it.subs.join(' ') : '') }; });
    return { lvl: lvl, msg: msg, T: T, txt: txt, ck: ck, qs: qs };
  }

  // ------------------------------------------------------------ 로그인(관리자 화면과 같은 세션 공유)
  function initAuth() {
    var C = window.DH_ADMIN || {};
    if (sb || !C.url || !window.supabase) { authChecked = true; return Promise.resolve(); }
    sb = window.DH_SB || window.supabase.createClient(C.url, C.anonKey, { auth: { persistSession: true, storageKey: 'dh_admin_auth' } });
    return sb.auth.getSession().then(function (r) {
      session = r.data.session;
      if (!session) return;
      return sb.from('profiles').select('role,name,scopes').eq('id', session.user.id).maybeSingle().then(function (q) { profile = q.data; });
    }).catch(function () {}).then(function () { authChecked = true; });
  }
  function isAdmin() { return profile && (profile.role === 'admin' || profile.role === 'super'); }

  // ------------------------------------------------------------ 지도 레이어(브이월드 WMS·WMTS)
  var OVER = [
    { k: 'cad', t: '연속지적', on: 1, layers: 'lp_pa_cbnd_bubun', styles: ['lp_pa_cbnd_bubun_line', 'lp_pa_cbnd_bubun'], minZoom: 15 },
    { k: 'road', t: '도시계획도로', on: 1, layers: 'lt_c_upisuq151', op: 0.75 },
    { k: 'wsp', t: '상수원보호', on: 1, layers: 'lt_c_um710', op: 0.7 },
    { k: 'emd', t: '법정동 경계', on: 1, layers: 'lt_c_ademd' },
    { k: 'sgg', t: '시·군 경계', on: 0, layers: 'lt_c_adsigg' },
    { k: 'zone', t: '용도지역', on: 0, layers: 'lt_c_uq111', op: 0.55 },
    { k: 'dup', t: '지구단위계획', on: 0, layers: 'lt_c_upisuq161', op: 0.6 },
    { k: 'ind', t: '산업단지', on: 0, layers: 'lt_c_damdan', op: 0.6 }
  ];
  var MAP = null;
  function layerState() {
    var st = {}; try { st = JSON.parse(localStorage.getItem('dh_land_layers') || '{}'); } catch (e) {}
    if (st.base == null) st.base = 'base';
    OVER.forEach(function (o) { if (st[o.k] == null) st[o.k] = !!o.on; });
    return st;
  }
  function layerSave(k, v) { var st = layerState(); st[k] = v; try { localStorage.setItem('dh_land_layers', JSON.stringify(st)); } catch (e) {} }
  var C900913 = window.L ? window.L.extend({}, window.L.CRS.EPSG3857, { code: 'EPSG:900913' }) : null;
  function setBase(kind) {
    if (!MAP) return; var L = window.L, m = MAP.m, vk = (H.D.map || {}).vworld;
    (MAP.baseL || []).forEach(function (x) { m.removeLayer(x); });
    if (kind === 'sat' && vk) {
      MAP.baseL = [L.tileLayer('https://api.vworld.kr/req/wmts/1.0.0/' + vk + '/Satellite/{z}/{y}/{x}.jpeg', { maxZoom: 19, attribution: '© 국토교통부 브이월드' }),
        L.tileLayer('https://api.vworld.kr/req/wmts/1.0.0/' + vk + '/Hybrid/{z}/{y}/{x}.png', { maxZoom: 19 })];
    } else MAP.baseL = [H.baseLayer()];
    MAP.baseL.forEach(function (x) { x.addTo(m); x.bringToBack(); });
  }
  function setOver(k, on) {
    if (!MAP) return; var L = window.L, m = MAP.m, o = OVER.filter(function (x) { return x.k === k; })[0], vk = (H.D.map || {}).vworld;
    if (MAP.over[k]) { m.removeLayer(MAP.over[k]); delete MAP.over[k]; }
    if (!on || !o || !vk) return;
    var styles = o.styles || [o.layers], si = 0, ok = 0, bad = 0;
    var t = L.tileLayer.wms('https://api.vworld.kr/req/wms', { layers: o.layers, styles: styles[0], format: 'image/png', transparent: true, version: '1.3.0', crs: C900913,
      key: vk, domain: location.origin, exceptions: 'text/xml', opacity: o.op || 1, maxZoom: 19, minZoom: o.minZoom || 0, zIndex: 5 });
    t.on('tileload', function () { ok++; });
    t.on('tileerror', function () { bad++; if (!ok && bad >= 2 && si + 1 < styles.length) { si++; bad = 0; t.setParams({ styles: styles[si] }); } });
    MAP.over[k] = t.addTo(m);
    if (MAP.parcel) MAP.parcel.bringToFront();
  }
  function layerBar() {
    var el = H.el, st = layerState(), box = el('div', { class: 'chips', style: 'gap:5px;flex-wrap:wrap;font-size:13px' });
    function chip(label, active, fn) {
      var b = el('button', { class: 'chip', style: 'cursor:pointer;border:1px solid #C9D2DE;font-weight:700;' + (active ? 'background:#1B3A6B;color:#fff' : 'background:#fff;color:#38475A'), text: label });
      b.onclick = function (e) { e.stopPropagation(); fn(b); }; return b;
    }
    [['base', '일반지도'], ['sat', '항공사진']].forEach(function (x) {
      box.appendChild(chip(x[1], st.base === x[0], function () { layerSave('base', x[0]); setBase(x[0]); box.querySelectorAll('[data-b]').forEach(function (b) { var a = b.getAttribute('data-b') === x[0]; b.style.background = a ? '#1B3A6B' : '#fff'; b.style.color = a ? '#fff' : '#38475A'; }); }));
      box.lastChild.setAttribute('data-b', x[0]);
    });
    OVER.forEach(function (o) {
      box.appendChild(chip(o.t, st[o.k], function (b) { var v = !layerState()[o.k]; layerSave(o.k, v); setOver(o.k, v); b.style.background = v ? '#1B3A6B' : '#fff'; b.style.color = v ? '#fff' : '#38475A'; }));
    });
    return box;
  }

  // ------------------------------------------------------------ 브이월드(브라우저에서 JSONP로)
  var seq = 0;
  function qs(o) { return Object.keys(o).map(function (k) { return k + '=' + encodeURIComponent(o[k]); }).join('&'); }
  function vw(url, prm) {
    var key = (H.D.map || {}).vworld;
    return new Promise(function (res, rej) {
      var cb = 'dhvw' + (seq++) + '_' + Date.now(), s = document.createElement('script');
      var t = setTimeout(function () { cleanup(); rej(new Error('브이월드 응답 없음')); }, 15000);
      function cleanup() { clearTimeout(t); try { delete window[cb]; } catch (e) { window[cb] = undefined; } s.remove(); }
      window[cb] = function (j) { cleanup(); res(j); };
      s.onerror = function () { cleanup(); rej(new Error('브이월드 연결 실패')); };
      s.src = url + '?' + qs(Object.assign({ key: key, domain: location.origin, format: 'json', callback: cb }, prm));
      document.head.appendChild(s);
    });
  }
  function arr(v) { return v == null ? [] : Array.isArray(v) ? v : [v]; }
  function geocode(q) {
    var addr = /동해/.test(q) ? q : '강원특별자치도 동해시 ' + q;
    function one(type) {
      return vw('https://api.vworld.kr/req/address', { service: 'address', request: 'getcoord', version: '2.0', crs: 'epsg:4326', address: addr, refine: 'true', simple: 'false', type: type })
        .then(function (j) { var r = j && j.response; if (!r || r.status !== 'OK') return null; return { x: +r.result.point.x, y: +r.result.point.y, text: (r.refined || {}).text || addr }; });
    }
    var parcelFirst = /\d+(-\d+)?\s*$/.test(q) && !/(로|길)\s*\d/.test(q);
    return one(parcelFirst ? 'parcel' : 'road').then(function (r) { return r || one(parcelFirst ? 'road' : 'parcel'); });
  }
  // 필지 주변(반경 km 상자) 공간자료: 경계 안/밖과 경계까지 거리(m, 지도 좌표로 계산)
  function near(id, f, km) {
    var c = center(f.geometry), dy = km / 111, dx = km / (111 * Math.cos(c[1] * Math.PI / 180));
    return vw('https://api.vworld.kr/req/data', { service: 'data', request: 'GetFeature', data: id, size: 100, geometry: 'true', attribute: 'true', crs: 'EPSG:4326',
      geomFilter: 'BOX(' + (c[0] - dx) + ',' + (c[1] - dy) + ',' + (c[0] + dx) + ',' + (c[1] + dy) + ')' })
      .then(function (j) {
        var r = (j || {}).response || {};
        if (r.status === 'NOT_FOUND') return { list: [] };
        if (r.status !== 'OK') return { _err: (r.error && r.error.text) || r.status || '응답 없음' };
        return { list: ((r.result || {}).featureCollection || {}).features.map(function (g) {
          var m = distTo(f.geometry, g.geometry); return { p: g.properties || {}, inside: m.inside, dist: m.dist };
        }).sort(function (a, b) { return a.dist - b.dist; }) };
      }).catch(function (e) { return { _err: e.message }; });
  }
  function rings(g) { return !g ? [] : g.type === 'Polygon' ? g.coordinates : g.type === 'MultiPolygon' ? [].concat.apply([], g.coordinates) : []; }
  function center(g) { var x = 0, y = 0, n = 0; rings(g).slice(0, 1).forEach(function (r) { r.forEach(function (p) { x += p[0]; y += p[1]; n++; }); }); return n ? [x / n, y / n] : [129.11, 37.52]; }
  function inRing(pt, r) { var c = false; for (var i = 0, j = r.length - 1; i < r.length; j = i++) { if (((r[i][1] > pt[1]) !== (r[j][1] > pt[1])) && (pt[0] < (r[j][0] - r[i][0]) * (pt[1] - r[i][1]) / (r[j][1] - r[i][1]) + r[i][0])) c = !c; } return c; }
  function distTo(a, b) {   // 필지(a)와 구역(b): 겹침 여부 + 가장 가까운 꼭짓점·변 사이 거리(m)
    var A = rings(a), B = rings(b), lat = center(a)[1], kx = 111320 * Math.cos(lat * Math.PI / 180), ky = 110540, best = Infinity, inside = false;
    var polys = b && b.type === 'MultiPolygon' ? b.coordinates : b && b.type === 'Polygon' ? [b.coordinates] : [];
    function inPoly(pt) { return polys.some(function (pg) { return inRing(pt, pg[0]) && !pg.slice(1).some(function (h) { return inRing(pt, h); }); }); }
    function seg(p, q, r) { var px = p[0] * kx, py = p[1] * ky, qx = q[0] * kx, qy = q[1] * ky, rx = r[0] * kx, ry = r[1] * ky, dx = rx - qx, dy = ry - qy, L2 = dx * dx + dy * dy, t = L2 ? Math.max(0, Math.min(1, ((px - qx) * dx + (py - qy) * dy) / L2)) : 0; return Math.hypot(px - qx - t * dx, py - qy - t * dy); }
    A.forEach(function (ra) { ra.forEach(function (p) { if (inPoly(p)) inside = true; B.forEach(function (rb) { for (var i = 1; i < rb.length; i++) best = Math.min(best, seg(p, rb[i - 1], rb[i])); }); }); });
    return { inside: inside, dist: inside ? 0 : best };
  }
  function parcelBy(prm) {
    return vw('https://api.vworld.kr/req/data', Object.assign({ service: 'data', request: 'GetFeature', data: 'LP_PA_CBND_BUBUN', size: 1, geometry: 'true', attribute: 'true', crs: 'EPSG:4326' }, prm))
      .then(function (j) { var f = (((j || {}).response || {}).result || {}).featureCollection; f = f && f.features && f.features[0]; return f || null; });
  }
  function ned(op, prm) {
    return vw('https://api.vworld.kr/ned/data/' + op, Object.assign({ numOfRows: 100, pageNo: 1 }, prm)).catch(function (e) { return { _err: e.message }; });
  }

  // ------------------------------------------------------------ 조회 → 판정
  function lookup(q) {
    q = String(q || '').trim();
    if (!q || busy) return;
    busy = true; cur = { loading: '위치를 찾는 중…', q: q }; H.render();
    var pnuIn = /^\d{19}$/.test(q) ? q : null, f;
    (pnuIn ? parcelBy({ attrFilter: 'pnu:=:' + pnuIn }) : geocode(q).then(function (g) {
      if (!g) throw new Error('주소를 찾지 못했습니다. 「천곡동 806」처럼 동 이름과 지번, 또는 도로명 주소로 넣어 주세요.');
      return parcelBy({ geomFilter: 'POINT(' + g.x + ' ' + g.y + ')' });
    })).then(function (feat) {
      if (!feat) throw new Error('필지를 찾지 못했습니다.');
      f = feat; var pnu = f.properties.pnu;
      cur = { loading: '토지·건축물 자료를 받는 중…', q: q };
      H.render();
      var yr = new Date().getFullYear();
      return Promise.all([
        ned('getLandUseAttr', { pnu: pnu }),
        ned('getLandCharacteristics', { pnu: pnu, stdrYear: String(yr) }).then(function (j) { return arr(((j || {}).landCharacteristicss || {}).field).length ? j : ned('getLandCharacteristics', { pnu: pnu, stdrYear: String(yr - 1) }); }),
        ned('ladfrlList', { pnu: pnu }),
        near('LT_C_UM710', f, 3),
        near('LT_C_UQ111', f, 0.3),
        (sb ? sb.functions.invoke('land', { body: { pnu: pnu } }) : Promise.reject(new Error('연결 설정 없음'))).then(function (r) { return r.error ? { _err: r.error.message } : r.data; }).catch(function (e) { return { _err: e.message }; })
      ]).then(function (res) {
        var d = { q: q, pnu: pnu, feat: f, use: arr(((res[0] || {}).landUses || {}).field), ch: arr(((res[1] || {}).landCharacteristicss || {}).field), lad: arr(((res[2] || {}).ladfrlVOList || {}).ladfrlVOList), wsp: res[3] || {}, bld: res[5] || {}, resz: res[4] || {},
          errs: [res[0] && res[0]._err ? '토지이용계획: ' + res[0]._err : null, res[1] && res[1]._err ? '토지특성: ' + res[1]._err : null, res[2] && res[2]._err ? '토지대장: ' + res[2]._err : null, res[3] && res[3]._err ? '상수원보호구역 조회: ' + res[3]._err : null, res[5] && res[5]._err ? '건축물대장: ' + res[5]._err : null, res[4] && res[4]._err ? '주거지역 거리 조회: ' + res[4]._err : null].filter(Boolean) };
        d.ch.sort(function (a, b) { return String(b.stdrYear).localeCompare(String(a.stdrYear)); });
        d.ev = evaluate(d);
        cur = d;
        saveHist(d);
      });
    }).catch(function (e) { cur = { error: e.message, q: q }; })
      .then(function () { busy = false; H.render(); });
  }

  // 동해시 조례 원문 수치
  function ordMe() { return ((((H.D.life || {}).ordin) || {}).regions || {})[H.D.me] || null; }
  function zoneRule(z) { var o = ordMe(); if (!o || !z) return null; var b = (o.bcr || {})[z], f = (o.far || {})[z]; return b == null && f == null ? null : { bcr: b, far: f }; }
  function artCite(k) { var o = ordMe(), a = o && o[k + '_art']; return a ? (o.name || '동해시 도시계획 조례') + ' ' + (a.no || '') + '(' + a.title + ')' : '동해시 도시계획 조례'; }
  function artText(k) { var o = ordMe(), a = o && o[k + '_art']; return a ? a.text : ''; }

  // 토지이용계획 항목 → 쉬운 설명·판정(키워드 규칙)
  var RULES = [
    [/개발제한구역/, 'RED', '「개발제한구역의 지정 및 관리에 관한 특별조치법」 제12조', '개발제한구역(그린벨트)', '원칙적으로 건축·개발 금지. 허용되는 시설만 허가로 가능합니다.'],
    [/농업진흥구역/, 'RED', '「농지법」 제32조', '농업진흥구역', '농업용 시설 외 건축 금지. 진흥구역 해제 없이는 일반 건축이 어렵습니다.'],
    [/하천구역/, 'RED', '「하천법」 제33조', '하천구역', '하천 점용허가 없이는 건축할 수 없습니다.'],
    [/(공익용산지|임업용산지|보전산지)/, 'YELLOW', '「산지관리법」 제12조', '보전산지', '산지전용 허가 대상이며 허용 용도가 제한됩니다.'],
    [/농업보호구역/, 'YELLOW', '「농지법」 제32조', '농업보호구역', '농지전용과 허용 용도 제한이 있습니다.'],
    [/지구단위계획구역/, 'YELLOW', '「국토의 계획 및 이용에 관한 법률」 제54조', '지구단위계획구역', '구역별 지구단위계획(용도·높이·건폐율 등)에 맞게 지어야 합니다. 결정 고시 내용을 확인해야 합니다.'],
    [/(군사기지|군사시설|비행안전구역|제한보호구역|통제보호구역)/, 'YELLOW', '「군사기지 및 군사시설 보호법」 제13조', '군사시설보호구역', '관할 부대 협의가 필요하며 높이·용도가 제한될 수 있습니다.'],
    [/(역사문화환경|문화유산|문화재|보존지역)/, 'YELLOW', '「문화유산의 보존 및 활용에 관한 법률」 제13조·제35조', '문화유산 보존구역', '현상변경 허가(문화유산 심의)가 필요할 수 있어 기간이 늘어납니다.'],
    [/절대보호구역/, 'YELLOW', '「교육환경 보호에 관한 법률」 제9조', '교육환경 절대보호구역', '학교 출입문 50m 안이라 유해시설 등 금지 시설이 많습니다.'],
    [/(교육환경보호구역|상대보호구역)/, 'INFO', '「교육환경 보호에 관한 법률」 제9조', '교육환경보호구역', '학교 주변이라 일부 시설(유해시설 등)은 들어설 수 없습니다.'],
    [/(자연재해위험|재해위험|급경사지|방재지구|침수)/, 'YELLOW', '「자연재해대책법」·「급경사지 재해예방에 관한 법률」', '재해위험 관련 지역', '재해 저감 대책·설계가 추가로 필요할 수 있습니다.'],
    [/(경관지구)/, 'YELLOW', '「국토계획법」 제76조, 동해시 도시계획 조례 제37조', '경관지구', '건폐율·높이·형태 제한이 추가될 수 있습니다.'],
    [/(중요시설물보호지구|보호지구)/, 'YELLOW', '「국토계획법」 제37조·제76조', '보호지구', '보호 대상 시설 기능을 해치는 건축이 제한될 수 있습니다.'],
    [/(가축사육제한구역)/, 'INFO', '「가축분뇨의 관리 및 이용에 관한 법률」 제8조', '가축사육제한구역', '축사 신축이 제한되는 곳입니다(일반 건축에는 영향 적음).'],
    [/상수원보호구역/, 'RED', '「수도법」 제7조', '상수원보호구역', '건축물 신축·증축, 토지 형질변경 등이 금지되거나 허가 대상입니다(주민 생활시설 등 일부만 허용).'],
    [/수변구역/, 'YELLOW', '수계별 물관리 및 주민지원에 관한 법률', '수변구역', '폐수배출시설·숙박·음식점 등 오염원 시설 설치가 제한됩니다.'],
    [/공장설립(제한|승인)지역/, 'YELLOW', '「수도법」 제7조의2', '공장설립 제한·승인지역(상수원 상류)', '상수원 보호를 위해 공장 설립이 금지되거나 승인을 받아야 합니다. 공장이 아니면 영향이 적습니다.'],
    [/수질보전특별대책지역/, 'YELLOW', '「환경정책기본법」 제38조', '수질보전특별대책지역', '오염물질 배출시설 입지와 규모가 제한됩니다.'],
    [/배출시설설치제한/, 'YELLOW', '「물환경보전법」', '배출시설 설치 제한지역', '폐수배출시설 설치가 제한됩니다.'],
    [/경제자유구역/, 'YELLOW', '「경제자유구역의 지정 및 운영에 관한 특별법」', '경제자유구역', '경제자유구역 개발계획·실시계획에 맞춰야 하며, 개발사업 시행자 협의가 필요할 수 있습니다.'],
    [/개발행위허가제한지역/, 'RED', '「국토의 계획 및 이용에 관한 법률」 제63조', '개발행위허가 제한지역', '지정 기간 동안 건축·형질변경 등 개발행위 허가가 제한됩니다.'],
    [/토지거래.*허가구역/, 'YELLOW', '「부동산 거래신고 등에 관한 법률」 제11조', '토지거래허가구역', '토지 매매 시 시장·군수 허가가 필요합니다.'],
    [/접도구역/, 'YELLOW', '「도로법」 제40조', '접도구역', '접도구역 안에서는 건축물 신축과 형질변경이 제한됩니다.'],
    [/홍수관리구역/, 'YELLOW', '「하천법」 제12조', '홍수관리구역', '홍수 흐름을 방해하는 건축·성토가 제한됩니다.'],
    [/소하천/, 'YELLOW', '「소하천정비법」', '소하천구역·예정지', '소하천 점용허가 없이 건축할 수 없습니다.'],
    [/(자연공원|공원구역|공원자연)/, 'RED', '「자연공원법」 제23조', '자연공원', '공원계획에 맞지 않는 건축·개발이 금지됩니다.'],
    [/백두대간/, 'RED', '「백두대간 보호에 관한 법률」 제7조', '백두대간보호지역', '핵심구역은 대부분의 개발이 금지되고, 완충구역도 행위 제한이 있습니다.'],
    [/산림보호구역/, 'YELLOW', '「산림보호법」 제9조', '산림보호구역', '건축·형질변경 등 행위가 제한됩니다.'],
    [/(습지보호|습지주변관리)/, 'YELLOW', '「습지보전법」 제13조', '습지보호지역', '건축물 신축 등 행위가 제한됩니다.'],
    [/(야생생물|야생동식물)/, 'YELLOW', '「야생생물 보호 및 관리에 관한 법률」', '야생생물 보호구역', '보호구역 안 행위가 제한될 수 있습니다.'],
    [/(관광단지|관광지)/, 'YELLOW', '「관광진흥법」 제54조', '관광지·관광단지', '조성계획에 맞는 시설만 지을 수 있습니다.'],
    [/(산업단지|농공단지)/, 'YELLOW', '「산업입지 및 개발에 관한 법률」', '산업단지', '관리기본계획의 입주 업종·시설 기준을 따라야 합니다.'],
    [/(연안육역|연안해역|연안관리)/, 'INFO', '「연안관리법」', '연안 관리 지역', '연안정비·연안관리계획 협의가 필요할 수 있습니다.'],
    [/(대기환경규제|대기관리권역)/, 'INFO', '「대기환경보전법」', '대기환경 규제지역', '대기오염물질 배출시설 기준이 강화됩니다(일반 건축에는 영향 적음).'],
    [/(공원|녹지)$/, 'YELLOW', '「도시공원 및 녹지 등에 관한 법률」', '도시계획시설(공원·녹지)', '공원·녹지 부지는 일반 건축이 제한됩니다.']
  ];
  function evaluate(d) {
    var R = [], ch = d.ch[0] || {}, lad = d.lad[0] || {};
    function add(level, area, tag, detail, impact, cite) { R.push({ level: level, area: area, tag: tag, detail: detail, impact: impact, cite: cite || '' }); }
    var area = +(lad.lndpclAr || ch.lndpclAr || 0), jimok = lad.lndcgrCodeNm || ch.lndcgrCodeNm || '';
    // 용도지역: 토지특성(용도지역1·2) → 없으면 토지이용계획에서 「…지역」
    var zones = [ch.prposArea1Nm, ch.prposArea2Nm].filter(function (z) { return z && z !== '지정되지않음'; });
    if (!zones.length) d.use.forEach(function (u) { var n = u.prposAreaDstrcCodeNm || ''; if (/지역$/.test(n) && /^UQA/.test(u.prposAreaDstrcCode || '') && zones.indexOf(n) < 0) zones.push(n); });
    var zone = zones[0] || '', rule = zoneRule(zone);
    // (1) 용도지역 + 조례 건폐율·용적률
    if (!zone) add('YELLOW', '토지', '용도지역 확인 안 됨', '토지특성·토지이용계획 자료에 용도지역이 없습니다.', '용도지역을 알 수 없어 규모(건폐율·용적률)를 계산하지 못했습니다.', '「국토계획법」 제36조');
    else if (!rule) add('YELLOW', '토지', zone + ' · 조례 수치 없음', '동해시 도시계획 조례에서 「' + zone + '」의 건폐율·용적률을 찾지 못했습니다.', '규모 계산을 하지 못했습니다.', artCite('bcr'));
    else add('GREEN', '토지', zone, zone + '은(는) 동해시 도시계획 조례상 건폐율 ' + fmt(rule.bcr) + '% · 용적률 ' + fmt(rule.far) + '% 이하입니다.' + (zones[1] ? ' (일부 ' + zones[1] + ' 걸침)' : ''), '대지 ' + fmt(area) + '㎡ 기준 바닥면적 최대 약 ' + fmt(area * rule.bcr / 100) + '㎡, 연면적 최대 약 ' + fmt(area * rule.far / 100) + '㎡ (예상치)', artCite('bcr') + ' · ' + artCite('far'));
    if (zones[1]) add('YELLOW', '토지', '용도지역 두 개에 걸침', zone + '와(과) ' + zones[1] + '에 걸쳐 있습니다.', '걸친 면적 비율에 따라 건폐율·용적률을 나눠 적용합니다(「국토계획법」 제84조).', '「국토계획법」 제84조');
    if (useSel) {
      var nmU = useSel + (useSub ? '(' + useSub + ')' : '');
      var rn = ch.roadSideCodeNm || '', RR = /광대/.test(rn) ? [25, null] : /중로/.test(rn) ? [12, 25] : /소로/.test(rn) ? [8, 12] : /세로/.test(rn) ? [0, 8] : /맹지/.test(rn) ? [0, 0] : null;
      var RZ = ((d.resz || {}).list || []).filter(function (x) { return /주거지역/.test(JSON.stringify(x.p)); });
      var inp = { area: inArea, floor: inFloor, road: inRoad, roadRange: RR, roadNm: rn, ans: qAns, resDist: !d.resz || d.resz._err ? null : RZ.length ? RZ[0].dist : !(d.resz.list || []).length ? 300 : (d.resz.list || []).some(function (x) { return /지역/.test(JSON.stringify(x.p)); }) ? 300 : null };
      var uz = [zone].concat(d.use.some(function (u) { return /자연취락지구/.test(u.prposAreaDstrcCodeNm || ''); }) ? ['자연취락지구'] : []);
      // 별표보다 먼저 적용되거나 함께 적용되는 구역·지구
      var names = d.use.map(function (u) { return u.prposAreaDstrcCodeNm || ''; });
      var PRE = [[/지구단위계획/, '지구단위계획구역', '지구단위계획에서 정한 허용·불허 용도와 규모가 별표보다 먼저 적용됩니다', '「국토계획법」 제54조'],
        [/개발제한구역/, '개발제한구역', '별표 대신 「개발제한구역법」 제12조·시행령 별표 1에서 허용하는 건축물만 지을 수 있습니다', '「개발제한구역의 지정 및 관리에 관한 특별조치법」 제12조'],
        [/특정용도제한지구/, '특정용도제한지구', '지구에서 막는 용도는 별표에 있어도 지을 수 없습니다', '「국토계획법」 제76조'],
        [/개발진흥지구/, '개발진흥지구', '개발진흥지구 계획에서 정한 용도가 적용됩니다', '「국토계획법」 제76조'],
        [/경관지구/, '경관지구', '높이·층수·건폐율 등이 조례로 더 제한됩니다', '「국토계획법」 제76조'],
        [/고도지구/, '고도지구', '도시관리계획으로 정한 높이까지만 지을 수 있습니다', '「국토계획법」 제76조'],
        [/(방재지구|보호지구|복합용도지구)/, '용도지구', '지구에서 정한 건축 제한이 함께 적용됩니다', '「국토계획법」 제76조']]
        .filter(function (r) { return names.some(function (n) { return r[0].test(n); }); });
      uz.forEach(function (z) {
        var J = useJudge(z, useSel, useSub, inp);
        if (!J) { add('YELLOW', '토지', '예정 용도: ' + nmU, '「' + (z || '용도지역 미확인') + '」의 동해시 도시계획 조례 별표를 찾지 못해 판정하지 못했습니다.', '토지이음에서 행위제한을 확인하세요.', '동해시 도시계획 조례 제31조'); return; }
        var lv = J.lvl, pre = PRE.map(function (r) { return '[' + r[1] + '] ' + r[2] + '(' + r[3] + ').'; });
        if (lv === 'GREEN' && PRE.some(function (r) { return /지구단위|개발제한|특정용도|개발진흥/.test(r[1]); })) lv = 'YELLOW';
        if (PRE.some(function (r) { return r[1] === '개발제한구역'; })) lv = lv === 'RED' ? 'RED' : 'YELLOW';
        var ho = '건축법 시행령 별표 1 제' + USE_HO[useSel] + '호';
        add(lv, '토지', '예정 용도: ' + nmU + ' · ' + J.msg.replace(/\(.*\)/, ''),
          '「' + z + '」에서 「' + nmU + '」은(는) 별표 기준 ' + J.msg + '.' + (J.ck.length ? ' 입력값 확인: ' + J.ck.join(', ') + '.' : '') + (J.T.note ? ' [별표 머리말] ' + J.T.note : '') + (pre.length ? ' ' + pre.join(' ') : ''),
          J.txt.length ? '해당 조항: ' + J.txt.join(' / ') : '「' + z + '」 ' + (J.T.kind === 'can' ? '허용' : '금지') + ' 목록(' + J.T.items.length + '개 항목)에 「' + nmU + '」(' + ho + ')이 없습니다.',
          (ordMe().name || '동해시 도시계획 조례') + ' ' + J.T.title + ' · 「' + ho.replace('건축법 시행령', '건축법 시행령」') );
        R[R.length - 1].qs = J.qs; R[R.length - 1].pin = true;
      });
    }
    // (2) 지목
    if (/^(전|답|과수원)$/.test(jimok)) add('YELLOW', '토지', '농지(' + jimok + ')', '지목이 「' + jimok + '」입니다.', '농지전용 허가와 농지보전부담금(공시지가의 30%, ㎡당 5만원 한도)이 듭니다.', '「농지법」 제34조·제38조');
    else if (jimok === '임야') add('YELLOW', '토지', '임야', '지목이 「임야」입니다.', '산지전용 허가와 대체산림자원조성비가 듭니다.', '「산지관리법」 제14조·제19조');
    else if (/^(도로|하천|구거|유지|제방|철도용지)$/.test(jimok)) add('RED', '토지', '지목 ' + jimok, '지목이 「' + jimok + '」로 공공시설 부지입니다.', '용도폐지·지목변경 없이는 일반 건축이 어렵습니다.', '「공간정보의 구축 및 관리 등에 관한 법률」 제67조');
    else if (jimok) add('GREEN', '토지', '지목 ' + jimok, '지목이 「' + jimok + '」입니다.', jimok === '대' ? '건축용 토지로 지목 변경이 필요 없습니다.' : '용도에 따라 지목 변경이 필요할 수 있습니다.', '「공간정보의 구축 및 관리 등에 관한 법률」 제67조');
    // (3) 도로(토지특성 도로접면)
    var road = ch.roadSideCodeNm || '';
    if (!road) add('YELLOW', '도로', '도로 정보 없음', '토지특성 자료에 도로접면 정보가 없습니다.', '도로에 접했는지 현장·지적도로 확인해야 합니다.', '건축법 제44조');
    else if (/맹지/.test(road)) add('RED', '도로', '맹지(도로 미접)', '도로에 닿지 않은 땅(맹지)입니다.', '건축하려면 너비 4m 이상 도로에 2m 이상 접해야 합니다. 진입로 확보(토지 매입·사용승낙) 없이는 건축허가가 어렵습니다.', '건축법 제2조제1항제11호·제44조');
    else if (/세로.*불/.test(road)) add('YELLOW', '도로', '좁은 도로(차량 통행 불가)', '「' + road + '」: 자동차가 다니기 어려운 폭 8m 미만 도로에 접합니다.', '도로 폭이 4m가 안 되면 도로 중심선에서 2m까지 건축선을 물려야 해 쓸 수 있는 대지가 줄어듭니다.', '건축법 제46조(건축선)');
    else if (/세로/.test(road)) add('INFO', '도로', '폭 8m 미만 도로', '「' + road + '」: 자동차 통행이 가능한 폭 8m 미만 도로에 접합니다.', '실제 폭이 4m 이상인지 지적도로 확인하세요. 4m 미만이면 건축선 후퇴가 생깁니다.', '건축법 제2조·제46조');
    else add('GREEN', '도로', '도로 접함(' + road + ')', '「' + road + '」: ' + (/광대/.test(road) ? '폭 25m 이상' : /중로/.test(road) ? '폭 12~25m' : '폭 8~12m') + ' 도로에 접합니다.', '진입 도로 기본 요건이 양호합니다.', '건축법 제44조');
    // (4) 토지이용계획: 도시계획시설(도로) 저촉·접함, 각종 지역·지구·구역
    var seen = {};
    d.use.forEach(function (u) {
      var n = u.prposAreaDstrcCodeNm || '', at = u.cnflcAtNm || '', key = n + at;
      if (seen[key] || !n || /^(도시지역|지정되지않음)$/.test(n) || n === zone) return; seen[key] = 1;
      if (/^(대로|중로|소로)\d?류/.test(n)) {
        if (/저촉/.test(at)) add('YELLOW', '도로', '계획도로 저촉(' + n + ')', '도시계획시설 도로 「' + n + '」가 땅 일부를 지나갑니다(저촉).', '저촉 부분은 건축이 제한되고, 사업 시행 시 수용될 수 있습니다. 저촉 면적을 확인하세요.', '「국토계획법」 제64조');
        else if (/접합/.test(at)) add('GREEN', '도로', '계획도로 접함(' + n + ')', '도시계획시설 도로 「' + n + '」에 접합니다.', '진입에 유리합니다.', '「국토계획법」 제43조');
        return;
      }
      for (var i = 0; i < RULES.length; i++) {
        var r = RULES[i]; if (!r[0].test(n)) continue;
        var lvl = r[1]; if (lvl === 'YELLOW' && /접합/.test(at)) lvl = 'INFO';
        add(lvl, '규제', n + (at ? '(' + at + ')' : ''), r[4], lvl === 'RED' ? '부지 재선정 또는 해제·허가 가능성 검토가 필요합니다.' : '해당 법령 협의·허가 기간과 비용을 일정에 반영해야 합니다.', r[2]);
        return;
      }
    });
    // (4-2) 상수원보호구역(지도 경계로 직접 확인, 반경 3km)
    var W = d.wsp || {};
    if (!W._err) {
      var w0 = (W.list || [])[0], wn = function (w) { var p = w.p; return (p.alias || p.remark || '상수원보호구역') + (p.dyear ? ' (' + p.dyear + '년 고시' + (p.dnum ? ' ' + p.dnum : '') + ')' : ''); };
      var already = R.some(function (r) { return /상수원보호구역/.test(r.tag); });
      if (w0 && w0.inside && !already) add('RED', '환경', '상수원보호구역 안', '필지가 「' + wn(w0) + '」 경계 안에 있습니다(브이월드 상수원보호 경계도).', '건축물 신축·증축, 토지 형질변경 등이 금지되거나 허가 대상입니다.', '「수도법」 제7조');
      else if (w0 && !w0.inside && w0.dist <= 1000) add('YELLOW', '환경', '상수원보호구역 ' + fmt(w0.dist) + 'm', '「' + wn(w0) + '」 경계에서 약 ' + fmt(w0.dist) + 'm 떨어져 있습니다(경계도 기준 직선거리).', '보호구역 밖이지만 상류 쪽이면 공장설립 제한·승인지역에 해당할 수 있습니다. 토지이용계획에 「공장설립」 지정이 있는지 함께 보세요.', '「수도법」 제7조·제7조의2');
      else if (w0 && !w0.inside) add('INFO', '환경', '상수원보호구역 ' + fmt(w0.dist) + 'm', '가장 가까운 「' + wn(w0) + '」 경계까지 약 ' + fmt(w0.dist) + 'm입니다(경계도 기준 직선거리).', '보호구역 밖입니다.', '「수도법」 제7조');
      else add('GREEN', '환경', '상수원보호구역 없음(반경 3km)', '필지 반경 약 3km 안에 상수원보호구역 경계가 없습니다(브이월드 상수원보호 경계도).', '상수원보호구역 행위 제한은 해당하지 않습니다.', '「수도법」 제7조');
    }
    // (5) 지형
    if (/급경사|고지/.test(ch.tpgrphHgCodeNm || '')) add('YELLOW', '토지', '지형 ' + ch.tpgrphHgCodeNm, '지형 높이가 「' + ch.tpgrphHgCodeNm + '」입니다.', '절·성토 등 토목 공사비가 늘어날 수 있습니다.', '「국토계획법」 제58조(개발행위허가 기준)');
    if (/부정형|자루형|삼각형/.test(ch.tpgrphFrmCodeNm || '')) add('INFO', '토지', '땅 모양 ' + ch.tpgrphFrmCodeNm, '땅 모양이 「' + ch.tpgrphFrmCodeNm + '」입니다.', '건물 배치가 불리해 실제 지을 수 있는 면적이 줄 수 있습니다.', '토지특성 조사(국토교통부)');
    // (6) 기존 건축물
    var B = buildings(d.bld);
    if (d.bld && d.bld._err) add('YELLOW', '건물', '건축물대장 조회 실패', d.bld._err, '건축물 유무를 확인하지 못했습니다.', '건축법 제38조');
    else if (!B.length) add('GREEN', '건물', '건축물 없음', '건축물대장에 등록된 건물이 없습니다(나대지 또는 미등재).', '철거 비용이 들지 않습니다. 무허가 건물이 있는지는 현장 확인이 필요합니다.', '건축법 제38조(건축물대장)');
    else {
      var oldest = B.reduce(function (a, b) { return (b.age || 0) > (a.age || 0) ? b : a; }, B[0]);
      if (oldest.age != null && oldest.age >= 30) add('INFO', '건물', '노후 건축물(' + oldest.age + '년 경과)', (oldest.name || '건물') + ': ' + (oldest.use || '') + ', ' + oldest.approve + ' 사용승인 → ' + oldest.age + '년 지났습니다.', '철거비·폐기물 처리비(석면 조사 포함) 또는 리모델링 타당성 검토가 필요합니다.', '「건축물관리법」 제13조·제30조');
      else add('INFO', '건물', '기존 건축물 ' + B.length + '동', B.map(function (b) { return (b.name || '') + ' ' + (b.use || '') + (b.approve ? ' (' + b.approve + ' 승인)' : ''); }).join(' · '), '기존 건물 활용 또는 철거 여부를 정해야 합니다.', '건축법 제38조');
    }
    var hasRed = R.some(function (r) { return r.level === 'RED'; }), hasYel = R.some(function (r) { return r.level === 'YELLOW'; });
    var status = hasRed ? 'RED' : hasYel ? 'YELLOW' : 'GREEN';
    return { status: status, reasons: R, zone: zone, zones: zones, rule: rule, area: area, jimok: jimok, road: road, buildings: B,
      price: +(ch.pblntfPclnd || (d.feat.properties || {}).jiga || 0), priceYear: ch.stdrYear || (d.feat.properties || {}).gosi_year };
  }
  function buildings(bld) {
    var t = (bld && bld.title && bld.title.items) || [], rc = !t.length && bld && bld.recap && bld.recap.items || [];
    if (rc.length) t = rc.map(function (x) { return Object.assign({}, x, { bldNm: (x.bldNm || '').trim() + ' (총괄표제부)' }); });
    return t.map(function (x) {
      var ap = String(x.useAprDay || '').trim(), y = +ap.slice(0, 4), now = new Date();
      var age = y > 1800 ? now.getFullYear() - y - ((now.getMonth() + 1) * 100 + now.getDate() < (+ap.slice(4, 6) || 1) * 100 + (+ap.slice(6, 8) || 1) ? 1 : 0) : null;
      return { name: (x.bldNm || '').trim() + (x.dongNm && x.dongNm.trim() ? ' ' + x.dongNm.trim() : ''), use: x.mainPurpsCdNm, struct: x.strctCdNm, floors: x.grndFlrCnt, under: x.ugrndFlrCnt, height: x.heit,
        tot: x.totArea, arch: x.archArea, plat: x.platArea, bc: x.bcRat, vl: x.vlRat, hhld: x.hhldCnt, ho: x.hoCnt, park: (+x.indrMechUtcnt || 0) + (+x.indrAutoUtcnt || 0) + (+x.oudrMechUtcnt || 0) + (+x.oudrAutoUtcnt || 0), elev: (+x.rideUseElvtCnt || 0) + (+x.emgenUseElvtCnt || 0), main: x.mainAtchGbCdNm, roof: x.roofCdNm, permit: x.pmsDay, start: x.stcnsDay, approve: ap.length >= 8 ? ap.slice(0, 4) + '.' + ap.slice(4, 6) + '.' + ap.slice(6, 8) : (ap || ''), age: age, earthquake: x.rserthqkDsgnApplyYn, eqAbility: x.rserthqkAblty };
    });
  }
  function annexFor(zone) { var o = ordMe(); return o && (o.annex || []).filter(function (a) { return zone && a.title && a.title.indexOf(zone) >= 0; })[0]; }
  function fmt(v, d) { return v == null || isNaN(v) ? '–' : Number(v).toLocaleString('ko-KR', { maximumFractionDigits: d == null ? 0 : d }); }
  function eumUrl(pnu) { return 'https://www.eum.go.kr/web/ar/lu/luLandDet.jsp?pnu=' + pnu + '&mode=search&isNoScr=script&selGbn=umd'; }
  function headline(d) {
    var ev = d.ev, n = ev.reasons.filter(function (r) { return r.level === 'RED'; }), y = ev.reasons.filter(function (r) { return r.level === 'YELLOW'; });
    var l1 = (ev.zone || '용도지역 미확인') + ' · ' + (ev.jimok || '지목 미확인') + ' · ' + fmt(ev.area) + '㎡' + (ev.rule ? ' → 연면적 최대 약 ' + fmt(ev.area * ev.rule.far / 100) + '㎡(예상치)' : '');
    var l2 = n.length ? '중대 제약: ' + n.map(function (r) { return r.tag; }).join(', ') : y.length ? '확인할 조건 ' + y.length + '건: ' + y.slice(0, 3).map(function (r) { return r.tag; }).join(', ') + (y.length > 3 ? ' 외' : '') : '중대한 제약이 확인되지 않았습니다.';
    var l3 = n.length ? '부지 재선정 또는 제약 해소 방안 검토' : y.length ? '협의·허가 기간과 추가 비용을 일정·예산에 반영' : '다음 단계(설계·인허가) 진행 가능';
    return [l1, l2, l3];
  }

  // ------------------------------------------------------------ 최근 검토(이 브라우저에만 저장, 서버 저장 없음)
  function recentGet() { try { return JSON.parse(localStorage.getItem('dh_land_recent') || '[]'); } catch (e) { return []; } }
  function saveHist(d) {
    if (!d.ev) return;
    var p = d.feat.properties || {}, r = recentGet().filter(function (x) { return x.pnu !== d.pnu; });
    r.unshift({ pnu: d.pnu, address: p.addr || d.q, status: d.ev.status });
    try { localStorage.setItem('dh_land_recent', JSON.stringify(r.slice(0, 6))); } catch (e) {}
  }

  // ------------------------------------------------------------ 화면
  function screen(helpers) {
    H = helpers;
    var el = H.el, view = H.view;
    if (!sb) initAuth();
    view.style.gridTemplateColumns = 'repeat(3, minmax(0, 1fr))';
    view.style.gridTemplateRows = '44px auto minmax(0, 1fr) minmax(0, 1fr)';
    var tabs = [['site', '부지 검토'], ['ord', '조례 비교 · 18개 시·군']];
    if (tab === 'hist') tab = 'site';
    view.appendChild(el('div', { class: 'title' }, [el('h1', { text: H.D.me + '시 토지 및 건축' }),
      el('div', { class: 'chips', style: 'flex-wrap:nowrap;gap:6px;margin-left:12px' }, tabs.map(function (t) {
        return el('button', { type: 'button', 'data-subtab': '1', class: 'chip' + (t[0] === tab ? ' on' : ''), style: 'cursor:pointer;border:0;font-weight:800;font-size:15px' + (t[0] === tab ? ';background:#1B3A6B;color:#fff' : ''), text: t[1], onclick: function () { tab = t[0]; H.render(); } }); })),
      el('span', { class: 'basis', text: tab === 'ord' ? '국가법령정보센터 자치법규 원문 · ' + (((H.D.life || {}).ordin || {}).at || '') + ' 확인' : '브이월드(국토교통부) · 건축HUB 건축물대장 · 동해시 도시계획 조례 원문' })]));
    if (tab === 'ord') return screenOrd(el);
    screenSite(el);
  }
  function full(node, row) { var s = H.el('section', { style: 'grid-column:1 / -1;grid-row:' + (row || '2 / span 3') }, [node]); H.view.appendChild(s); }

  function searchBar(el) {
    var inp = el('input', { type: 'text', placeholder: '지번(예: 천곡동 806) · 도로명 주소 · PNU 19자리', value: (cur && cur.q) || '', style: 'flex:1;font:inherit;font-size:19px;padding:10px 14px;border:2px solid #C9D2DE;border-radius:10px;min-width:0' });
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') lookup(inp.value); e.stopPropagation(); });
    var SST = 'font:inherit;font-size:16px;padding:9px;border:2px solid #C9D2DE;border-radius:10px';
    function re() { if (cur && cur.ev) { cur.ev = evaluate(cur); H.render(); } }
    var sel = el('select', { style: SST }, USES.map(function (u) { var o = el('option', { value: u, text: u || '예정 용도(선택)' }); if (u === useSel) o.selected = true; return o; }));
    sel.addEventListener('change', function () { useSel = sel.value; useSub = ''; re(); if (!cur) H.render(); });
    var subs = SUBS[useSel] || [];
    var sub = subs.length ? el('select', { style: SST + ';max-width:190px' }, [''].concat(subs.map(function (x) { return x[0]; })).map(function (u) { var o = el('option', { value: u, text: u || '세부 용도(전체)' }); if (u === useSub) o.selected = true; return o; })) : null;
    if (sub) sub.addEventListener('change', function () { useSub = sub.value; re(); });
    function num(ph, v, set, w) {
      var i = el('input', { type: 'number', min: '0', placeholder: ph, value: v == null ? '' : v, title: ph, style: SST + ';width:' + w + 'px' });
      i.addEventListener('keydown', function (e) { e.stopPropagation(); if (e.key === 'Enter') { set(i.value === '' ? null : +i.value); re(); } });
      i.addEventListener('change', function () { set(i.value === '' ? null : +i.value); re(); });
      return i;
    }
    var nums = useSel ? [num('바닥면적㎡', inArea, function (v) { inArea = v; }, 118), num('층수', inFloor, function (v) { inFloor = v; }, 72), num('도로폭m', inRoad, function (v) { inRoad = v; }, 98)] : [];
    var recent = recentGet().slice(0, 5);
    var bar = el('section', { style: 'grid-column:1 / -1;grid-row:2;flex-direction:row;align-items:center;gap:10px;padding:10px 14px' }, [inp, sel, sub].concat(nums).concat([
      el('button', { type: 'button', style: 'font:inherit;font-weight:800;font-size:18px;background:#1B3A6B;color:#fff;border:0;border-radius:10px;padding:10px 22px;cursor:pointer', text: busy ? '조회 중…' : '검토', onclick: function () { lookup(inp.value); } }),
      recent.length ? el('div', { class: 'chips', style: 'flex-wrap:nowrap;gap:6px;max-width:' + (useSel ? '18%' : '42%') + ';overflow:hidden' }, recent.map(function (h) {
        return el('button', { type: 'button', class: 'chip', style: 'cursor:pointer;border:0;white-space:nowrap;background:' + LV[h.status || 'INFO'].bg + ';color:' + LV[h.status || 'INFO'].c, text: '● ' + String(h.address || h.pnu).replace(/^강원특별자치도\s*동해시\s*/, ''), onclick: function () { lookup(h.pnu); } }); })) : null]));
    H.view.appendChild(bar);
    setTimeout(function () { if (!cur) inp.focus(); }, 50);
  }

  function screenSite(el) {
    searchBar(el);
    if (!cur || cur.loading || cur.error) {
      full(el('div', { style: 'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;height:100%;color:#556274' }, cur && cur.error ? [
        el('div', { style: 'font-size:24px;font-weight:800;color:#D9534F', text: '조회하지 못했습니다' }), el('div', { style: 'font-size:17px', text: cur.error })] : cur && cur.loading ? [
        el('div', { style: 'font-size:24px;font-weight:800;color:#1B3A6B', text: cur.loading })] : [
        el('div', { style: 'font-size:26px;font-weight:800;color:#1B3A6B', text: '검토할 땅의 지번이나 주소를 넣어 주세요' }),
        el('div', { style: 'font-size:17px', text: '토지이용계획·토지특성·토지대장·건축물대장을 한 번에 조회해 신호등(초록·노랑·빨강)으로 판정합니다.' }),
        el('div', { style: 'font-size:15px', text: '판정 기준: 국토계획법·건축법·도로법 + 동해시 도시계획 조례 원문 수치(' + (ordMe() ? ordMe().date.replace(/(\d{4})(\d\d)(\d\d)/, '$1.$2.$3') + ' 시행' : '조례 수집 대기') + ')' })]), '3 / span 2');
      return;
    }
    var d = cur, ev = d.ev, S = LV[ev.status], p = d.feat.properties || {};
    // ① 신호등 + 요약
    var hl = headline(d);
    var p1 = H.panel('종합 판정', p.addr || d.q, [
      el('div', { style: 'display:flex;align-items:center;gap:18px;margin:4px 0 8px' }, [
        el('div', { style: 'width:64px;height:64px;border-radius:50%;flex:none;background:' + S.c + ';box-shadow:0 0 0 7px ' + S.bg }),
        el('div', {}, [el('div', { style: 'font-size:28px;font-weight:900;color:' + S.c, text: { GREEN: '초록', YELLOW: '노랑', RED: '빨강' }[ev.status] }), el('div', { style: 'font-size:19px;font-weight:800;color:#1B3A6B', text: S.t })])]),
      el('ol', { style: 'margin:0;padding-left:22px;font-size:16px;line-height:1.45;color:#1D2733' }, hl.map(function (t) { return el('li', { text: t }); })),
      el('div', { class: 'chips', style: 'margin-top:8px;flex-wrap:wrap;gap:6px;max-height:27px;overflow:hidden' }, ev.reasons.filter(function (r) { return r.level === 'RED' || r.level === 'YELLOW'; }).map(function (r) {
        return el('span', { class: 'chip', style: 'background:' + LV[r.level].bg + ';color:' + LV[r.level].c + ';font-weight:800', text: r.tag }); })),
      el('div', { class: 'chips', style: 'margin-top:auto;padding-top:10px;gap:8px' }, [
        el('a', { class: 'chip navy', href: eumUrl(d.pnu), target: '_blank', rel: 'noopener', style: 'text-decoration:none;font-weight:800', text: '토지이음 원본 ↗' }),
        el('button', { type: 'button', class: 'chip violet', style: 'cursor:pointer;border:0;font-weight:800', text: '1장 브리핑 인쇄', onclick: function () { briefing(d); } }),
        annexFor(ev.zone) ? el('a', { class: 'chip', href: annexFor(ev.zone).url, target: '_blank', rel: 'noopener', style: 'text-decoration:none;font-weight:800', text: '조례 별표(허용 용도) ↗' }) : null,
        el('span', { class: 'chip', text: 'PNU ' + d.pnu })])]);
    p1.style.gridRow = '3';
    // ② 4대 요약 카드
    var B = ev.buildings, b0 = B[0];
    function kv(rows) { return el('div', { style: 'min-height:0' }, [el('table', { class: 'dt', style: 'font-size:15px' }, [el('tbody', {}, rows.filter(Boolean).map(function (r) { return el('tr', {}, [el('td', { style: 'color:#556274;white-space:nowrap', text: r[0] }), el('td', { class: 'r', html: '<b>' + r[1] + '</b>' })]); }))])]); }
    var p2 = H.panel('토지 · 규모 · 도로', '자료 기준: 토지특성 ' + ((d.ch[0] || {}).stdrYear || '–') + '년 · 공시지가 ' + (ev.priceYear || '–') + '년', kv([
      ['용도지역', ev.zones.join(' · ') || '–'], ['지목 · 면적', (ev.jimok || '–') + ' · ' + fmt(ev.area) + '㎡'],
      ['공시지가', ev.price ? fmt(ev.price) + '원/㎡ (총 약 ' + fmt(ev.price * ev.area / 1e8, 1) + '억원)' : '–'],
      ['건폐율 · 용적률(조례)', ev.rule ? fmt(ev.rule.bcr) + '% · ' + fmt(ev.rule.far) + '%' : '–'],
      ['최대 바닥 · 연면적', ev.rule ? '약 ' + fmt(ev.area * ev.rule.bcr / 100) + '㎡ · 약 ' + fmt(ev.area * ev.rule.far / 100) + '㎡ <small>예상치</small>' : '–'],
      ['도로접면', ev.road || '–'], ['지형', ((d.ch[0] || {}).tpgrphHgCodeNm || '–') + ' · ' + ((d.ch[0] || {}).tpgrphFrmCodeNm || '–')],
      ['이용상황', (d.ch[0] || {}).ladUseSittnNm || '–'], ['소유 구분', (d.lad[0] || {}).posesnSeCodeNm || '–'],
      ['위반건축물 여부', 'API 미제공 항목 <small>(세움터 확인)</small>']]));
    p2.style.gridRow = '4';
    // ③ 지도(필지 경계 + 브이월드 레이어 켜고 끄기)
    var mb = el('div', { style: 'position:absolute;inset:0' });
    var mwrap = el('div', { style: 'flex:1;min-height:0;border-radius:10px;overflow:hidden;background:#EEF3F8;position:relative' }, [mb]);
    var ll = center(d.feat.geometry);
    var p3 = H.panel('위치 · 필지 경계', (p.jibun || '') + ' · 브이월드 지도', el('div', { style: 'display:flex;flex-direction:column;gap:6px;flex:1;min-height:0' }, [
      layerBar(), mwrap,
      el('div', { class: 'chips', style: 'gap:6px;font-size:13px;flex-wrap:wrap' }, [
        el('a', { class: 'chip', href: 'https://map.ngii.go.kr/ms/map/NlipMap.do', target: '_blank', rel: 'noopener', text: '항공사진 연혁 (국토정보플랫폼) ↗' }),
        el('a', { class: 'chip', href: 'https://map.kakao.com/link/map/' + encodeURIComponent(p.jibun || '부지') + ',' + ll[1] + ',' + ll[0], target: '_blank', rel: 'noopener', text: '카카오맵 과거 스카이뷰 ↗' })])]));
    p3.style.gridRow = '3'; p3.style.gridColumn = '2';
    setTimeout(function () {
      if (!window.L || !window.L.map) return;
      var m = window.L.map(mb, { zoomControl: false, maxZoom: 19 });
      MAP = { m: m, base: null, over: {} };
      setBase(layerState().base);
      try { var g = window.L.geoJSON(d.feat.geometry, { style: { color: S.c, weight: 4, fillOpacity: 0.2 } }).addTo(m); g.bringToFront(); MAP.parcel = g; m.fitBounds(g.getBounds(), { maxZoom: 18, padding: [20, 20] }); } catch (e) { m.setView([ll[1], ll[0]], 16); }
      OVER.forEach(function (o) { if (layerState()[o.k]) setOver(o.k, true); });
    }, 30);
    // ④ 토지이용계획 목록
    var U = d.use.slice().sort(function (a, b) { return String(a.cnflcAt).localeCompare(String(b.cnflcAt)); });
    var p4 = H.panel('토지이용계획 (지역·지구·구역)', '토지이음과 같은 국토이용정보체계 · ' + U.length + '건', U.length ? el('table', { class: 'dt', style: 'font-size:15px' }, [
      el('thead', {}, [el('tr', {}, ['지역·지구·구역', '관계', '등록일'].map(function (h, j) { return el('th', { class: j ? 'r' : '', text: h }); }))]),
      el('tbody', {}, U.map(function (u) { return el('tr', {}, [el('td', { text: u.prposAreaDstrcCodeNm }), el('td', { class: 'r', html: '<b style="color:' + (/저촉/.test(u.cnflcAtNm) ? '#D9534F' : /포함/.test(u.cnflcAtNm) ? '#1B3A6B' : '#556274') + '">' + (u.cnflcAtNm || '') + '</b>' }), el('td', { class: 'r', text: (u.registDt || '').slice(0, 10) })]); }))]) : el('div', { class: 'empty', text: '자료 없음' }));
    p4.style.gridRow = '4'; p4.style.gridColumn = '2';
    // 판정에서 자동으로 못 따지는 조건: 사람이 「해당함/아님」을 누르면 다시 판정
    function qBox(q) {
      var Y = q.kind === 'can' ? '조건 갖춤' : '해당함', N = q.kind === 'can' ? '못 갖춤' : '해당 안 함';
      function b(lbl, v) {
        var on = q.ans === v;
        return el('button', { type: 'button', style: 'font:inherit;font-size:14px;font-weight:800;border-radius:8px;padding:4px 12px;cursor:pointer;border:2px solid #1B3A6B;background:' + (on ? '#1B3A6B' : '#fff') + ';color:' + (on ? '#fff' : '#1B3A6B'),
          text: (on ? '✔ ' : '') + lbl, onclick: function (e) { e.preventDefault(); e.stopPropagation(); if (on) delete qAns[q.id]; else qAns[q.id] = v; cur.ev = evaluate(cur); H.render(); } });
      }
      return el('div', { style: 'margin-top:6px;background:#fff;border:1px dashed #9AA8BA;border-radius:8px;padding:6px 10px' }, [
        el('div', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' }, [
          el('b', { style: 'font-size:15px;color:#1B3A6B', text: '👉 「' + q.text.split('.')[0] + '」 항목의 ' + (q.kind === 'can' ? '조건을 갖추었나요?' : '금지 조건에 해당하나요?') }), b(Y, true), b(N, false)]),
        el('div', { style: 'font-size:13px;color:#38475A;margin-top:4px', text: q.text.length > 140 ? q.text.slice(0, 140) + '…' : q.text })]);
    }
    // ⑤ 판정 근거
    var order = { RED: 0, YELLOW: 1, INFO: 2, GREEN: 3 };
    var list = el('div', { class: 'landlist', style: 'display:flex;flex-direction:column;gap:8px;min-height:0' }, ev.reasons.slice().sort(function (a, b) { return (b.pin ? 1 : 0) - (a.pin ? 1 : 0) || order[a.level] - order[b.level]; }).map(function (r) {
      var L = LV[r.level], det = el('details', { 'data-fit': '1', style: 'border-left:5px solid ' + L.c + ';background:' + L.bg + ';border-radius:8px;padding:8px 12px' }, [
        el('summary', { style: 'cursor:pointer;font-size:16px;font-weight:800;color:#1B3A6B', html: '<span style="color:' + L.c + '">●</span> [' + r.area + '] ' + r.tag }),
      ].concat((r.qs || []).map(qBox)).concat([
        el('div', { style: 'font-size:15px;margin-top:6px', text: r.detail }),
        el('div', { style: 'font-size:15px;margin-top:4px;font-weight:700', text: '→ ' + r.impact }),
        r.cite ? el('div', { style: 'font-size:13px;margin-top:4px;color:#556274', text: '근거: ' + r.cite }) : null]));
      if (r.pin) { det.open = true; det.removeAttribute('data-fit'); det.style.maxHeight = '300px'; det.style.overflow = 'auto'; det.style.flexShrink = '0'; }   // 예정 용도: 숨기지 말고 맨 위에(길면 칸 안에서 굴림)
      if (r.area === '토지' && /건폐율/.test(r.detail) && artText('bcr')) det.appendChild(el('div', { style: 'font-size:12px;margin-top:6px;color:#38475A;white-space:pre-wrap;max-height:120px;overflow:auto;background:#fff;padding:6px;border-radius:6px', text: '[조례 원문] ' + artText('bcr') + '\n\n' + artText('far') }));
      return det; }));
    var p5 = H.panel('판정 근거 · 확인할 것', '빨강·노랑부터 · 눌러서 근거 조문 보기', [list].concat(d.errs.length ? [el('div', { class: 'chips', style: 'margin-top:8px;gap:6px;flex-wrap:wrap' }, d.errs.map(function (e) { return el('span', { class: 'chip bad', text: e }); }))] : []));
    p5.style.gridRow = '4'; p5.style.gridColumn = '3';
    setTimeout(function () { Array.prototype.forEach.call(H.view.querySelectorAll('section.zoom details'), function (x) { x.open = true; }); }, 0);   // 크게 보기: 근거를 모두 펼침
    // ⑥ 건물 정보(건축물대장): 어떤 건물인지, 언제 지었는지
    var d8 = function (v) { v = String(v || '').trim(); return v.length >= 8 ? v.slice(0, 4) + '.' + v.slice(4, 6) + '.' + v.slice(6, 8) : '–'; };
    var bbody;
    if (d.bld && d.bld._err) bbody = el('div', { class: 'empty', style: 'color:#D9534F', text: '건축물대장 조회 실패: ' + d.bld._err });
    else if (!B.length && d.bld && ((d.bld.title || {}).error || (d.bld.recap || {}).error)) bbody = el('div', { class: 'empty', style: 'color:#D9534F' }, [
      el('div', { text: '건축물대장 조회 실패: ' + ((d.bld.title || {}).error || (d.bld.recap || {}).error) }),
      el('button', { type: 'button', class: 'chip', style: 'margin-top:8px;cursor:pointer;border:0;font-weight:800', text: '↻ 다시 조회', onclick: function () { lookup(d.pnu); } })]);
    else if (!B.length) bbody = el('div', { class: 'empty', text: '건축물대장에 등록된 건물이 없습니다(나대지 또는 미등재).' });
    else bbody = el('div', { class: 'landlist', style: 'min-height:0;display:flex;flex-direction:column;gap:8px' }, B.map(function (b) {
      var oldC = b.age != null && b.age >= 30 ? '#D9534F' : '#1B3A6B';
      return el('div', { 'data-fit': '1', style: 'border:1px solid #DDE3EC;border-radius:10px;padding:8px 12px' }, [
        el('div', { style: 'display:flex;justify-content:space-between;gap:8px;align-items:baseline' }, [
          el('div', { style: 'font-size:18px;font-weight:900;color:#1B3A6B', text: (b.name || '(건물명 없음)') + (b.main ? ' · ' + b.main : '') }),
          el('div', { style: 'font-size:17px;font-weight:900;color:' + oldC, text: b.age != null ? b.age + '년 경과' : '' })]),
        el('div', { style: 'font-size:15px;margin-top:3px', html: '<b>' + (b.use || '용도 미기재') + '</b> · ' + (b.struct || '구조 미기재') + ' · 지상 ' + (b.floors || 0) + '층' + (+b.under ? '/지하 ' + b.under + '층' : '') + (+b.height ? ' · 높이 ' + fmt(b.height, 1) + 'm' : '') }),
        el('div', { style: 'font-size:14px;color:#38475A;margin-top:3px', text: '사용승인 ' + (b.approve || '–') + ' · 허가 ' + d8(b.permit) + ' · 착공 ' + d8(b.start) }),
        el('div', { style: 'font-size:14px;color:#38475A', text: '연면적 ' + fmt(b.tot) + '㎡ · 건축면적 ' + fmt(b.arch) + '㎡' + (+b.bc ? ' · 건폐율 ' + fmt(b.bc, 1) + '%' : '') + (+b.vl ? ' · 용적률 ' + fmt(b.vl, 1) + '%' : '') }),
        el('div', { style: 'font-size:14px;color:#38475A', text: (+b.hhld ? '세대 ' + b.hhld + ' · ' : '') + (+b.ho ? '호 ' + b.ho + ' · ' : '') + '주차 ' + (b.park || 0) + '대 · 승강기 ' + (b.elev || 0) + '대 · 내진설계 ' + (b.earthquake === '1' ? '적용' : b.earthquake === '0' ? '미적용' : '미기재') + (b.eqAbility && String(b.eqAbility).trim() ? ' (' + b.eqAbility + ')' : '') })]); }));
    var recap = ((d.bld || {}).recap || {}).items || [];
    var p6 = H.panel('건물 정보 · 건축물대장', B.length ? B.length + '동' + (recap.length ? ' · 총괄표제부 있음' : '') + ' · 건축HUB' : '건축HUB', bbody);
    p6.style.gridRow = '3'; p6.style.gridColumn = '3';
  }

  function screenOrd(el) {
    var O = ((H.D.life || {}).ordin) || {}, R = O.regions || {};
    if (!Object.keys(R).length) { full(el('div', { class: 'empty', style: 'font-size:22px', text: '조례 자료를 받는 중입니다(하루 한 번 수집)' })); return; }
    var me = R[H.D.me] || {}, zones = Object.keys(me.far || me.bcr || {});
    if (!cmpZone || zones.indexOf(cmpZone) < 0) cmpZone = zones.indexOf('제2종일반주거지역') >= 0 ? '제2종일반주거지역' : zones[0];
    var k = cmpKind, unit = '%';
    var vals = {}; Object.keys(R).forEach(function (n) { var v = (R[n][k] || {})[cmpZone]; if (v != null) vals[n] = v; });
    var names = Object.keys(vals).sort(function (a, b) { return vals[b] - vals[a]; }), rank = 0, prev = null;
    var I = { id: 'ord', name: cmpZone, unit: unit, digits: 0, n: names.length, ranking: names.map(function (n, i) { if (vals[n] !== prev) rank = i + 1; prev = vals[n]; return { name: n, value: vals[n], rank: rank, judge: 'excluded' }; }) };
    I.me = I.ranking.filter(function (x) { return x.name === H.D.me; })[0];
    var sw = el('div', { class: 'chips', style: 'gap:6px;margin-bottom:6px;flex-wrap:nowrap' }, [['far', '용적률'], ['bcr', '건폐율']].map(function (x) {
      return el('button', { type: 'button', class: 'chip', style: 'cursor:pointer;border:0;font-weight:800' + (k === x[0] ? ';background:#1B3A6B;color:#fff' : ''), text: x[1], onclick: function () { cmpKind = x[0]; H.render(); } }); }));
    var p1 = H.panel((k === 'far' ? '용적률' : '건폐율') + ' · ' + cmpZone + ' · 강원 ' + names.length + '개 시·군', '각 시·군 도시계획 조례 원문 · 높은 순', [sw, H.rankList(I, null, null)]);
    p1.style.gridRow = '2 / span 3';
    var avg = function (kk, z) { var t = 0, c = 0; Object.keys(R).forEach(function (n) { var v = (R[n][kk] || {})[z]; if (v != null) { t += v; c++; } }); return c ? t / c : null; };
    var tb = el('table', { class: 'dt', style: 'font-size:15px' }, [el('thead', {}, [el('tr', {}, ['용도지역', '동해 건폐율', '도내 평균', '동해 용적률', '도내 평균', '도내 범위(용적률)'].map(function (h, j) { return el('th', { class: j ? 'r' : '', text: h }); }))]),
      el('tbody', {}, zones.map(function (z) {
        var fv = Object.keys(R).map(function (n) { return (R[n].far || {})[z]; }).filter(function (v) { return v != null; });
        return el('tr', { style: 'cursor:pointer' + (z === cmpZone ? ';background:#E4EEFB' : ''), onclick: function () { cmpZone = z; H.render(); } }, [el('td', { html: '<b>' + z + '</b>' }),
          el('td', { class: 'r', text: fmt((me.bcr || {})[z]) + '%' }), el('td', { class: 'r', text: fmt(avg('bcr', z), 1) + '%' }),
          el('td', { class: 'r', html: '<b>' + fmt((me.far || {})[z]) + '%</b>' }), el('td', { class: 'r', text: fmt(avg('far', z), 1) + '%' }),
          el('td', { class: 'r', text: fv.length ? fmt(Math.min.apply(null, fv)) + '~' + fmt(Math.max.apply(null, fv)) + '%' : '–' })]); }))]);
    var p2 = H.panel('용도지역별 건폐율·용적률 · ' + (me.name || ''), (me.date ? me.date.replace(/(\d{4})(\d\d)(\d\d)/, '$1.$2.$3') + ' 시행 · ' : '') + (me.bcr_art ? me.bcr_art.no + '·' : '') + (me.far_art ? me.far_art.no : '') + ' · 줄을 누르면 왼쪽 비교', el('div', { style: 'overflow:auto;min-height:0' }, [tb]));
    p2.style.gridColumn = '2 / span 2'; p2.style.gridRow = '2 / span 3';
  }

  // ------------------------------------------------------------ 1장 브리핑(인쇄)
  function briefing(d) {
    var ev = d.ev, S = LV[ev.status], p = d.feat.properties || {}, hl = headline(d), o = ordMe() || {};
    var esc = function (t) { return String(t == null ? '' : t).replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); };
    var rows = ev.reasons.slice().sort(function (a, b) { return ({ RED: 0, YELLOW: 1, INFO: 2, GREEN: 3 })[a.level] - ({ RED: 0, YELLOW: 1, INFO: 2, GREEN: 3 })[b.level]; });
    var w = window.open('', '_blank');
    if (!w) return;
    w.document.write('<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>부지 검토 브리핑 · ' + esc(p.addr || d.q) + '</title><style>' +
      'body{font-family:"Malgun Gothic",sans-serif;margin:24px;color:#1D2733;font-size:13px}h1{font-size:20px;margin:0 0 4px;color:#1B3A6B}h2{font-size:15px;color:#1B3A6B;margin:16px 0 6px;border-bottom:2px solid #1B3A6B;padding-bottom:3px}' +
      'table{width:100%;border-collapse:collapse}td,th{border:1px solid #C9D2DE;padding:5px 7px;text-align:left;vertical-align:top}th{background:#EEF2F8;width:22%}.lv{display:inline-block;padding:3px 12px;border-radius:12px;color:#fff;font-weight:800}' +
      'ol{margin:6px 0;padding-left:20px;line-height:1.6}.small{color:#556274;font-size:11px}@media print{button{display:none}}</style></head><body>' +
      '<button onclick="print()" style="float:right;padding:6px 14px">인쇄</button>' +
      '<h1>부지 검토 브리핑</h1><div class="small">' + esc(new Date().toLocaleString('ko-KR', { hour12: false })) + ' · 동해시 AI 시장실</div>' +
      '<h2>1. 대상지</h2><table><tr><th>소재지</th><td>' + esc(p.addr || d.q) + '</td></tr><tr><th>PNU</th><td>' + d.pnu + '</td></tr><tr><th>용도지역 · 지목 · 면적</th><td>' + esc(ev.zones.join(' · ') || '–') + ' · ' + esc(ev.jimok) + ' · ' + fmt(ev.area) + '㎡</td></tr>' +
      '<tr><th>공시지가</th><td>' + (ev.price ? fmt(ev.price) + '원/㎡ (' + esc(ev.priceYear) + '년)' : '–') + '</td></tr>' + (useSel ? '<tr><th>예정 용도</th><td>' + esc(useSel + (useSub ? '(' + useSub + ')' : '') + (inArea ? ' · 바닥면적 ' + fmt(inArea) + '㎡' : '') + (inFloor ? ' · ' + inFloor + '층' : '') + (inRoad ? ' · 도로 ' + inRoad + 'm' : '')) + '</td></tr>' : '') + '</table>' +
      '<h2>2. 종합 판정</h2><p><span class="lv" style="background:' + S.c + '">' + { GREEN: '초록', YELLOW: '노랑', RED: '빨강' }[ev.status] + '</span> <b>' + S.t + '</b></p><ol>' + hl.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ol>' +
      '<h2>3. 항목별 판정과 근거</h2><table><tr><th style="width:9%">판정</th><th style="width:22%">항목</th><th>내용 · 영향</th><th style="width:24%">근거</th></tr>' +
      rows.map(function (r) { return '<tr><td style="color:' + LV[r.level].c + ';font-weight:800">' + { GREEN: '초록', YELLOW: '노랑', RED: '빨강', INFO: '참고' }[r.level] + '</td><td>[' + esc(r.area) + '] ' + esc(r.tag) + '</td><td>' + esc(r.detail) + '<br><b>→ ' + esc(r.impact) + '</b></td><td class="small">' + esc(r.cite) + '</td></tr>'; }).join('') + '</table>' +
      '<h2>4. 규모 검토(조례 기준)</h2><table><tr><th>건폐율 · 용적률</th><td>' + (ev.rule ? fmt(ev.rule.bcr) + '% · ' + fmt(ev.rule.far) + '% (' + esc(o.name || '') + ' ' + esc(((o.bcr_art || {}).no || '')) + '·' + esc(((o.far_art || {}).no || '')) + ')' : '–') + '</td></tr>' +
      '<tr><th>최대 바닥면적 · 연면적</th><td>' + (ev.rule ? '약 ' + fmt(ev.area * ev.rule.bcr / 100) + '㎡ · 약 ' + fmt(ev.area * ev.rule.far / 100) + '㎡ (예상치: 높이·일조·주차 기준 미반영)' : '–') + '</td></tr></table>' +
      '<h2>5. 원본 자료</h2><div class="small">토지이음 ' + eumUrl(d.pnu) + '<br>자료: 브이월드 토지이용계획·토지특성·토지대장, 건축HUB 건축물대장, 국가법령정보센터 ' + esc(o.name || '') + ' (' + esc(o.date || '') + ' 시행)</div>' +
      '</body></html>');
    w.document.close();
  }

  return { screen: screen };
})();
