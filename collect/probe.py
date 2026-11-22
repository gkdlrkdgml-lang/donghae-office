"""점검 스크립트: 키를 넣은 뒤 한 번 실행합니다.

각 API를 동해시 기준으로 한 번씩 불러서
  - 성공/실패, 오류 코드
  - 응답에 들어 있는 항목 이름(영문) 목록
  - 첫 번째 줄 예시
를 화면에 보여주고 probe_결과.txt 로 저장합니다. 이 파일을 Claude에게 보내 주시면 settings.json을 맞춰 드립니다.
(키 값은 파일에 남기지 않습니다.)
"""
import json
import urllib.parse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (settings, codes, load_env, http_get, parse_body, find_items, check_error, ym_shift, now, ROOT)  # noqa: E402

lines = []


def say(s=''):
    print(s)
    lines.append(s)


def probe(name, src, extra):
    say('=' * 70)
    say('[%s] %s' % (name, src.get('url') or '(주소 없음)'))
    key = os.environ.get(src.get('key_env', ''), '').strip()
    say('  키 형태: 길이 %d, %%포함=%s, 끝이 ==: %s' % (len(key), '%' in key, key.endswith('==')))
    if '%' in key:
        import urllib.parse
        key = urllib.parse.unquote(key)
    if not key:
        say('  → .env에 %s 가 없습니다' % src.get('key_env'))
        return
    if not src.get('url'):
        say('  → settings.json에 요청 주소가 아직 없습니다')
        return
    params = dict(src.get('params', {}))
    params.update(extra)
    params[src.get('key_param', 'serviceKey')] = key
    if 'numOfRows' in params:
        params['numOfRows'] = '5'
    if 'pSize' in params:
        params['pSize'] = '5'
    try:
        text = http_get(src['url'], params, tries=1)
    except Exception as e:  # noqa: BLE001
        say('  → 호출 실패: %s' % e)
        return
    say('  응답 앞부분: ' + text[:1500].replace(key, '***').replace('\n', ' '))
    try:
        obj = parse_body(text)
    except Exception as e:  # noqa: BLE001
        say('  → 응답을 읽지 못함: %s' % e)
        return
    err = check_error(obj)
    if err:
        say('  → 오류 코드: %s' % err)
        return
    items = find_items(obj)
    say('  목록 %d건' % len(items))
    if items:
        say('  항목 이름: ' + ', '.join(items[0].keys()))
        say('  첫 줄: ' + json.dumps(items[0], ensure_ascii=False)[:800])


def kepco_probe():
    kp = os.environ.get('KEPCO_KEY', '').strip()
    say('[한전] 키 길이 %d' % len(kp))
    if not kp:
        return
    B = 'https://bigdata.kepco.co.kr/openapi/v1/'
    tests = [('코드-시도', 'commonCode.do', {'codeTy': 'metroCd'}),
             ('코드-시군', 'commonCode.do', {'codeTy': 'cityCd'}),
             ('코드-계약', 'commonCode.do', {'codeTy': 'cntrCd'}),
             ('코드-발전원', 'commonCode.do', {'codeTy': 'genSrcCd'})]
    for y, m in (('2026', '10'), ('2026', '09'), ('2026', '06'), ('2025', '12')):
        tests += [('가구평균 %s%s' % (y, m), 'powerUsage/houseAve.do', {'year': y, 'month': m, 'metroCd': '51'}),
                  ('계약종별 %s%s' % (y, m), 'powerUsage/contractType.do', {'year': y, 'month': m, 'metroCd': '51'}),
                  ('산업분류 %s%s' % (y, m), 'powerUsage/industryType.do', {'year': y, 'month': m, 'metroCd': '51'})]
    for y in ('2026', '2025'):
        tests += [('신재생 %s' % y, 'renewEnergy.do', {'year': y, 'metroCd': '51'})]
    for nm, path, prm in tests:
        try:
            q = dict(prm); q.update({'apiKey': kp, 'returnType': 'json'})
            t = http_get(B + path, q, tries=1, timeout=30)
            say('[한전] %s → %s' % (nm, t[:1500].replace(kp, '***').replace('\n', ' ')))
        except Exception as e:  # noqa: BLE001
            say('[한전] %s 실패 %s' % (nm, str(e)[:250]))


def supabase_probe():
    import admin_sync, urllib.request as ur
    key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
    h = {'apikey': key, 'Accept': 'application/json', 'User-Agent': 'donghae-office-collector/1.0'}
    for path in ('profiles?select=login_id,name,dept,role,scopes,created_at&order=created_at',
                 'entries?select=id,ref_date,section,author_name,deleted,created_at&order=created_at.desc&limit=20'):
        try:
            with ur.urlopen(ur.Request(admin_sync._url() + '/rest/v1/' + path, headers=h), timeout=30) as r:
                say('[supabase] %s → %s' % (path.split('?')[0], r.read().decode('utf-8')[:3000]))
        except Exception as e:  # noqa: BLE001
            say('[supabase] %s 실패 %s' % (path.split('?')[0], e))


