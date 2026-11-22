"""관광·날씨 수집: 관광지 집중률(30일 예측), 관광지·축제 목록(국문 관광정보), 단기예보.

모두 공공데이터포털 키(DATA_GO_KR_KEY) 하나로 부릅니다.
"""
import datetime as _dt

from common import to_num, log, now
from sources import _call

KEY = 'DATA_GO_KR_KEY'
APP = {'MobileOS': 'ETC', 'MobileApp': 'donghae', '_type': 'json'}
# 동해시: 법정동 시도 51, 시군구 170 / 행정코드 51170
LDONG = {'lDongRegnCd': '51', 'lDongSignguCd': '170'}
BOX = (37.38, 37.62, 128.95, 129.20)  # 동해시 대략 범위(위도, 경도)


def _src(url, params):
    return {'url': url, 'key_env': KEY, 'params': params}


def _in_box(lat, lng):
    return lat is not None and lng is not None and BOX[0] <= lat <= BOX[1] and BOX[2] <= lng <= BOX[3]


# ---------------------------------------------------------------- 관광지 집중률(오늘부터 30일 예측)
CNCTR_URL = 'https://apis.data.go.kr/B551011/TatsCnctrRateService/tatsCnctrRatedList'


def concentration():
    rows = _call(_src(CNCTR_URL, dict(APP, areaCd='51', signguCd='51170', numOfRows='1000', pageNo='1')), {}, 'cnctr')
    spots = {}
    for r in rows:
        name = str(r.get('tAtsNm') or '').strip()
        v = to_num(r.get('cnctrRate'))
        if not name or v is None:
            continue
        spots.setdefault(name, []).append([str(r.get('baseYmd')), round(v, 1)])
    for k in spots:
        spots[k].sort()
    if not spots:
        raise RuntimeError('관광지 집중률 응답이 비어 있음')
    return {'at': now().strftime('%Y-%m-%d'), 'spots': spots}


# ---------------------------------------------------------------- 관광지·축제 목록
KOR = 'https://apis.data.go.kr/B551011/KorService2/'
TYPES = {'12': '관광지', '14': '문화시설', '15': '축제·행사', '28': '레포츠'}


def _item(r):
    lat, lng = to_num(r.get('mapy')), to_num(r.get('mapx'))
    return {'id': str(r.get('contentid')), 'type': str(r.get('contenttypeid')), 'title': str(r.get('title') or '').strip(),
            'addr': str(r.get('addr1') or '').replace('강원특별자치도 ', ''), 'lat': lat if _in_box(lat, lng) else None,
            'lng': lng if _in_box(lat, lng) else None}


def places():
    out = []
    for t in ('12', '14', '28'):
        try:
            rows = _call(_src(KOR + 'areaBasedList2', dict(APP, **LDONG, contentTypeId=t, arrange='Q', numOfRows='300', pageNo='1')), {}, 'places_%s' % t)
        except Exception as e:  # noqa: BLE001
            log('관광지 목록 %s 실패: %s' % (t, e))
            continue
        out.extend(_item(r) for r in rows)
    if not out:
        raise RuntimeError('관광지 목록이 비어 있음')
    return out


def festivals():
    """축제·행사: 행사 검색(올해 이후 일정) + 축제 항목 각각의 소개(기간)."""
    seen, out = set(), []
    start = '%04d0101' % (now().year - 3)
    try:
        rows = _call(_src(KOR + 'searchFestival2', dict(APP, **LDONG, eventStartDate=start, arrange='A', numOfRows='200', pageNo='1')), {}, 'festival_search')
    except Exception as e:  # noqa: BLE001
        log('축제 검색 실패: %s' % e)
        rows = []
    for r in rows:
        it = _item(r)
        it.update({'start': str(r.get('eventstartdate') or ''), 'end': str(r.get('eventenddate') or '')})
        seen.add(it['id'])
        out.append(it)
    try:
        rows = _call(_src(KOR + 'areaBasedList2', dict(APP, **LDONG, contentTypeId='15', arrange='Q', numOfRows='200', pageNo='1')), {}, 'festival_list')
    except Exception as e:  # noqa: BLE001
        log('축제 목록 실패: %s' % e)
        rows = []
    for r in rows[:40]:
        it = _item(r)
        if it['id'] in seen:
            continue
        try:
            d = _call(_src(KOR + 'detailIntro2', dict(APP, contentId=it['id'], contentTypeId='15', numOfRows='1', pageNo='1')), {}, 'festival_intro')
        except Exception as e:  # noqa: BLE001
            log('축제 소개 %s 실패: %s' % (it['title'], e))
            d = []
        if d:
            it.update({'start': str(d[0].get('eventstartdate') or ''), 'end': str(d[0].get('eventenddate') or ''),
                       'place': str(d[0].get('eventplace') or '')})
        seen.add(it['id'])
        out.append(it)
    out.sort(key=lambda x: x.get('start') or '0')
    return out


