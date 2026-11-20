"""점검 스크립트: 키를 넣은 뒤 한 번 실행합니다.

각 API를 동해시 기준으로 한 번씩 불러서
  - 성공/실패, 오류 코드
  - 응답에 들어 있는 항목 이름(영문) 목록
  - 첫 번째 줄 예시
를 화면에 보여주고 probe_결과.txt 로 저장합니다. 이 파일을 Claude에게 보내 주시면 settings.json을 맞춰 드립니다.
(키 값은 파일에 남기지 않습니다.)
"""
import json
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


def main():
    load_env()
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
    import sources as _s9
    for org, tb in (('101', 'DT_1ES3A03_A01S'),):
        try:
            meta = _s9.kosis_meta({'key_env': 'KOSIS_KEY', 'meta_url': 'https://kosis.kr/openapi/statisticsData.do', 'params': {'orgId': org, 'tblId': tb}})
            objs = {}
            for m in meta:
                objs.setdefault(m.get('OBJ_ID'), []).append(m)
            say('[경제메타] %s: %s' % (tb, ' / '.join('%s(%s개, %s): %s' % (k, len(v), v[0].get('OBJ_NM'), ', '.join('%s=%s' % (x.get('ITM_ID'), x.get('ITM_NM')) for x in v[:30])) for k, v in objs.items())))
            say('[경제메타] %s 동해: %s' % (tb, ', '.join('%s:%s=%s(상위 %s)' % (x.get('OBJ_ID'), x.get('ITM_ID'), x.get('ITM_NM'), x.get('UP_ITM_ID')) for x in meta if '동해' in str(x.get('ITM_NM')) or '강원' in str(x.get('ITM_NM')))))
            t = http_get('https://kosis.kr/openapi/statisticsData.do', {'method': 'getMeta', 'type': 'PRD', 'orgId': org, 'tblId': tb, 'format': 'json', 'jsonVD': 'Y', 'apiKey': _kk})
            say('[경제주기] %s: %s' % (tb, t[:300]))
        except Exception as e:  # noqa: BLE001
            say('[경제메타] %s 실패 %s' % (tb, e))
    for q in ():
        try:
            t = http_get('https://kosis.kr/openapi/statisticsSearch.do', {'method': 'getList', 'apiKey': _kk, 'searchNm': q, 'format': 'json', 'jsonVD': 'Y', 'resultCount': '20'})
            j = json.loads(t)
            say('[KOSIS검색] %s → %s' % (q, ' | '.join('%s/%s %s(%s~%s %s)' % (x.get('ORG_ID'), x.get('TBL_ID'), x.get('TBL_NM'), x.get('STRT_PRD_DE'), x.get('END_PRD_DE'), x.get('PRD_SE', '')) for x in j)[:3000] if isinstance(j, list) else str(j)[:300]))
        except Exception as e:  # noqa: BLE001
            say('[KOSIS검색] %s 실패 %s' % (q, e))
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