def supabase_test(mode):
    """연결 시험: 공식 값과 같은 숫자로 공식 기준월 말일 입력을 넣었다 지움(화면 값은 바뀌지 않음)."""
    import admin_sync, urllib.request as ur
    key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
    h = {'apikey': key, 'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'donghae-office-collector/1.0', 'Prefer': 'return=representation'}
    base = admin_sync._url() + '/rest/v1/'
    def call(method, path, body=None):
        req = ur.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
        with ur.urlopen(req, timeout=30) as r:
            return r.read().decode('utf-8')
    if mode == 'add':
        st = json.load(open(os.path.join(ROOT, 'web', 'data', 'state.json'), encoding='utf-8'))
        A = st['admin']; ym = A['ym']; tot = A['regions']['동해']['total']
        import calendar
        d = '%s-%s-%02d' % (ym[:4], ym[4:], calendar.monthrange(int(ym[:4]), int(ym[4:]))[1])
        uid = json.loads(call('GET', 'profiles?select=id&role=eq.super&limit=1'))[0]['id']
        say('[supabase-test] 추가 → ' + call('POST', 'entries', {'ref_date': d, 'section': 'pop', 'data': {'total': tot}, 'author': uid, 'author_name': '연결 시험'}))
    else:
        say('[supabase-test] 삭제 → ' + call('DELETE', 'entries?author_name=eq.' + __import__('urllib.parse').parse.quote('연결 시험')))


def land_probe():
    """국토·건축: 브이월드(지오코더·연속지적·토지이용계획·토지특성·토지임야), 건축HUB 건축물대장, 국가법령 조례."""
    import urllib.parse as up
    S = settings()
    vk = (S.get('map') or {}).get('vworld_key', '')
    dom = 'https://gkdlrkdgml-lang.github.io'
    def vw(url, prm, tag):
        q = dict(prm); q.update({'key': vk, 'domain': dom})
        try:
            t = http_get(url, q, tries=1, timeout=30)
            say('[land] %s → %s' % (tag, t[:1500].replace(vk, '***').replace('\n', ' ')))
            return t
        except Exception as e:  # noqa: BLE001
            say('[land] %s 실패 %s' % (tag, str(e)[:300]))
            return ''
    t = vw('https://api.vworld.kr/req/address', {'service': 'address', 'request': 'getcoord', 'version': '2.0', 'crs': 'epsg:4326', 'address': '강원특별자치도 동해시 천곡로 77', 'refine': 'true', 'simple': 'false', 'format': 'json', 'type': 'road'}, '지오코더')
    x, y = '129.1143', '37.5247'   # 지오코더 실패 시 동해시청 근처 좌표
    try:
        pt = json.loads(t)['response']['result']['point']; x, y = pt['x'], pt['y']
    except Exception:  # noqa: BLE001
        pass
    vw('https://api.vworld.kr/req/wmts/1.0.0/%s/Base/7/48/109.png' % vk, {}, 'WMTS 연결확인')
    pnu = ''
    if x:
        t = vw('https://api.vworld.kr/req/data', {'service': 'data', 'request': 'GetFeature', 'data': 'LP_PA_CBND_BUBUN', 'geomFilter': 'POINT(%s %s)' % (x, y), 'format': 'json', 'size': '1', 'geometry': 'false', 'attribute': 'true', 'crs': 'EPSG:4326'}, '연속지적')
        try:
            pnu = json.loads(t)['response']['result']['featureCollection']['features'][0]['properties']['pnu']
        except Exception:  # noqa: BLE001
            pass
        vw('https://api.vworld.kr/req/data', {'service': 'data', 'request': 'GetFeature', 'data': 'LT_C_UQ111', 'geomFilter': 'POINT(%s %s)' % (x, y), 'format': 'json', 'size': '5', 'geometry': 'false', 'attribute': 'true', 'crs': 'EPSG:4326'}, '용도지역레이어')
    pnu = pnu or '5117010100108060000'   # 동해시청(천곡동 806), 브라우저 시험에서 확인
    say('[land] PNU=%s' % pnu)
    if pnu:
        vw('https://api.vworld.kr/ned/data/getLandUseAttr', {'pnu': pnu, 'format': 'json', 'numOfRows': '50', 'pageNo': '1'}, '토지이용계획')
        for yr in ('2026', '2025'):
            vw('https://api.vworld.kr/ned/data/getLandCharacteristics', {'pnu': pnu, 'stdrYear': yr, 'format': 'json', 'numOfRows': '5', 'pageNo': '1'}, '토지특성 %s' % yr)
        vw('https://api.vworld.kr/ned/data/ladfrlList', {'pnu': pnu, 'format': 'json', 'numOfRows': '5', 'pageNo': '1'}, '토지임야')
        dk = up.unquote(os.environ.get('DATA_GO_KR_KEY', '').strip())
        prm = {'serviceKey': dk, 'sigunguCd': pnu[:5], 'bjdongCd': pnu[5:10], 'platGbCd': '0' if pnu[10] == '1' else '1', 'bun': pnu[11:15], 'ji': pnu[15:19], '_type': 'json', 'numOfRows': '5', 'pageNo': '1'}
        for op in ('getBrTitleInfo', 'getBrBasisOulnInfo'):
            try:
                t = http_get('https://apis.data.go.kr/1613000/BldRgstHubService/' + op, prm, tries=1, timeout=40)
                say('[land] 건축물대장 %s → %s' % (op, t[:1800].replace(dk, '***')))
            except Exception as e:  # noqa: BLE001
                say('[land] 건축물대장 %s 실패 %s' % (op, str(e)[:300]))
    oc = os.environ.get('LAW_OC', '').strip()
    say('[land] LAW_OC 길이 %d' % len(oc))
    if oc:
        for q in ('동해시 도시계획 조례', '동해시 건축 조례'):
            try:
                t = http_get('https://www.law.go.kr/DRF/lawSearch.do', {'OC': oc, 'target': 'ordin', 'type': 'JSON', 'query': q, 'display': '5'}, tries=1, timeout=30)
                say('[land] 조례검색 %s → %s' % (q, t[:2500].replace('\\n', ' ').replace('\n', ' ')))
            except Exception as e:  # noqa: BLE001
                say('[land] 조례검색 %s 실패 %s' % (q, str(e)[:300]))


def ordin_probe():
    oc = os.environ.get('LAW_OC', '').strip()
    t = http_get('https://www.law.go.kr/DRF/lawService.do', {'OC': oc, 'target': 'ordin', 'MST': '2091767', 'type': 'JSON'}, tries=2, timeout=60)
    os.makedirs(os.path.join(ROOT, 'probe_out'), exist_ok=True)
    open(os.path.join(ROOT, 'probe_out', 'ordin.json'), 'w', encoding='utf-8').write(t)
    say('[ordin] 길이 %d 앞 %s' % (len(t), t[:600].replace('\n', ' ')))
    j = json.loads(t)['LawService']
    say('[ordin] 키 %s' % list(j.keys()))
    jo = j.get('조문') or {}
    say('[ordin] 조문 키 %s' % (list(jo.keys()) if isinstance(jo, dict) else type(jo)))
    arts = jo.get('조') if isinstance(jo, dict) else jo
    arts = arts if isinstance(arts, list) else [arts]
    say('[ordin] 조 개수 %d, 첫 조 키 %s' % (len(arts), list(arts[0].keys()) if arts and isinstance(arts[0], dict) else arts[:1]))
    for a in arts:
        txt = json.dumps(a, ensure_ascii=False)
        if '건폐율' in txt[:200] or '용적률' in txt[:200]:
            say('[ordin] 조문 %s' % txt[:4000])
    say('[ordin] 별표 %s' % json.dumps(j.get('별표') or '', ensure_ascii=False)[:1500])


def lock_probe():
    import urllib.request, urllib.error, random
    def code(url, data=None, h=None):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h or {}), timeout=30)
            return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()[:300]
    site = 'https://gkdlrkdgml-lang.github.io/donghae-office/'
    for u in ['', 'auth.js', 'data/data.js', 'data/state.json', 'data/stores_snap.json']:
        say('공개 사이트 %s → %s' % (u or '(첫 화면)', code(site + u + '?x=%d' % random.randint(1, 9999))[0]))
    sb = 'https://zkdsystvrakicrkckcrd.supabase.co'
    k = 'sb_publishable_EA-Zz_6YVEloxXYANEgZoQ_81RAqrv0'
    say('익명 저장소 읽기 → %s %s' % code(sb + '/storage/v1/object/dash/data/data.json.gz', h={'apikey': k}))
    say('공개 주소 읽기 → %s %s' % code(sb + '/storage/v1/object/public/dash/data/data.json.gz'))
    say('land 익명 → %s %s' % code(sb + '/functions/v1/land', b'{"pnu":"5117010100108060000"}', {'apikey': k, 'Content-Type': 'application/json', 'Origin': 'https://gkdlrkdgml-lang.github.io'}))
    sk = os.environ.get('SUPABASE_SERVICE_KEY', '')
    st, b = code(sb + '/storage/v1/object/dash/data/version.txt', h={'apikey': sk})
    say('서버 키 version.txt → %s %s' % (st, b[:40]))
    # 임시 보기 전용 계정으로 실제 로그인 → 자료 받기 → 계정 삭제
    import json as J, secrets
    ah = {'apikey': sk, 'Content-Type': 'application/json'}
    em, pw = 'zz_locktest_%d@dh-office.local' % random.randint(1000, 9999), secrets.token_urlsafe(16)
    st, b = code(sb + '/auth/v1/admin/users', J.dumps({'email': em, 'password': pw, 'email_confirm': True, 'user_metadata': {'login_id': em.split('@')[0], 'name': '잠금시험'}}).encode(), ah)
    uid = J.loads(b if st == 200 else b'{}').get('id') if st == 200 else None
    if not uid:
        r = urllib.request.urlopen(urllib.request.Request(sb + '/auth/v1/admin/users', data=J.dumps({'email': em, 'password': pw, 'email_confirm': True}).encode(), headers=ah), timeout=30)
        uid = J.loads(r.read())['id']
    try:
        for role in ['pending', 'viewer']:
            req = urllib.request.Request(sb + '/rest/v1/profiles?id=eq.' + uid, data=J.dumps({'role': role}).encode(), method='PATCH', headers=dict(ah, Prefer='return=minimal'))
            urllib.request.urlopen(req, timeout=30)
            r = urllib.request.urlopen(urllib.request.Request(sb + '/auth/v1/token?grant_type=password', data=J.dumps({'email': em, 'password': pw}).encode(), headers={'apikey': k, 'Content-Type': 'application/json'}), timeout=30)
            tok = J.loads(r.read())['access_token']
            uh = {'apikey': k, 'Authorization': 'Bearer ' + tok}
            st, b = code(sb + '/storage/v1/object/dash/data/data.json.gz', h=uh)
            say('%s 계정 자료 받기 → %s (%d바이트)' % (role, st, len(b)))
            st, b = code(sb + '/storage/v1/object/dash/cache/state.json.gz', h=uh)
            say('%s 계정 캐시 받기(막혀야 함) → %s' % (role, st))
            st, b = code(sb + '/functions/v1/land', b'{"pnu":"5117010100108060000"}', dict(uh, **{'Content-Type': 'application/json'}))
            say('%s 계정 건축물대장 → %s %s' % (role, st, b[:60]))
    finally:
        req = urllib.request.Request(sb + '/auth/v1/admin/users/' + uid, method='DELETE', headers=ah)
        say('임시 계정 삭제 → %s' % urllib.request.urlopen(req, timeout=30).status)


