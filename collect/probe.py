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


def main():
    load_env()
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
            t = http_get('https://kosis.kr/openapi/statisticsSearch.do', {'method': 'getList', 'apiKey': _kk, 'searchNm': q, 'format': 'json', 'jsonVD': 'Y', 'resultCount': '20'})
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
