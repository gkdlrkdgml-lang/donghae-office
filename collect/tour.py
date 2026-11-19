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
    seen, out = set(), []
    for x in res:
        if not x['title'] or not x['start']:
            continue
        k = (_re.sub(r'\s', '', x['title']), x['start'])
        if k in seen:
            continue
        seen.add(k)
        x['title'] = str(x['title']).strip()
        out.append(x)
    out.sort(key=lambda x: x['start'])
    return out