# ---------------------------------------------------------------- 단기예보(3시간 간격, 모레까지)
FCST_URL = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst'
GRID = ('97', '127')  # 동해시 천곡동 격자
KEEP = ('TMP', 'SKY', 'PTY', 'POP', 'PCP', 'WSD', 'REH', 'TMN', 'TMX', 'WAV')


import math

# 행정동 중심(근사) → 기상청 격자
DONG_LL = {'망상동': (37.588, 129.088), '묵호동': (37.557, 129.125), '발한동': (37.547, 129.106), '부곡동': (37.534, 129.092), '동호동': (37.531, 129.123),
           '천곡동': (37.522, 129.112), '송정동': (37.498, 129.124), '북삼동': (37.497, 129.083), '북평동': (37.472, 129.138), '삼화동': (37.466, 129.038)}


def kma_grid(lat, lon):
    RE, GRID, S1, S2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    d = math.pi / 180.0
    re = RE / GRID
    s1, s2, olon, olat = S1 * d, S2 * d, OLON * d, OLAT * d
    sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(math.tan(math.pi * 0.25 + s2 * 0.5) / math.tan(math.pi * 0.25 + s1 * 0.5))
    sf = math.pow(math.tan(math.pi * 0.25 + s1 * 0.5), sn) * math.cos(s1) / sn
    ro = re * sf / math.pow(math.tan(math.pi * 0.25 + olat * 0.5), sn)
    ra = re * sf / math.pow(math.tan(math.pi * 0.25 + lat * d * 0.5), sn)
    th = lon * d - olon
    th = (th + 2 * math.pi) if th < -math.pi else (th - 2 * math.pi) if th > math.pi else th
    th *= sn
    return int(math.floor(ra * math.sin(th) + XO + 0.5)), int(math.floor(ro - ra * math.cos(th) + YO + 0.5))


def _fcst(bd, bt, nx, ny, name):
    rows = _call(_src(FCST_URL, {'dataType': 'JSON', 'base_date': bd, 'base_time': bt, 'nx': str(nx), 'ny': str(ny), 'numOfRows': '1000', 'pageNo': '1'}), {}, name)
    slots = {}
    for r in rows:
        c = r.get('category')
        if c not in KEEP:
            continue
        k = '%s%s' % (r.get('fcstDate'), r.get('fcstTime'))
        slots.setdefault(k, {})[c] = r.get('fcstValue')
    return dict(sorted(slots.items()))


def weather():
    t = now() - _dt.timedelta(minutes=15)
    bases = [2, 5, 8, 11, 14, 17, 20, 23]
    h = max([b for b in bases if b <= t.hour], default=None)
    if h is None:
        t -= _dt.timedelta(days=1)
        h = 23
    bd, bt = t.strftime('%Y%m%d'), '%02d00' % h
    slots = _fcst(bd, bt, GRID[0], GRID[1], 'weather')
    if not slots:
        raise RuntimeError('단기예보 응답이 비어 있음')
    out = {'base': bd + bt, 'slots': slots, 'dongs': {}, 'grids': {}}
    main = '%s,%s' % GRID
    for dong, (la, lo) in DONG_LL.items():
        nx, ny = kma_grid(la, lo)
        key = '%d,%d' % (nx, ny)
        out['dongs'][dong] = key
        if key in out['grids'] or key == main:
            continue
        try:
            g = _fcst(bd, bt, nx, ny, 'weather_%s' % key)
            out['grids'][key] = {k: v for k, v in list(g.items())[:30]}  # 동별은 앞 30시간만
        except Exception as e:  # noqa: BLE001
            log('동별 예보 %s 실패: %s' % (dong, e))
    out['grids'][main] = {k: v for k, v in list(slots.items())[:30]}
    return out


