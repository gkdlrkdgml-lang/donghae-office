"""2단계 생활 분야 수집: 보건(의료기관), 교통(전기차 충전기), 환경(대기질), 관광(방문자).

모두 공공데이터포털 키(DATA_GO_KR_KEY) 하나로 부릅니다.
값은 강원 18개 시·군 단위로 모아 run.py가 지표·화면 자료로 씁니다.
"""
import datetime as _dt

from common import to_num, match_region, log, now
from sources import _call

KEY = 'DATA_GO_KR_KEY'


def _src(url, params):
    return {'url': url, 'key_env': KEY, 'params': params}


# ---------------------------------------------------------------- 보건: 의료기관
HOSP_URL = 'https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList'


def hospitals(C):
    """심평원 병원정보: 강원 요양기관(약국 제외)을 시·군·종별로 셉니다."""
    rows = _call(_src(HOSP_URL, {'sidoCd': '320000', 'numOfRows': '1000', 'pageNo': '1', '_type': 'json'}), {}, 'hospitals')
    out = {}
    mine = []
    for r in rows:
        name = match_region(r.get('sgguCdNm'), C['regions'])
        if not name:
            continue
        kind = str(r.get('clCdNm') or '기타').strip()
        d = out.setdefault(name, {'total': 0, 'doctors': 0, 'kinds': {}})
        d['total'] += 1
        d['doctors'] += int(to_num(r.get('drTotCnt')) or 0)
        d['kinds'][kind] = d['kinds'].get(kind, 0) + 1
        if name == C['me']:
            mine.append({'name': r.get('yadmNm'), 'kind': kind, 'dong': r.get('emdongNm'), 'doctors': int(to_num(r.get('drTotCnt')) or 0),
                         'lat': to_num(r.get('YPos')), 'lng': to_num(r.get('XPos'))})
    if len(out) < 15:
        raise RuntimeError('의료기관 응답에서 강원 시·군을 다 찾지 못함(%d)' % len(out))
    # 약국(심평원 약국정보서비스) — 실패하면 약국 없이 진행
    try:
        prow = _call(_src('https://apis.data.go.kr/B551182/pharmacyInfoService/getParmacyBasisList', {'sidoCd': '320000', 'numOfRows': '1000', 'pageNo': '1', '_type': 'json'}), {}, 'pharmacy')
        for r in prow:
            name = match_region(r.get('sgguCdNm'), C['regions'])
            if not name or name not in out:
                continue
            d = out[name]
            d['total'] += 1
            d['kinds']['약국'] = d['kinds'].get('약국', 0) + 1
    except Exception as e:  # noqa: BLE001
        log('약국 실패: %s' % e)
    mine.sort(key=lambda x: -x['doctors'])
    return {'regions': out, 'mine': mine[:40], 'at': now().strftime('%Y-%m-%d')}


# ---------------------------------------------------------------- 교통: 전기차 충전기
EV_URL = 'https://apis.data.go.kr/B552584/EvCharger/getChargerInfo'
SLOW = {'02', '08'}


def ev_chargers(C):
    """환경공단 충전기 정보: 강원(zcode 51) 충전기를 시·군별 급속·완속으로 셉니다."""
    rows = _call(_src(EV_URL, {'zcode': '51', 'dataType': 'JSON', 'numOfRows': '9999', 'pageNo': '1'}), {}, 'ev')
    by_sgg = {r['sgg']: r['name'] for r in C['regions']}
    out = {}
    seen = set()
    for r in rows:
        if str(r.get('delYn', 'N')).upper() == 'Y':
            continue
        key = (r.get('statId'), r.get('chgerId'))
        if key in seen:
            continue
        seen.add(key)
        name = by_sgg.get(str(r.get('zscode', ''))[:5]) or match_region(r.get('addr'), C['regions'])
        if not name:
            continue
        d = out.setdefault(name, {'total': 0, 'fast': 0, 'slow': 0, 'stations': set(), 'busy': 0})
        d['total'] += 1
        d['slow' if str(r.get('chgerType')) in SLOW else 'fast'] += 1
        d['stations'].add(r.get('statId'))
        if str(r.get('stat')) == '3':
            d['busy'] += 1
    for d in out.values():
        d['stations'] = len(d['stations'])
    if len(out) < 15:
        raise RuntimeError('충전기 응답에서 강원 시·군을 다 찾지 못함(%d)' % len(out))
    return {'regions': out, 'at': now().strftime('%Y-%m-%d')}


# ---------------------------------------------------------------- 환경: 대기질(실시간)
AIR_URL = 'https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty'
STN_URL = 'https://apis.data.go.kr/B552584/MsrstnInfoInqireSvc/getMsrstnList'