def agri_probe():
    import urllib.request, urllib.parse, json as J
    def get(url, prm):
        u = url + '?' + urllib.parse.urlencode(prm)
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60)
            return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            return 'ERR %s %s' % (e, getattr(e, 'read', lambda: b'')()[:200])
    import sources
    for org, tbl in [('101','DT_1EA1011'),('101','DT_1EB002'),('101','DT_1AG25102'),('101','DT_1AG25101'),('101','DT_1AG25110'),('101','DT_1AG25501'),('101','DT_1AG25411'),('101','DT_1FS25103'),('101','DT_1FS25113'),('101','DT_1FS25115'),('101','DT_1FS25120'),('101','DT_1YL20121'),('101','DT_1A02002'),('101','DT_1FS000'),('101','DT_1NG0001'),('101','DT_1EA1014'),('101','DT_1EA1040')]:
        try:
            meta = sources.kosis_meta({'key_env': 'KOSIS_KEY', 'meta_url': 'https://kosis.kr/openapi/statisticsData.do', 'params': {'orgId': org, 'tblId': tbl}})
            od = {}
            for m in meta: od.setdefault(m.get('OBJ_ID'), []).append(m)
            say('== %s %s' % (tbl, ' / '.join('%s(%s:%d%s)' % (k, (v[0].get('OBJ_NM') or ''), len(v), ' 동해O' if any('동해' in str(x.get('ITM_NM')) for x in v) else '') for k, v in od.items())))
            it = od.get('ITEM') or []
            say('   항목: ' + ', '.join(str(x.get('ITM_NM')) + ('[' + str(x.get('UNIT_NM')) + ']' if x.get('UNIT_NM') else '') for x in it[:14]))
            for k, v in od.items():
                if k != 'ITEM' and not any('동해' in str(x.get('ITM_NM')) for x in v):
                    say('   %s: %s' % (k, ', '.join(str(x.get('ITM_NM')) for x in v[:10])))
        except Exception as e:  # noqa: BLE001
            say('== %s 오류 %s' % (tbl, e))
    import urllib.parse as UP
    key = UP.unquote(os.environ.get('DATA_GO_KR_KEY', ''))
    for nm, url, prm in [
        ('위판(일자별위탁판매, 파일→API)', 'https://api.odcloud.kr/api/15102791/v1/uddi:', {}),
        ('수협 위판정보 API', 'https://apis.data.go.kr/1192000/select0040List/getselect0040List', {'pageNo': 1, 'numOfRows': 5, 'type': 'json'}),
    ]:
        t = get(url, dict(prm, serviceKey=key))
        say('== %s → %s' % (nm, t[:400].replace('\n', ' ')))