# ---------------------------------------------------------------- 지역별 관광 수요 강도(월, 지수 0~100)
DEM = 'https://apis.data.go.kr/B551011/AreaTarDemDsService/'
DEM_OPS = (('areaTarExpDsList', 'exp', 'tarExpDsIxCd', 'tarExpDsIxNm', 'tarExpDsIxVal', ('22', '2201', '2202', '2203')),
           ('areaTarSjrnDsList', 'stay', 'tarSjrnDsIxCd', 'tarSjrnDsIxNm', 'tarSjrnDsIxVal', ('21', '2101', '2102', '2103', '2104', '2105')))


def demand(C, cache=None, n_months=25):
    """관광 소비 강도·체류 강도: {YYYYMM: {시군: {코드: 값}}}, 코드 이름표."""
    from common import match_region
    cache = dict(cache or {})
    names = {}
    t = now()
    y, m = t.year, t.month
    yms = []
    for _ in range(n_months + 2):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        yms.append('%04d%02d' % (y, m))
    for i, ym in enumerate(yms):
        if ym in cache and i > 1:  # 최근 2달은 매번 다시
            continue
        got = {}
        rows_all = []
        for op, kind, ck, nk, vk, codes in DEM_OPS:
            for code in (codes if i < 13 else codes[:1]):
                try:
                    rows = _call(_src(DEM + op, dict(APP, **{'baseYm': ym, 'areaCd': '51', 'numOfRows': '100', 'pageNo': '1', ck: code})), {}, 'dem_' + kind)
                except Exception as e:  # noqa: BLE001
                    log('관광 수요 강도 %s %s %s 실패: %s' % (ym, kind, code, e))
                    continue
                rows_all.extend((r, ck, nk, vk) for r in rows)
        for r, ck, nk, vk in rows_all:
            if True:
                nm = r.get('signguNm')
                name = '강원' if str(r.get('signguCd')) == '0' else match_region(str(nm or ''), C['regions'])
                v = to_num(r.get(vk))
                if not name or v is None:
                    continue
                got.setdefault(name, {})[str(r.get(ck))] = v
                names[str(r.get(ck))] = str(r.get(nk))
        if len(got) >= 15:
            cache[ym] = got
    keep = sorted(cache)[-n_months:]
    return {k: cache[k] for k in keep}, names


# ---------------------------------------------------------------- 행사 일정(표준데이터 2종 + 문화정보원)
import re as _re

STD = 'https://api.data.go.kr/openapi/'


def _ymd(s):
    s = _re.sub(r'\D', '', str(s or ''))
    return s[:8] if len(s) >= 8 else ''


def _is_me(*xs):
    t = ' '.join(str(x or '') for x in xs)
    return '동해시' in t and ('강원' in t or '동해시' in t)


def _std_scan(path, name, max_pages=60):
    import json as _json
    from common import http_get
    from urllib.parse import unquote
    import os
    key = unquote(os.environ.get(KEY, '').strip())
    out, page = [], 1
    while page <= max_pages:
        t = http_get(STD + path, {'serviceKey': key, 'type': 'json', 'numOfRows': '1000', 'pageNo': str(page)})
        j = _json.loads(t)
        body = (j.get('response') or j).get('body') or {}
        items = (body.get('items') or {})
        items = items.get('item', items) if isinstance(items, dict) else items
        if isinstance(items, dict):
            items = [items]
        if not items:
            break
        out.extend(items)
        total = int(body.get('totalCount') or 0)
        if page * 1000 >= total:
            break
        page += 1
    log('%s: 전국 %d건 확인' % (name, len(out)))
    return out


