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
            rows = _call(_src(KOR + 'areaBasedList2', dict(APP, LDONG, contentTypeId=t, arrange='Q', numOfRows='300', pageNo='1')), {}, 'places_%s' % t)
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
        rows = _call(_src(KOR + 'searchFestival2', dict(APP, LDONG, eventStartDate=start, arrange='A', numOfRows='200', pageNo='1')), {}, 'festival_search')
    except Exception as e:  # noqa: BLE001
        log('축제 검색 실패: %s' % e)
        rows = []
    for r in rows:
        it = _item(r)
        it.update({'start': str(r.get('eventstartdate') or ''), 'end': str(r.get('eventenddate') or '')})
        seen.add(it['id'])
        out.append(it)
    try:
        rows = _call(_src(KOR + 'areaBasedList2', dict(APP, LDONG, contentTypeId='15', arrange='Q', numOfRows='200', pageNo='1')), {}, 'festival_list')
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


def weather():
    t = now() - _dt.timedelta(minutes=15)
    bases = [2, 5, 8, 11, 14, 17, 20, 23]
    h = max([b for b in bases if b <= t.hour], default=None)
    if h is None:
        t -= _dt.timedelta(days=1)
        h = 23
    bd, bt = t.strftime('%Y%m%d'), '%02d00' % h
    rows = _call(_src(FCST_URL, {'dataType': 'JSON', 'base_date': bd, 'base_time': bt, 'nx': GRID[0], 'ny': GRID[1], 'numOfRows': '1000', 'pageNo': '1'}), {}, 'weather')
    slots = {}
    for r in rows:
        c = r.get('category')
        if c not in KEEP:
            continue
        k = '%s%s' % (r.get('fcstDate'), r.get('fcstTime'))
        slots.setdefault(k, {})[c] = r.get('fcstValue')
    if not slots:
        raise RuntimeError('단기예보 응답이 비어 있음')
    return {'base': bd + bt, 'slots': dict(sorted(slots.items()))}