def agri2_probe():
    import agri
    o = None
    o = agri.collect(codes())
    say('오류: %s' % o['errors'])
    for k, t in o['tables'].items():
        yrs = sorted(t['data'])
        d = t['data'][t['year']]
        say('== %s %s 연도 %s~%s 지역 %d' % (k, t['tbl'], yrs[0], yrs[-1], len(d)))
        say('   동해: ' + str({a: b for a, b in list((d.get('동해') or {}).items())[:16]}))
        say('   강원: ' + str({a: b for a, b in list((d.get('강원') or {}).items())[:6]}))


def chk_probe():
    import store, gzip, json as J
    d = J.loads(gzip.decompress(store.get('data/data.json.gz')))
    A = (d.get('life') or {}).get('agri') or {}
    say('메뉴 %s' % [m['id'] for m in d['menu']])
    say('agri 표 %s 오류 %s' % ({k: v['year'] for k, v in (A.get('tables') or {}).items()}, A.get('errors')))
    say('상태 %s' % (d['status'].get('agri')))
    for i in d['indicators']:
        if i['id'] in ('ag_farms', 'ag_land', 'ag_old', 'ag_eco', 'fs_hh'):
            say('%s 동해 %s / %d' % (i['id'], i.get('me'), i.get('n')))


def wipan_probe():
    import urllib.request, urllib.parse, json as J
    for ns in ('15102792/v1', '15102791/v1'):
        try:
            t = urllib.request.urlopen('https://infuser.odcloud.kr/oas/docs?namespace=' + ns, timeout=60).read().decode()
            d = J.loads(t)
            for path, v in d.get('paths', {}).items():
                g = v.get('get', {})
                say('== %s %s | %s | params %s' % (ns, path, g.get('summary'), [p_.get('name') for p_ in g.get('parameters', [])]))
        except Exception as e:  # noqa: BLE001
            say('== %s 오류 %s' % (ns, e))
    key = urllib.parse.unquote(os.environ.get('DATA_GO_KR_KEY', ''))
    try:
        t = urllib.request.urlopen('https://infuser.odcloud.kr/oas/docs?namespace=15102792/v1', timeout=60).read().decode()
        paths = list(J.loads(t).get('paths', {}))
        for pth in paths[-2:]:
            u = 'https://api.odcloud.kr/api' + pth + '?' + urllib.parse.urlencode({'page': 1, 'perPage': 3, 'serviceKey': key, 'cond[위판장명::LIKE]': '묵호'})
            try:
                r = urllib.request.urlopen(u, timeout=60).read().decode()
                say('호출 %s → %s' % (pth, r[:600]))
            except Exception as e:  # noqa: BLE001
                say('호출 %s → %s %s' % (pth, e, getattr(e, 'read', lambda: b'')()[:200]))
    except Exception as e:  # noqa: BLE001
        say('호출 실패 %s' % e)