def events():
    res = []
    try:
        for r in _std_scan('tn_pubr_public_cltur_fstvl_api', '축제 표준데이터', 10):
            if _is_me(r.get('rdnmadr'), r.get('lnmadr'), r.get('mnnstNm'), r.get('auspcInsttNm')):
                res.append({'title': r.get('fstvlNm'), 'start': _ymd(r.get('fstvlStartDate')), 'end': _ymd(r.get('fstvlEndDate')),
                            'place': r.get('opar') or '', 'kind': '축제', 'desc': str(r.get('fstvlCo') or '').replace('+', ', ')[:120],
                            'lat': to_num(r.get('latitude')), 'lng': to_num(r.get('longitude')), 'src': '전국문화축제표준데이터'})
    except Exception as e:  # noqa: BLE001
        log('축제 표준데이터 실패: %s' % e)
    try:
        for r in _std_scan('tn_pubr_public_pblprfr_event_info_api', '공연행사 표준데이터', 80):
            if _is_me(r.get('rdnmadr'), r.get('lnmadr'), r.get('insttNm')):
                res.append({'title': r.get('eventNm'), 'start': _ymd(r.get('eventStartDate')), 'end': _ymd(r.get('eventEndDate')),
                            'place': r.get('opar') or '', 'kind': '공연·행사', 'desc': str(r.get('eventCo') or '')[:120],
                            'lat': to_num(r.get('latitude')), 'lng': to_num(r.get('longitude')), 'src': '전국공연행사정보표준데이터'})
    except Exception as e:  # noqa: BLE001
        log('공연행사 표준데이터 실패: %s' % e)
    try:
        frm = '%04d0101' % (now().year - 3)
        to = (now() + _dt.timedelta(days=200)).strftime('%Y%m%d')
        rows = []
        for pg in range(1, 15):
            got = _call(_src('https://apis.data.go.kr/B553457/cultureinfo/area2', {'numOfrows': '500', 'PageNo': str(pg), 'sido': '강원', 'gugun': '동해시', 'from': frm, 'to': to}), {}, 'culture')
            rows.extend(got)
            if len(got) < 500:
                break
        log('문화정보원 강원 %d건 확인' % len(rows))
        for r in rows:
            if str(r.get('sigungu') or '').strip() != '동해시':
                continue
            res.append({'title': r.get('title'), 'start': _ymd(r.get('startDate')), 'end': _ymd(r.get('endDate')), 'place': r.get('place') or '',
                        'kind': r.get('realmName') or r.get('serviceName') or '공연·전시', 'desc': '', 'lat': to_num(r.get('gpsY')), 'lng': to_num(r.get('gpsX')),
                        'src': '한국문화정보원'})
    except Exception as e:  # noqa: BLE001
        log('문화정보원 공연·전시 실패: %s' % e)
    import html as _html
    seen, out = set(), []
    for x in res:
        if not x['title'] or not x['start']:
            continue
        x['title'] = _html.unescape(_re.sub(r'^\s*\[[^\]]*\]\s*', '', str(x['title'])))
        k = (_re.sub(r'[\s&·,]|\d{4}', '', x['title'])[:10], x['start'])
        if k in seen:
            continue
        seen.add(k)
        x['title'] = str(x['title']).strip()
        out.append(x)
    # 같은 날 같은 공연이 출처마다 다른 이름으로 올 때(예: '연극 노인의 꿈'과 '노인의 꿈') 하나만 남깁니다
    def nk(t):
        return _re.sub(r'[\s&·,:\-"“”\'<>《》]|\d{4}', '', t)
    keep = []
    for x in sorted(out, key=lambda x: len(x['title'])):
        if any(y['start'] == x['start'] and (nk(y['title']) in nk(x['title']) or nk(x['title']) in nk(y['title'])) for y in keep):
            continue
        keep.append(x)
    keep.sort(key=lambda x: x['start'])
    return keep


