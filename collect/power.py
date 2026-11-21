"""에너지·전력: 한전 전력데이터 개방포털(bigdata.kepco.co.kr) Open API.

키: GitHub Secret KEPCO_KEY (한전 포털에서 받은 40자리 키)
- 계약종별 전력사용량(주택용·일반용·교육용·산업용·농사용·가로등·심야) → 시·군 월별
- 가구 평균 전력사용량·요금 → 시·군 월별
- 산업분류별 전력사용량 → 최신 달만
지난 달 자료는 바뀌지 않으므로 한 번 받은 달은 다시 받지 않습니다.
"""
import json
import os
import time

from common import http_get, log, now, ym_shift

BASE = 'https://bigdata.kepco.co.kr/openapi/v1/'
METRO = '51'   # 강원(한전 코드표에서는 32도 강원이지만 51로 불러도 강원 18개 시·군이 나옴)
KEEP = 25      # 25개월 보관(13개월 추이 + 전년 같은 달 비교)


def _get(path, params):
    key = os.environ.get('KEPCO_KEY', '').strip()
    if not key:
        raise RuntimeError('KEPCO_KEY 없음')
    q = dict(params)
    q.update({'apiKey': key, 'returnType': 'json', 'metroCd': METRO})
    last = None
    for i in range(4):   # 한전 서버가 자주 끊겨서 몇 번 더 시도합니다
        try:
            t = http_get(BASE + path, q, tries=1, timeout=40)
            j = json.loads(t)
            return j.get('data') or []
        except Exception as e:  # noqa: BLE001
            last = e
            if '404' in str(e):
                return []      # 아직 공표 안 된 달
            time.sleep([3, 8, 15, 20][i])
    raise RuntimeError(str(last).replace(key, '***')[:200])


def _num(x):
    try:
        return float(str(x).replace(',', ''))
    except (TypeError, ValueError):
        return None


def _month(y, m, names):
    """한 달치: 계약종별 + 가구평균. 18개 시·군이 다 있어야 그 달을 씁니다."""
    rows = _get('powerUsage/contractType.do', {'year': y, 'month': m})
    out = {}
    for r in rows:
        n = names.get(r.get('city'))
        if not n:
            continue
        d = out.setdefault(n, {'total': 0.0, 'cust': 0.0, 'bill': 0.0, 'by': {}})
        k = str(r.get('cntr', '')).replace(' ', '')
        u, c, b = _num(r.get('powerUsage')), _num(r.get('custCnt')), _num(r.get('bill'))
        if u is None:
            continue
        d['by'][k] = {'kwh': u, 'cust': c, 'bill': b}
        d['total'] += u
        d['cust'] += c or 0
        d['bill'] += b or 0
    if len(out) < len(names):
        return None
    time.sleep(1)
    for r in _get('powerUsage/houseAve.do', {'year': y, 'month': m}):
        n = names.get(r.get('city'))
        if n in out:
            out[n]['house'] = {'cnt': _num(r.get('houseCnt')), 'kwh': _num(r.get('powerUsage')), 'bill': _num(r.get('bill'))}
    return out


def _biz(y, m, names):
    out = {}
    for r in _get('powerUsage/industryType.do', {'year': y, 'month': m}):
        n = names.get(r.get('city'))
        u = _num(r.get('powerUsage'))
        if n and u is not None:
            out.setdefault(n, {})[r.get('biz')] = u
    return out


def collect(C, prev=None):
    names = {r['full']: r['name'] for r in C['regions']}
    prev = prev or {}
    months = dict(prev.get('months') or {})
    errors = []
    cur = '%04d%02d' % (now().year, now().month)
    # 1) 가장 최근 공표된 달 찾기(보통 2달 전)
    latest = None
    for back in range(1, 7):
        ym = ym_shift(cur, -back)
        if ym in months and months[ym]:
            if all('house' in v for v in months[ym].values()):
                latest = ym
                break
        try:
            d = _month(ym[:4], ym[4:], names)
        except Exception as e:  # noqa: BLE001
            errors.append('%s %s' % (ym, e))
            continue
        if d:
            months[ym] = d
            latest = ym
            break
        time.sleep(1)
    if not latest:
        raise RuntimeError('최근 6개월 자료를 받지 못함: %s' % '; '.join(errors[-3:]))
    # 2) 비어 있는 지난 달 채우기(최근 25개월)
    for back in range(1, KEEP):
        ym = ym_shift(latest, -back)
        if ym in months and all('house' in v for v in months[ym].values()):
            continue
        try:
            d = _month(ym[:4], ym[4:], names)
            if d:
                months[ym] = d
        except Exception as e:  # noqa: BLE001
            errors.append('%s %s' % (ym, e))
        time.sleep(1)
    keep = sorted(months)[-KEEP:]
    months = {k: months[k] for k in keep if k <= latest}
    # 3) 최신 달 산업분류
    biz, biz_ym = prev.get('biz') or {}, prev.get('biz_ym')
    if biz_ym != latest or not biz:
        try:
            b = _biz(latest[:4], latest[4:], names)
            if b:
                biz, biz_ym = b, latest
        except Exception as e:  # noqa: BLE001
            errors.append('산업분류 %s' % e)
    if errors:
        log('전력 일부 실패: %s' % '; '.join(errors[:5]))
    return {'at': now().strftime('%Y-%m-%d'), 'ym': latest, 'months': months,
            'biz': biz, 'biz_ym': biz_ym,
            'errors': errors[:5], 'source': '한전 전력데이터 개방포털'}
