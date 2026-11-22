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
  var tab = 'site', cur = null, busy = false, cmpZone = null, cmpKind = 'far', useSel = '';
  var LV = { GREEN: { c: '#2E8B57', bg: '#E2F3E9', t: '추진 가능' }, YELLOW: { c: '#D99A00', bg: '#FFF4D6', t: '조건부 가능 · 검토 필요' }, RED: { c: '#D9534F', bg: '#FDE7E4', t: '추진 곤란 · 중대 제약' }, INFO: { c: '#1F6FD1', bg: '#E4EEFB', t: '참고' } };
  var USES = ['', '단독주택', '공동주택', '제1종근린생활시설', '제2종근린생활시설', '문화및집회시설', '판매시설', '의료시설', '교육연구시설', '노유자시설', '수련시설', '운동시설', '업무시설', '숙박시설', '공장', '창고시설', '위험물저장및처리시설', '자동차관련시설', '공공용시설', '관광휴게시설', '주차장'];

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
        (sb ? sb.functions.invoke('land', { body: { pnu: pnu } }) : Promise.reject(new Error('연결 설정 없음'))).then(function (r) { return r.error ? { _err: r.error.message } : r.data; }).catch(function (e) { return { _err: e.message }; })
      ]).then(function (res) {
        var d = { q: q, pnu: pnu, feat: f, use: arr(((res[0] || {}).landUses || {}).field), ch: arr(((res[1] || {}).landCharacteristicss || {}).field), lad: arr(((res[2] || {}).ladfrlVOList || {}).ladfrlVOList), bld: res[3] || {},
          errs: [res[0] && res[0]._err ? '토지이용계획: ' + res[0]._err : null, res[1] && res[1]._err ? '토지특성: ' + res[1]._err : null, res[2] && res[2]._err ? '토지대장: ' + res[2]._err : null, res[3] && res[3]._err ? '건축물대장: ' + res[3]._err : null].filter(Boolean) };
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
    [/(상수원보호구역|수변구역)/, 'YELLOW', '「수도법」 제7조', '상수원보호구역', '오염 우려 시설·행위가 제한됩니다.'],
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
    if (useSel) add('INFO', '토지', '예정 용도: ' + useSel, '「' + zone + '」에서 「' + useSel + '」을(를) 지을 수 있는지는 동해시 도시계획 조례 별표(용도지역별 건축 가능 건축물)에 있습니다.', '아래 「별표 원문」에서 해당 용도지역 표를 확인하세요. (별표는 한글 파일이라 자동 판정하지 않음)', annexFor(zone) ? annexFor(zone).title : '동해시 도시계획 조례 별표');
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
    var t = (bld && bld.title && bld.title.items) || [];
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
    var sel = el('select', { style: 'font:inherit;font-size:16px;padding:9px;border:2px solid #C9D2DE;border-radius:10px' }, USES.map(function (u) { var o = el('option', { value: u, text: u || '예정 용도(선택)' }); if (u === useSel) o.selected = true; return o; }));
    sel.addEventListener('change', function () { useSel = sel.value; if (cur && cur.ev) { cur.ev = evaluate(cur); H.render(); } });
    var recent = recentGet().slice(0, 5);
    var bar = el('section', { style: 'grid-column:1 / -1;grid-row:2;flex-direction:row;align-items:center;gap:10px;padding:10px 14px' }, [inp, sel,
      el('button', { type: 'button', style: 'font:inherit;font-weight:800;font-size:18px;background:#1B3A6B;color:#fff;border:0;border-radius:10px;padding:10px 22px;cursor:pointer', text: busy ? '조회 중…' : '검토', onclick: function () { lookup(inp.value); } }),
      recent.length ? el('div', { class: 'chips', style: 'flex-wrap:nowrap;gap:6px;max-width:42%;overflow:hidden' }, recent.map(function (h) {
        return el('button', { type: 'button', class: 'chip', style: 'cursor:pointer;border:0;white-space:nowrap;background:' + LV[h.status || 'INFO'].bg + ';color:' + LV[h.status || 'INFO'].c, text: '● ' + String(h.address || h.pnu).replace(/^강원특별자치도\s*동해시\s*/, ''), onclick: function () { lookup(h.pnu); } }); })) : null]);
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
    // ③ 지도(필지 경계)
    var mb = el('div', { style: 'flex:1;min-height:0;border-radius:10px;overflow:hidden;background:#EEF3F8' });
    var p3 = H.panel('위치 · 필지 경계', (p.jibun || '') + ' · 브이월드 지도', mb);
    p3.style.gridRow = '3'; p3.style.gridColumn = '2';
    setTimeout(function () {
      if (!window.L || !window.L.map) return;
      var m = window.L.map(mb, { zoomControl: false });
      H.baseLayer().addTo(m);
      try { var g = window.L.geoJSON(d.feat.geometry, { style: { color: S.c, weight: 4, fillOpacity: 0.25 } }).addTo(m); m.fitBounds(g.getBounds(), { maxZoom: 18, padding: [20, 20] }); } catch (e) { m.setView([37.52, 129.11], 16); }
    }, 30);
    // ④ 토지이용계획 목록
    var U = d.use.slice().sort(function (a, b) { return String(a.cnflcAt).localeCompare(String(b.cnflcAt)); });
    var p4 = H.panel('토지이용계획 (지역·지구·구역)', '토지이음과 같은 국토이용정보체계 · ' + U.length + '건', U.length ? el('table', { class: 'dt', style: 'font-size:15px' }, [
      el('thead', {}, [el('tr', {}, ['지역·지구·구역', '관계', '등록일'].map(function (h, j) { return el('th', { class: j ? 'r' : '', text: h }); }))]),
      el('tbody', {}, U.map(function (u) { return el('tr', {}, [el('td', { text: u.prposAreaDstrcCodeNm }), el('td', { class: 'r', html: '<b style="color:' + (/저촉/.test(u.cnflcAtNm) ? '#D9534F' : /포함/.test(u.cnflcAtNm) ? '#1B3A6B' : '#556274') + '">' + (u.cnflcAtNm || '') + '</b>' }), el('td', { class: 'r', text: (u.registDt || '').slice(0, 10) })]); }))]) : el('div', { class: 'empty', text: '자료 없음' }));
    p4.style.gridRow = '4'; p4.style.gridColumn = '2';
    // ⑤ 판정 근거
    var order = { RED: 0, YELLOW: 1, INFO: 2, GREEN: 3 };
    var list = el('div', { class: 'landlist', style: 'display:flex;flex-direction:column;gap:8px;min-height:0' }, ev.reasons.slice().sort(function (a, b) { return order[a.level] - order[b.level]; }).map(function (r) {
      var L = LV[r.level], det = el('details', { 'data-fit': '1', style: 'border-left:5px solid ' + L.c + ';background:' + L.bg + ';border-radius:8px;padding:8px 12px' }, [
        el('summary', { style: 'cursor:pointer;font-size:16px;font-weight:800;color:#1B3A6B', html: '<span style="color:' + L.c + '">●</span> [' + r.area + '] ' + r.tag }),
        el('div', { style: 'font-size:15px;margin-top:6px', text: r.detail }),
        el('div', { style: 'font-size:15px;margin-top:4px;font-weight:700', text: '→ ' + r.impact }),
        r.cite ? el('div', { style: 'font-size:13px;margin-top:4px;color:#556274', text: '근거: ' + r.cite }) : null]);
      if (r.area === '토지' && /건폐율/.test(r.detail) && artText('bcr')) det.appendChild(el('div', { style: 'font-size:12px;margin-top:6px;color:#38475A;white-space:pre-wrap;max-height:120px;overflow:auto;background:#fff;padding:6px;border-radius:6px', text: '[조례 원문] ' + artText('bcr') + '\n\n' + artText('far') }));
      return det; }));
    var p5 = H.panel('판정 근거 · 확인할 것', '빨강·노랑부터 · 눌러서 근거 조문 보기', [list].concat(d.errs.length ? [el('div', { class: 'chips', style: 'margin-top:8px;gap:6px;flex-wrap:wrap' }, d.errs.map(function (e) { return el('span', { class: 'chip bad', text: e }); }))] : []));
    p5.style.gridRow = '4'; p5.style.gridColumn = '3';
    setTimeout(function () { Array.prototype.forEach.call(H.view.querySelectorAll('section.zoom details'), function (x) { x.open = true; }); }, 0);   // 크게 보기: 근거를 모두 펼침
    // ⑥ 건물 정보(건축물대장): 어떤 건물인지, 언제 지었는지
    var d8 = function (v) { v = String(v || '').trim(); return v.length >= 8 ? v.slice(0, 4) + '.' + v.slice(4, 6) + '.' + v.slice(6, 8) : '–'; };
    var bbody;
    if (d.bld && d.bld._err) bbody = el('div', { class: 'empty', style: 'color:#D9534F', text: '건축물대장 조회 실패: ' + d.bld._err });
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
      '<tr><th>공시지가</th><td>' + (ev.price ? fmt(ev.price) + '원/㎡ (' + esc(ev.priceYear) + '년)' : '–') + '</td></tr>' + (useSel ? '<tr><th>예정 용도</th><td>' + esc(useSel) + '</td></tr>' : '') + '</table>' +
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