# ---------------------------------------------------------------- 주차장(전국주차장정보표준데이터 → 강원 18개 시·군 집계)
def parking(C):
    from common import match_region
    rows = _std_scan('tn_pubr_prkplce_info_api', '주차장 표준데이터', 60)
    out = {}
    for r in rows:
        addr = ' '.join(str(r.get(k) or '') for k in ('rdnmadr', 'lnmadr', 'insttNm', 'institutionNm'))
        if '강원' not in addr:
            continue
        if str(r.get('prkplceSe')) != '공영':  # 공영주차장만
            continue
        nm = str(r.get('insttNm') or '').replace('강원특별자치도', '').replace('강원도', '').strip()
        name = match_region(nm, C['regions'])
        if not name:
            continue
        o = out.setdefault(name, {'lots': 0, 'spaces': 0, 'public': 0, 'public_sp': 0, 'private': 0, 'free': 0, 'paid': 0, '노상': 0, '노외': 0, '부설': 0, 'items': []})
        sp = to_num(r.get('prkcmprt')) or 0
        o['lots'] += 1
        o['spaces'] += sp
        if str(r.get('prkplceSe')) == '공영':
            o['public'] += 1
            o['public_sp'] += sp
        else:
            o['private'] += 1
        if '무료' in str(r.get('parkingchrgeInfo')):
            o['free'] += 1
        elif r.get('parkingchrgeInfo'):
            o['paid'] += 1
        t = str(r.get('prkplceType') or '')
        if t in o:
            o[t] += 1
        if name == C['me']:
            o['items'].append({'name': r.get('prkplceNm'), 'type': t, 'se': r.get('prkplceSe'), 'sp': sp, 'fee': r.get('parkingchrgeInfo'),
                               'lat': to_num(r.get('latitude')), 'lng': to_num(r.get('longitude')), 'ref': r.get('referenceDate')})
    for k, o in out.items():
        if k != C['me']:
            o.pop('items')
    if len(out) < 10:
        raise RuntimeError('주차장: 강원 시·군 %d곳만 찾음' % len(out))
    return out


# ---------------------------------------------------------------- 택시(전국택시업체·택시승차대 표준데이터 → 강원 시·군 집계)
def taxi(C):
    from common import match_region
    out = {}
    for r in _std_scan('tn_pubr_public_taxi_corp_api', '택시업체 표준데이터', 20):
        if '강원' not in str(r.get('ctpvNm') or '') + str(r.get('insttNm') or ''):
            continue
        name = match_region(str(r.get('sggNm') or ''), C['regions'])
        if not name:
            continue
        o = out.setdefault(name, {'total': 0, 'personal': 0, 'corp': 0, 'corps': 0, 'stands': 0, 'stand_sp': 0, 'list': [], 'stand_list': []})
        n = to_num(r.get('lcnsCntom')) or 0
        nm = str(r.get('bzentyNm') or '').strip()
        o['total'] += n
        if '개인택시' in nm:
            o['personal'] += n
        else:
            o['corp'] += n
            o['corps'] += 1
        if name == C['me']:
            o['list'].append([nm, n])
    for r in _std_scan('tn_pubr_public_taxi_stand_api', '택시승차대 표준데이터', 20):
        if '강원' not in str(r.get('ctpvNm') or '') + str(r.get('insttNm') or ''):
            continue
        name = match_region(str(r.get('sggNm') or ''), C['regions'])
        if not name:
            continue
        o = out.setdefault(name, {'total': 0, 'personal': 0, 'corp': 0, 'corps': 0, 'stands': 0, 'stand_sp': 0, 'list': [], 'stand_list': []})
        n = to_num(r.get('taxExclsScplcCnt')) or 0
        o['stands'] += 1
        o['stand_sp'] += n
        if name == C['me']:
            o['stand_list'].append([str(r.get('dtlPstn') or r.get('lctnRoadNmAddr') or ''), n])
    for k, o in out.items():
        if k != C['me']:
            o.pop('list'); o.pop('stand_list')
        else:
            o['list'].sort(key=lambda x: -x[1]); o['stand_list'].sort(key=lambda x: -x[1])
    if not out.get(C['me']):
        raise RuntimeError('택시: 동해시 자료가 없음(강원 %d곳)' % len(out))
    return out