def main():
    if os.environ.get('PROBE_ONLY') == 'wipan':
        wipan_probe(); return
    if os.environ.get('PROBE_ONLY') == 'chk':
        chk_probe(); return
    if os.environ.get('PROBE_ONLY') == 'agri2':
        agri2_probe(); return
    if os.environ.get('PROBE_ONLY') == 'agri':
        agri_probe(); return
    if os.environ.get('PROBE_ONLY') == 'lock':
        lock_probe(); return
    load_env()
    if os.environ.get('PROBE_ONLY') == 'ordin':
        ordin_probe()
        return
    if os.environ.get('PROBE_ONLY') == 'land':
        land_probe()
        return
    if os.environ.get('PROBE_ONLY', '').startswith('sbtest_'):
        supabase_test(os.environ['PROBE_ONLY'][7:])
        return
    if os.environ.get('PROBE_ONLY') == 'supabase':
        supabase_probe()
        return
    if os.environ.get('PROBE_ONLY') == 'kepco':
        kepco_probe()
        return
    S, C = settings(), codes()
    ym = ym_shift('%04d%02d' % (now().year, now().month), -2)
    me = [r for r in C['regions'] if r['name'] == C['me']][0]
    say('점검 시각 %s · 기준월 %s' % (now().strftime('%Y-%m-%d %H:%M'), ym))
    probe('population', S['sources']['population'], {'stdgCd': C['sido']['stdg'], 'srchFrYm': ym, 'srchToYm': ym})
    probe('dong_population', S['sources']['dong_population'], {'stdgCd': me['stdg'], 'srchFrYm': ym, 'srchToYm': ym})
    say('=' * 70)
    say('[age_kosis 메타]')
    try:
        import sources
        src = S['sources']['age']['kosis']
        meta = sources.kosis_meta(src)
        objs = {}
        for m in meta:
            objs.setdefault((m.get('OBJ_ID'), m.get('OBJ_NM')), []).append(m)
        for (oid, onm), ms in objs.items():
            say('  분류 %s %s · %d개 · 예: %s' % (oid, onm, len(ms), ', '.join('%s=%s' % (x.get('ITM_ID'), x.get('ITM_NM')) for x in ms[:6])))
        say('  첫 메타 줄: ' + json.dumps(meta[0], ensure_ascii=False)[:400] if meta else '  메타 없음')
        oid, rcodes = sources.kosis_region_codes(meta, C, tuple(src.get('region_code_prefix', [])))
        say('  강원 시·군 코드(%s): %s' % (oid, rcodes))
        ages, basis = sources.age_kosis(S, C)
        say('  연령 자료: %d개 시·군, 기준 %s, 동해 칸: %s' % (len(ages), basis, sorted(ages.get('동해', []))[:30]))
        dh = rcodes.get('동해', '')
        kids = [m for m in meta if m.get('OBJ_ID') == oid and str(m.get('ITM_ID', '')).startswith(dh) and str(m.get('ITM_ID')) != dh]
        say('  동해 하위 코드 %d개: %s' % (len(kids), ', '.join('%s=%s(up %s)' % (x.get('ITM_ID'), x.get('ITM_NM'), x.get('UP_ITM_ID')) for x in kids)))
        say('  연령 분류 이름: %s' % ', '.join('%s=%s' % (m.get('ITM_ID'), m.get('ITM_NM')) for m in meta if m.get('OBJ_ID') not in (oid, 'ITEM')))
    except Exception as e:  # noqa: BLE001
        say('  → 실패: %s' % e)
    import re as _re2
    for nm, url in (('death', 'https://apis.data.go.kr/1741000/admmSexdAgeErsr/selectAdmmSexdAgeErsr'),
                    ('hsmb', 'https://apis.data.go.kr/1741000/admmHsmbHh/selectAdmmHsmbHh'),
                    ('birth', 'https://apis.data.go.kr/1741000/admmSexdBrthReg/selectAdmmSexdBrthReg')):
        for lv in ():
            try:
                from urllib.parse import unquote as _uq; key = _uq(os.environ.get('DATA_GO_KR_KEY', '').strip())
                t = http_get(url, {'serviceKey': key, 'type': 'JSON', 'numOfRows': '30', 'pageNo': '1', 'lv': lv, 'regSeCd': '1', 'admmCd': me['stdg'], 'srchFrYm': ym, 'srchToYm': ym})
                items = find_items(parse_body(t))
                say('[%s lv%s] %d건' % (nm, lv, len(items)))
                for it in items[:12]:
                    say('   ' + json.dumps({k: v for k, v in it.items() if not _re2.match(r'^(male|feml)\d+Age', k)}, ensure_ascii=False)[:600])
            except Exception as e:  # noqa: BLE001
                say('[%s lv%s] 실패 %s' % (nm, lv, str(e)[:400]))
    from datetime import timedelta as _td
    _t = now() - _td(hours=3)
    _bd = _t.strftime('%Y%m%d')
    for nm, url, pr in () and (('cnctr', 'https://apis.data.go.kr/B551011/TatsCnctrRateService/tatsCnctrRatedList', {'areaCd': '51', 'signguCd': '51170', 'MobileOS': 'ETC', 'MobileApp': 'donghae', '_type': 'json', 'numOfRows': '5', 'pageNo': '1'}),
                        ('festival', 'https://apis.data.go.kr/B551011/KorService2/searchFestival2', {'eventStartDate': '20240101', 'areaCode': '32', 'sigunguCode': '3', 'MobileOS': 'ETC', 'MobileApp': 'donghae', '_type': 'json', 'numOfRows': '5', 'pageNo': '1', 'arrange': 'A'}),
                        ('festival_ld', 'https://apis.data.go.kr/B551011/KorService2/searchFestival2', {'eventStartDate': '20240101', 'lDongRegnCd': '51', 'lDongSignguCd': '170', 'MobileOS': 'ETC', 'MobileApp': 'donghae', '_type': 'json', 'numOfRows': '5', 'pageNo': '1', 'arrange': 'A'}),
                        ('spots', 'https://apis.data.go.kr/B551011/KorService2/areaBasedList2', {'areaCode': '32', 'sigunguCode': '3', 'contentTypeId': '12', 'MobileOS': 'ETC', 'MobileApp': 'donghae', '_type': 'json', 'numOfRows': '3', 'pageNo': '1', 'arrange': 'Q'}),
                        ('weather', 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst', {'dataType': 'JSON', 'base_date': _bd, 'base_time': '0500', 'nx': '97', 'ny': '127', 'numOfRows': '20', 'pageNo': '1'}),
                        ('visit_old', 'https://apis.data.go.kr/B551011/DataLabService/locgoRegnVisitrDDList', {'MobileOS': 'ETC', 'MobileApp': 'donghae', '_type': 'json', 'startYmd': '20230801', 'endYmd': '20230801', 'numOfRows': '3', 'pageNo': '1'})):
        try:
            from urllib.parse import unquote as _uq2
            q = dict(pr); q['serviceKey'] = _uq2(os.environ.get('DATA_GO_KR_KEY', '').strip())
            t = http_get(url, q, tries=1)
            say('[신규 %s] 됨: %s' % (nm, t[:1500].replace('\n', ' ')))
        except Exception as e:  # noqa: BLE001
            say('[신규 %s] 안 됨: %s' % (nm, str(e)[-300:]))
    from urllib.parse import unquote as _uq7
    kk = _uq7(os.environ.get('DATA_GO_KR_KEY', '').strip())
    tries = []
    for base, extra in (('BusStop/getBusStop', {}), ('NumberofRoutesServingEachStop/getNumberofRoutesServingEachStop', {}), ('NumberofRoutesServingEachStop/getNumberofRoutesServingEachStop', {'opr_ymd': '20251101'}),
                        ('StopbyRouteTripVolume/getDailyStopbyRouteTripVolume', {'opr_ymd': '20251101'})):
        for c, g in (('51', '51170'), ('42', '42170'), ('32', '32040')):
            q = dict(extra, ctpv_cd=c, sgg_cd=g, dataType='JSON')
            tries.append(('%s %s/%s' % (base.split('/')[0], c, g), 'https://apis.data.go.kr/1613000/' + base, q))
    tries = []
    for base in ['http://openapi.tour.go.kr/openapi/service/TourismResourceStatsService/getPchrgTrrsrtVisitorList',
                 'https://openapi.tour.go.kr/openapi/service/TourismResourceStatsService/getPchrgTrrsrtVisitorList'] + \
                ['https://apis.data.go.kr/%s/TourismResourceStatsService/getPchrgTrrsrtVisitorList' % o for o in ('B551011', 'B551014', 'B553077', '1371000', 'B490007', 'B552015', 'B553662', 'B551010')]:
        for sd in ('강원특별자치도', '강원도'):
            tries.append(('stat %s %s' % (base.split('//')[1][:40], sd), base, {'YM': '202506', 'SIDO': sd, 'GUNGU': '동해시', '_type': 'json'}))
    for nm, url, extra in tries:
        try:
            q = {'serviceKey': kk, 'numOfRows': '5', 'pageNo': '1'}
            q.update(extra)
            t = http_get(url, q, tries=1)
            say('[찾기 %s] 됨 %s' % (nm, t[:2500].replace('\n', ' ')))
        except Exception as e:  # noqa: BLE001
            m = str(e)
            code = 'NO_SERVICE' if 'NO_OPENAPI' in m or '404' in m else 'NOT_REG' if 'NOT_REGISTERED' in m else m[-200:].replace('\n', ' ')
            say('[찾기 %s] %s' % (nm, code))
    _kk = os.environ.get('KOSIS_KEY', '')
    from urllib.parse import unquote as _uq9
    _dk = _uq9(os.environ.get('DATA_GO_KR_KEY', '').strip())
    for svc in ('general_restaurants', 'rest_cafes', 'lodgings', 'bakeries', 'rural_homestays'):
        for q in ({'cond[ROAD_NM_ADDR::LIKE]': '동해시'}, {'cond[LOTNO_ADDR::LIKE]': '강원특별자치도 동해시'}):
            try:
                t = http_get('https://apis.data.go.kr/1741000/%s/info' % svc, dict(q, serviceKey=_dk, pageNo='1', numOfRows='2', returnType='json'), tries=1)
                say('[인허가 %s %s] %s' % (svc, list(q)[0], t[:1500].replace('\n', ' ')))
            except Exception as e:  # noqa: BLE001
                say('[인허가 %s] 실패 %s' % (svc, str(e)[-300:]))
    try:
        import urllib.request as _ur2
        bd = json.dumps({'dc_search': {'STT_OFR_TBL_NM': 'TTQSNAI01T082143', 'STT_PBL_YR': '2026', 'STT_PBL_MM': '08', 'SCH_TFB_BC_CL': 'BC', 'SCH_CLUS_CL': 'sex', 'SCH_TFB_BC_CD': '00', 'SCH_TFB_BC_NM': '업태전체', 'SCH_SIDO_CD': '51', 'SCH_SIDO_NM': '강원특별자치도', 'SCH_SGG_CD': '00000', 'SCH_SGG_NM': '전체'}}, ensure_ascii=False).encode()
        rq = _ur2.Request('https://tasis.nts.go.kr/wqAction.do?actionId=ATWEPFFA001R04', data=bd, headers={'Content-Type': 'application/json; charset=UTF-8', 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://tasis.nts.go.kr/websquare/websquare.html?w2xPath=/cm/index.xml'})
        with _ur2.urlopen(rq, timeout=30) as r:
            say('[TASIS] %s %s' % (r.status, r.read()[:600].decode('utf-8', 'replace')))
    except Exception as e:  # noqa: BLE001
        say('[TASIS] 실패 %s' % e)
    try:
        import urllib.request as _ur
        body = 'datsClCrit=WS&datsClNo=1004&datsNo=22&datTbl=TIP_DPWL_DSRT_DSTP_DSPSN_STN&radioType=1&statYm=202610&statYy=2026&statMm=10&selbox=%ED%95%B4%EB%8B%B9%EC%9B%94&statCtprvCd=51&statSggCd=5117000000&meaCol=REG_DSPSN_NT&chartType=bar&spdmRtYN=N&dimCols=DSDGR_NM%20AS%20DIMCOL0&grpCol0=DSDGR_NM&DIMCOL0=DSDGR_NM&ordCol0=DSDGR_NM_ORD0'
        rq = _ur.Request('https://www.bokjiro.go.kr/ssis-tbu/twatga/sociGuaStat/selectChartData.do', data=body.encode(), headers={'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bokjiro.go.kr/ssis-tbu/twatga/sociGuaStat/SociGuaStatDetailIframe.do?datsNo=22&datsClNo=1041&datsClCrit=WS'})
        with _ur.urlopen(rq, timeout=30) as r:
            say('[복지로] %s %s' % (r.status, r.read()[:500].decode('utf-8', 'replace')))
        with _ur.urlopen(_ur.Request('https://www.bokjiro.go.kr/ssis-tbu/twatga/sociGuaStat/SociGuaStatDetailIframe.do?datsNo=56&datsClNo=1071&datsClCrit=WS', headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as r:
            h = r.read().decode('utf-8', 'replace')
            import re as _r7
            say('[복지로 페이지] datTbl=%s meaCol=%s dims=%s' % (_r7.findall(r'datTbl[^>]*value="([^"]*)"', h)[:3], _r7.findall(r'name="meaCol"[^>]*', h)[:4], _r7.findall(r'name="dimCols"[^>]*', h)[:6]))
    except Exception as e:  # noqa: BLE001
        say('[복지로] 실패 %s' % e)
    try:
        t = http_get('https://infuser.odcloud.kr/oas/docs', {'namespace': '15062448/v1'})
        import re as _re8
        paths = _re8.findall(r'"(/15062448/v1/uddi:[^"]+)"', t)
        say('[사회보장 swagger] %s' % paths)
        from urllib.parse import unquote as _uq8
        for pth in paths[-3:]:
            try:
                r = http_get('https://api.odcloud.kr/api' + pth, {'serviceKey': _uq8(os.environ.get('DATA_GO_KR_KEY', '').strip()), 'page': '1', 'perPage': '3', 'returnType': 'JSON'}, tries=1)
                say('[사회보장 호출] %s → %s' % (pth, r[:700]))
            except Exception as e:  # noqa: BLE001
                say('[사회보장 호출] %s 실패 %s' % (pth, str(e)[-300:]))
    except Exception as e:  # noqa: BLE001
        say('[사회보장 swagger] 실패 %s' % e)
    import sources as _s9
    for org, tb in ():
        try:
            meta = _s9.kosis_meta({'key_env': 'KOSIS_KEY', 'meta_url': 'https://kosis.kr/openapi/statisticsData.do', 'params': {'orgId': org, 'tblId': tb}})
            objs = {}
            for m in meta:
                objs.setdefault(m.get('OBJ_ID'), []).append(m)
            say('[물메타] %s: %s' % (tb, ' / '.join('%s(%s개, %s): %s' % (k, len(v), v[0].get('OBJ_NM'), ', '.join('%s=%s' % (x.get('ITM_ID'), x.get('ITM_NM')) for x in v[:40])) for k, v in objs.items())))
            say('[물메타] %s 동해: %s' % (tb, ', '.join('%s:%s=%s(상위 %s)' % (x.get('OBJ_ID'), x.get('ITM_ID'), x.get('ITM_NM'), x.get('UP_ITM_ID')) for x in meta if '동해' in str(x.get('ITM_NM')) or str(x.get('ITM_NM')).startswith('강원'))))
            t = http_get('https://kosis.kr/openapi/statisticsData.do', {'method': 'getMeta', 'type': 'PRD', 'orgId': org, 'tblId': tb, 'format': 'json', 'jsonVD': 'Y', 'apiKey': _kk})
            say('[물주기] %s: %s' % (tb, t[:200]))
            prm = {'method': 'getList', 'format': 'json', 'jsonVD': 'Y', 'orgId': org, 'tblId': tb, 'prdSe': 'Y', 'newEstPrdCnt': '1', 'apiKey': _kk}
            i = 0
            for k, v in objs.items():
                if k == 'ITEM':
                    prm['itmId'] = 'ALL'
                    continue
                i += 1
                dh = [x for x in v if '동해' in str(x.get('ITM_NM'))]
                prm['objL%d' % i] = (dh[0]['ITM_ID'] + '+') if dh else 'ALL'
            t = http_get('https://kosis.kr/openapi/Param/statisticsParameterData.do', prm)
            j = json.loads(t)
            say('[물자료] %s %s: %s' % (tb, {k: v for k, v in prm.items() if k.startswith('obj')}, ' | '.join('%s %s %s %s=%s%s' % (r.get('PRD_DE'), r.get('C1_NM'), r.get('C2_NM', ''), r.get('ITM_NM'), r.get('DT'), r.get('UNIT_NM', '')) for r in j[:60]) if isinstance(j, list) else str(j)[:300]))
        except Exception as e:  # noqa: BLE001
            say('[물메타] %s 실패 %s' % (tb, e))
    for q in ():
        try:
            t = http_get('https://kosis.kr/openapi/statisticsSearch.do', {'method': 'getList', 'apiKey': _kk, 'searchNm': q, 'format': 'json', 'jsonVD': 'Y', 'resultCount': '40'})
            j = json.loads(t)
            say('[KOSIS검색] %s → %s' % (q, ' | '.join('%s/%s %s(%s~%s %s)' % (x.get('ORG_ID'), x.get('TBL_ID'), x.get('TBL_NM'), x.get('STRT_PRD_DE'), x.get('END_PRD_DE'), x.get('PRD_SE', '')) for x in j if str(x.get('ORG_ID')) in ('117', '322', '331', '350', '101', '110', '106', '126', '116', '460'))[:2500] if isinstance(j, list) else str(j)[:300]))
        except Exception as e:  # noqa: BLE001
            say('[KOSIS검색] %s 실패 %s' % (q, e))
    from urllib.parse import unquote as _unq
    _dk = _unq(os.environ.get('DATA_GO_KR_KEY', '').strip())
    tests = [
        ('전자파1', 'https://apis.data.go.kr/B552729/kcaApiService_emf/getEmfExposureIndex', {'address': '동해시', 'distance': '1000', 'pageNo': '1', 'numOfRows': '3'}),
        ('전자파2', 'https://apis.data.go.kr/B552729/kcaApiService_emf/getEmfExposureIndex', {'address': '강원특별자치도 동해시 천곡동', 'distance': '500', 'pageNo': '1', 'numOfRows': '3', 'type': 'json'}),
        ('생활전자파간이', 'https://apis.data.go.kr/B552729/KCCEWISLE/bemf', {'pageNo': '1', 'numOfRows': '3'}),
        ('생활전자파소형', 'https://apis.data.go.kr/B552729/KCCEWISLE/meas', {'pageNo': '1', 'numOfRows': '3'}),
    ]
    for nm, url, prm in tests:
        try:
            q = dict(prm); q['serviceKey'] = _dk
            t = http_get(url, q, tries=1, timeout=120)
            say('[환경API] %s → %s' % (nm, t[:1000].replace(_dk, '***').replace('\n', ' ')))
        except Exception as e:  # noqa: BLE001
            say('[환경API] %s 실패 %s' % (nm, str(e)[:300].replace('\n', ' ')))
    _kp = os.environ.get('KEPCO_KEY', '').strip()
    if _kp:
        for nm, url, prm in (('코드', 'https://bigdata.kepco.co.kr/openapi/v1/commonCode.do', {'codeTy': 'metroCd'}),
                             ('계약종별', 'https://bigdata.kepco.co.kr/openapi/v1/powerUsage/contractType.do', {'year': '2026', 'month': '09', 'metroCd': '51'}),
                             ('가구평균', 'https://bigdata.kepco.co.kr/openapi/v1/powerUsage/houseAve.do', {'year': '2026', 'month': '09', 'metroCd': '51'})):
            try:
                q = dict(prm); q.update({'apiKey': _kp, 'returnType': 'json'})
                t = http_get(url, q, tries=1, timeout=30)
                say('[한전] %s → %s' % (nm, t[:1200].replace(_kp, '***')))
            except Exception as e:  # noqa: BLE001
                say('[한전] %s 실패 %s' % (nm, str(e)[:250]))
    else:
        say('[한전] KEPCO_KEY 없음')
    if os.environ.get('PROBE_FULL') != '1':
        return
    probe('admm_population', {'url': 'https://apis.data.go.kr/1741000/admmPpltnHhStus/selectAdmmPpltnHhStus', 'key_env': 'DATA_GO_KR_KEY',
                               'params': {'type': 'JSON', 'numOfRows': '100', 'pageNo': '1', 'lv': '3', 'regSeCd': '1'}},
          {'admmCd': me['stdg'], 'srchFrYm': ym, 'srchToYm': ym})
    probe('age_mois', S['sources']['age']['mois'], {})
    import urllib.request
    kk = os.environ.get('KOSIS_KEY', '')
    import sources as _s
    for tb in ('DT_1B26003_A02', 'DT_1B26001_A01'):
        try:
            src = {'key_env': 'KOSIS_KEY', 'meta_url': 'https://kosis.kr/openapi/statisticsData.do', 'params': {'orgId': '101', 'tblId': tb}}
            meta = _s.kosis_meta(src)
            objs = {}
            for m in meta:
                objs.setdefault(m.get('OBJ_ID'), []).append(m)
            say('[메타] %s: %s' % (tb, ' / '.join('%s(%s개, %s): %s' % (k, len(v), v[0].get('OBJ_NM'), ', '.join('%s=%s' % (x.get('ITM_ID'), x.get('ITM_NM')) for x in v[:6])) for k, v in objs.items())))
            dh = [x for x in meta if '동해' in str(x.get('ITM_NM'))]
            say('[메타] %s 동해 코드: %s' % (tb, ', '.join('%s:%s=%s' % (x.get('OBJ_ID'), x.get('ITM_ID'), x.get('ITM_NM')) for x in dh)))
            t = http_get('https://kosis.kr/openapi/statisticsData.do', {'method': 'getMeta', 'type': 'PRD', 'orgId': '101', 'tblId': tb, 'format': 'json', 'jsonVD': 'Y', 'apiKey': kk})
            say('[주기] %s: %s' % (tb, t[:300]))
        except Exception as e:  # noqa: BLE001
            say('[메타] %s 실패 %s' % (tb, e))
    for q in ('1세별 주민등록인구', '각세별 주민등록인구'):
        try:
            t = http_get('https://kosis.kr/openapi/statisticsSearch.do', {'method': 'getList', 'apiKey': kk, 'searchNm': q, 'format': 'json', 'jsonVD': 'Y', 'resultCount': '15'})
            j = json.loads(t)
            say('[검색] %s → %s' % (q, ' | '.join('%s/%s %s(%s~%s %s)' % (x.get('ORG_ID'), x.get('TBL_ID'), x.get('TBL_NM'), x.get('STRT_PRD_DE'), x.get('END_PRD_DE'), x.get('PRD_SE', '')) for x in (j if isinstance(j, list) else []))[:1800] if isinstance(j, list) else str(j)[:300]))
        except Exception as e:  # noqa: BLE001
            say('[검색] %s 실패 %s' % (q, e))
    for u in ():
        try:
            with urllib.request.urlopen(u, timeout=25) as r:
                say('  연결 %s → %s' % (u, r.status))
        except Exception as e:  # noqa: BLE001
            say('  연결 %s → 실패 %s' % (u, e))
    probe('finance', S['sources']['finance'], {})
    probe('finance_final', S['sources']['finance_final'], {})
    path = os.path.join(ROOT, 'probe_결과.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('\n저장: %s' % path)


if __name__ == '__main__':
    main()