def air(C):
    """에어코리아: 강원 측정소 실시간 값 → 시·군별 평균(측정소가 없는 군은 빠짐)."""
    stns = _call(_src(STN_URL, {'addr': '강원', 'returnType': 'json', 'numOfRows': '200', 'pageNo': '1'}), {}, 'air_stations')
    where = {}
    for s in stns:
        name = match_region(s.get('addr'), C['regions'])
        if name:
            where[s.get('stationName')] = name
    rows = _call(_src(AIR_URL, {'sidoName': '강원', 'returnType': 'json', 'numOfRows': '200', 'pageNo': '1', 'ver': '1.0'}), {}, 'air_now')
    reg, mine, t = {}, [], None
    for r in rows:
        name = where.get(r.get('stationName'))
        if not name:
            continue
        pm25, pm10 = to_num(r.get('pm25Value')), to_num(r.get('pm10Value'))
        t = r.get('dataTime') or t
        d = reg.setdefault(name, {'pm25': [], 'pm10': []})
        if pm25 is not None:
            d['pm25'].append(pm25)
        if pm10 is not None:
            d['pm10'].append(pm10)
        if name == C['me']:
            mine.append({'station': r.get('stationName'), 'pm25': pm25, 'pm10': pm10, 'o3': to_num(r.get('o3Value')),
                         'no2': to_num(r.get('no2Value')), 'khai': to_num(r.get('khaiValue')), 'grade': r.get('khaiGrade')})
    out = {}
    for k, d in reg.items():
        out[k] = {'pm25': round(sum(d['pm25']) / len(d['pm25']), 1) if d['pm25'] else None,
                  'pm10': round(sum(d['pm10']) / len(d['pm10']), 1) if d['pm10'] else None, 'n': max(len(d['pm25']), len(d['pm10']))}
    if not out:
        raise RuntimeError('대기질 응답에서 강원 시·군 값을 못 찾음')
    return {'regions': out, 'mine': mine, 'time': t}


# ---------------------------------------------------------------- 관광: 방문자
VISIT_URL = 'https://apis.data.go.kr/B551011/DataLabService/locgoRegnVisitrDDList'


def _visit_rows(start, end):
    return _call(_src(VISIT_URL, {'MobileOS': 'ETC', 'MobileApp': 'donghae', '_type': 'json', 'numOfRows': '10000', 'pageNo': '1',
                                  'startYmd': start, 'endYmd': end}), {}, 'visit_%s' % start)


def _gangwon(r):
    t = ' '.join(str(r.get(k, '')) for k in ('areaNm', 'areaCode', 'signguCode'))
    return '강원' in t or str(r.get('signguCode', '')).startswith(('51', '42')) or str(r.get('areaCode', '')) in ('51', '42', '32')


def visitors(C, cache, days=None, n_months=37):
    """관광공사 데이터랩: 시·군별 월 방문자(현지인·외지인·외국인).

    cache = {'YYYYMM': {시군: {...}}}, days = {'YYYYMMDD': [현지인, 외지인, 외국인]} (동해시 일별) 를 이어서 채웁니다.
    최근 n_months개월(3년+1달)을 보관하고, 마지막 날이 든 달은 일별만 매번 새로 받습니다.
    """
    cache = dict(cache or {})
    days = dict(days or {})
    today = now().date()
    last = None
    for back in range(1, 70, 3):
        d = today - _dt.timedelta(days=back)
        rows = _visit_rows(d.strftime('%Y%m%d'), d.strftime('%Y%m%d'))
        if rows:
            last = d
            break
    if not last:
        raise RuntimeError('방문자 자료를 최근 70일 안에서 찾지 못함')
    # 마지막 날 뒤로 더 있는지 하루씩 확인
    for fwd in range(1, 3):
        d = last + _dt.timedelta(days=fwd)
        if d >= today or not _visit_rows(d.strftime('%Y%m%d'), d.strftime('%Y%m%d')):
            break
        last = d
    first_of = _dt.date(last.year, last.month, 1)
    full_end = first_of - _dt.timedelta(days=1) if last.day < 28 else last
    months = []
    y, m = full_end.year, full_end.month
    for _ in range(n_months):
        months.append('%04d%02d' % (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12

    def fetch(start, end):
        rows = _visit_rows(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'))
        agg, dd = {}, {}
        for r in rows:
            if not _gangwon(r):
                continue
            name = match_region(r.get('signguNm'), C['regions'])
            if not name:
                continue
            v = to_num(r.get('touNum')) or 0
            div = str(r.get('touDivCd') or r.get('touDivNm') or '')
            idx = 0 if div in ('1', '현지인(a)', '현지인') else 1 if div in ('2', '외지인(b)', '외지인') else 2 if div in ('3', '외국인(c)', '외국인') else None
            key = ('local', 'outside', 'foreign')[idx] if idx is not None else 'other'
            d = agg.setdefault(name, {'local': 0, 'outside': 0, 'foreign': 0, 'other': 0})
            d[key] += v
            if name == C['me'] and idx is not None:
                ymd = str(r.get('baseYmd'))
                dd.setdefault(ymd, [0, 0, 0])[idx] += round(v)
        return agg, dd
    for ym in months:
        y, m = int(ym[:4]), int(ym[4:])
        start = _dt.date(y, m, 1)
        end = (_dt.date(y + (m == 12), m % 12 + 1, 1) - _dt.timedelta(days=1))
        have_days = sum(1 for k in days if k.startswith(ym))
        if ym in cache and have_days >= end.day:
            continue
        try:
            agg, dd = fetch(start, end)
        except Exception as e:  # noqa: BLE001
            log('방문자 %s 실패: %s' % (ym, e))
            continue
        if len(agg) >= 15:
            cache[ym] = agg
            days.update(dd)
        else:
            log('방문자 %s: 강원 시·군 %d곳만 있어 보관 안 함' % (ym, len(agg)))
    if last >= first_of and full_end < last:  # 진행 중인 달은 일별만
        try:
            _, dd = fetch(first_of, last)
            days.update(dd)
        except Exception as e:  # noqa: BLE001
            log('방문자 이번 달 일별 실패: %s' % e)
    keep = sorted(cache)[-n_months:]
    lo = keep[0] + '01' if keep else '0'
    days = {k: v for k, v in days.items() if k >= lo}
    return {k: cache[k] for k in keep}, last.strftime('%Y-%m-%d'), dict(sorted(days.items()))