# ---------------------------------------------------------------- 버스 운수업체(전국버스업체표준데이터, 시·군이 올린 곳만)
def bus_corp(C):
    import os
    from urllib.parse import unquote
    import json as _json
    from common import http_get, match_region
    key = unquote(os.environ.get(KEY, '').strip())
    rows, page = [], 1
    while page <= 40:
        j = _json.loads(http_get('https://api.data.go.kr/openapi/tn_pubr_public_bus_corp_api', {'serviceKey': key, 'pageNo': str(page), 'numOfRows': '1000', 'type': 'json'}, tries=2))
        b = j.get('body') or (j.get('response') or {}).get('body') or {}
        it = (b.get('items') or {}).get('item') or []
        if isinstance(it, dict):
            it = [it]
        rows += it
        if len(it) < 1000:
            break
        page += 1
    def n(v):
        try:
            return int(str(v).replace(',', ''))
        except (TypeError, ValueError):
            return None
    out = {}
    for r in rows:
        if '강원' not in str(r.get('ctpvNm')):
            continue
        name = match_region(r.get('sggNm'), C['regions'])
        if not name:
            continue
        out.setdefault(name, []).append({'nm': (r.get('bzentyNm') or '').strip(), 'se': r.get('operSeNm') or '', 'routes': n(r.get('rteCnt')),
                                         'buses': n(r.get('busHldCntom')), 'staff': n(r.get('tnoemp')), 'ymd': r.get('dataCrtrYmd') or '', 'addr': r.get('lctnRoadNmAddr') or ''})
    if not out:
        raise RuntimeError('강원 시·군 자료 없음')
    return out


# ---------------------------------------------------------------- 업종별 운수업체(KOSIS 강원 기본통계 + 시·군 기본통계의 농어촌버스)
BUS_KINDS = ('시내버스', '농어촌버스', '마을버스', '전세버스', '시외버스', '택시(업체)', '개인택시')
SGG_TBL = {'춘천': ('651', 'DT_65101_J000029'), '원주': ('652', 'DT_65201_J000073'), '강릉': ('653', 'DT_65301_J000073'), '동해': ('654', 'DT_65401_J000073'),
           '태백': ('655', 'DT_65503_J000029'), '속초': ('656', 'DT_65601_J000073'), '삼척': ('657', 'DT_65701_J000029'), '홍천': ('658', 'DT_65801_J000073'),
           '횡성': ('659', 'DT_65901_J000161'), '영월': ('660', 'DT_66001_J000029'), '평창': ('661', 'DT_661001_J250004'), '철원': ('663', 'DT_66301_J000029'),
           '화천': ('664', 'DT_66401_J000029'), '양구': ('665', 'DT_66501_J000029'), '인제': ('666', 'DT_66601_J000029'), '고성': ('667', 'DT_66701_J000029'),
           '양양': ('668', 'DT_66801_J000029')}


def _kosis_rows(org, tbl, years):
    from sources import kosis_meta
    meta = kosis_meta({'key_env': 'KOSIS_KEY', 'meta_url': 'https://kosis.kr/openapi/statisticsData.do', 'params': {'orgId': org, 'tblId': tbl}})
    params = {'method': 'getList', 'format': 'json', 'jsonVD': 'Y', 'orgId': org, 'tblId': tbl, 'prdSe': 'Y', 'newEstPrdCnt': str(years), 'itmId': 'ALL'}
    objs = []
    for m in meta:
        if m.get('OBJ_ID') != 'ITEM' and m.get('OBJ_ID') not in objs:
            objs.append(m.get('OBJ_ID'))
    for i, _ in enumerate(objs):
        params['objL%d' % (i + 1)] = 'ALL'
    return _call({'key_env': 'KOSIS_KEY', 'key_param': 'apiKey', 'url': 'https://kosis.kr/openapi/Param/statisticsParameterData.do', 'params': params}, {}, 'kb_' + tbl)


def bus_firms(C):
    """{year, regions:{시군:{종류:{n 업체, v 대수}}}, rural:{시군:{year, n, v}}} — '-'는 0으로 보지 않고 없음."""
    from common import match_region
    rows = _kosis_rows('211', 'DT_211002_J004', 3)
    ys = sorted({str(r.get('PRD_DE')) for r in rows})
    if not ys:
        raise RuntimeError('응답이 비었음')
    y = ys[-1]
    out = {}
    for r in rows:
        if str(r.get('PRD_DE')) != y:
            continue
        kind = str(r.get('C1_NM', '')).strip()
        if kind not in BUS_KINDS:
            continue
        nm = str(r.get('C2_NM', '')).strip()
        reg = '강원' if nm == '전체' else match_region(nm, C['regions'])
        v = to_num(r.get('DT'))
        if not reg or v is None:
            continue
        f = 'n' if '업체' in str(r.get('ITM_NM')) else 'v'
        out.setdefault(reg, {}).setdefault(kind, {})[f] = v
    if len(out) < 15:
        raise RuntimeError('시·군이 %d곳뿐' % len(out))
    rural = {}
    for reg, (org, tbl) in SGG_TBL.items():
        try:
            rr = _kosis_rows(org, tbl, 1)
        except Exception as e:  # noqa: BLE001
            log('  농어촌버스 %s 실패: %s' % (reg, e))
            continue
        cell = {}
        for r in rr:
            if str(r.get('C1_NM', '')).strip() != '농어촌버스':
                continue
            v = to_num(r.get('DT'))
            if v is None:
                continue
            cell['year'] = str(r.get('PRD_DE'))
            cell['n' if '업체' in str(r.get('ITM_NM')) else 'v'] = v
        if cell.get('v'):
            rural[reg] = cell
    return {'year': y, 'regions': out, 'rural': rural}


# ---------------------------------------------------------------- 시내버스 정류장(국토부 정류장별 정차 노선수, 시·군별)
def bus_stops(C):
    import os
    from urllib.parse import unquote
    import json as _json
    from common import http_get
    key = unquote(os.environ.get(KEY, '').strip())
    url = 'https://apis.data.go.kr/1613000/NumberofRoutesServingEachStop/getNumberofRoutesServingEachStop'
    # 가장 최근 기준일 찾기(매월 1일 → 15일 순)
    t = now()
    cands = []
    for back in range(0, 14):
        y, m = t.year, t.month - back
        while m < 1:
            y, m = y - 1, m + 12
        cands += ['%04d%02d01' % (y, m), '%04d%02d15' % (y, m)]
    ymd = None
    me = next(r for r in C['regions'] if r['name'] == C['me'])
    for d in cands:
        if d > t.strftime('%Y%m%d'):
            continue
        try:
            txt = http_get(url, {'serviceKey': key, 'pageNo': '1', 'numOfRows': '1', 'opr_ymd': d, 'ctpv_cd': '51', 'sgg_cd': me['sgg'], 'dataType': 'JSON'}, tries=1)
            if '"item"' in txt:
                ymd = d
                break
        except Exception:  # noqa: BLE001
            continue
    if not ymd:
        raise RuntimeError('정류장 자료의 기준일을 찾지 못함')
    out = {}
    for r in C['regions']:
        rows, page = [], 1
        while page <= 10:
            try:
                txt = http_get(url, {'serviceKey': key, 'pageNo': str(page), 'numOfRows': '1000', 'opr_ymd': ymd, 'ctpv_cd': '51', 'sgg_cd': r['sgg'], 'dataType': 'JSON'}, tries=2)
            except Exception as e:  # noqa: BLE001
                log('정류장 %s 실패: %s' % (r['name'], e))
                break
            j = _json.loads(txt)
            body = ((j.get('Response') or j.get('response') or {}).get('body') or {})
            items = (body.get('items') or {}).get('item') or []
            if isinstance(items, dict):
                items = [items]
            rows += items
            if len(items) < 1000:
                break
            page += 1
        stops = {}
        for it in rows:
            sid = str(it.get('sttn_id'))
            o = stops.setdefault(sid, {'n': it.get('sttn_nm'), 'emd': it.get('emd_nm'), 'r': 0})
            o['r'] = max(o['r'], int(it.get('rte_cnt') or 0))
        if not stops:
            continue
        emd = {}
        for o in stops.values():
            e = emd.setdefault(o['emd'] or '기타', [0, 0])
            e[0] += 1
            e[1] += o['r']
        o = {'stops': len(stops), 'avg_routes': round(sum(x['r'] for x in stops.values()) / len(stops), 2), 'max_routes': max(x['r'] for x in stops.values())}
        if r['name'] == C['me']:
            o['emd'] = emd
            o['top'] = sorted(([x['n'], x['emd'], x['r']] for x in stops.values()), key=lambda x: -x[2])[:12]
        out[r['name']] = o
    if C['me'] not in out:
        raise RuntimeError('정류장: 동해시 자료가 없음')
    return {'ymd': ymd, 'regions': out}
