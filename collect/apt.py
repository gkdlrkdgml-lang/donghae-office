"""아파트 매매 실거래가(국토교통부 RTMSDataSvcAptTrade): 강원 18개 시·군, 지난해 1월부터 달별.

거래 신고는 계약 후 30일 안이라 최근 3개월은 매번 다시 받고, 그 전 달은 받아 둔 값을 씁니다.
해제(취소)된 거래는 뺍니다. 시·군·달마다 건수·가격 중앙값·㎡당 가격 중앙값, 동해시는 거래 목록(최근 6개월)도 둡니다.
"""
import os
import re
import time
import urllib.parse

from common import http_get, log, now

URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade'
CODES = {'춘천': '51110', '원주': '51130', '강릉': '51150', '동해': '51170', '태백': '51190', '속초': '51210', '삼척': '51230',
         '홍천': '51720', '횡성': '51730', '영월': '51750', '평창': '51760', '정선': '51770', '철원': '51780', '화천': '51790',
         '양구': '51800', '인제': '51810', '고성': '51820', '양양': '51830'}
ME = '동해'
REFRESH = 3     # 최근 3개월은 매번 다시
LIST_M = 6      # 동해 거래 목록 보관 개월
BUDGET = 360


def _key():
    k = urllib.parse.unquote(os.environ.get('DATA_GO_KR_KEY', '').strip())
    if not k:
        raise RuntimeError('DATA_GO_KR_KEY 없음')
    return k


def _tag(x, t):
    m = re.search(r'<%s>(.*?)</%s>' % (t, t), x, re.S)
    return m.group(1).strip() if m else ''


def _med(a):
    a = sorted(a)
    n = len(a)
    if not n:
        return None
    return a[n // 2] if n % 2 else (a[n // 2 - 1] + a[n // 2]) / 2


def _month(k, code, ym):
    out, page = [], 1
    while page <= 20:
        t = http_get(URL, {'serviceKey': k, 'LAWD_CD': code, 'DEAL_YMD': ym, 'numOfRows': '1000', 'pageNo': str(page)}, tries=2, timeout=60)
        rc = _tag(t, 'resultCode')
        if rc and rc not in ('00', '000'):
            raise RuntimeError('%s %s' % (rc, _tag(t, 'resultMsg')))
        it = re.findall(r'<item>(.*?)</item>', t, re.S)
        for x in it:
            if _tag(x, 'cdealType'):          # 해제된 거래
                continue
            try:
                amt = float(_tag(x, 'dealAmount').replace(',', ''))   # 만원
                ar = float(_tag(x, 'excluUseAr') or 0)
            except ValueError:
                continue
            out.append({'nm': _tag(x, 'aptNm'), 'dong': _tag(x, 'umdNm'), 'ar': round(ar, 2), 'amt': amt,
                        'fl': _tag(x, 'floor'), 'by': _tag(x, 'buildYear'), 'd': _tag(x, 'dealDay')})
        tot = int(_tag(t, 'totalCount') or 0)
        if not it or page * 1000 >= tot:
            break
        page += 1
    return out


def _stat(rows):
    amts = [r['amt'] for r in rows]
    per = [r['amt'] / r['ar'] for r in rows if r['ar'] > 0]
    return {'n': len(rows), 'med': _med(amts), 'per': round(_med(per), 1) if per else None, 'pa': sorted(round(x) for x in per)}


def collect(cache):
    k = _key()
    t0 = time.time()
    today = now().date()
    old = cache if isinstance(cache, dict) and cache.get('v') == 1 else {}
    st = {r: dict(v) for r, v in (old.get('stat') or {}).items()}
    lst = dict(old.get('list') or {})
    months = []
    y, m = today.year - 1, 1
    while (y, m) <= (today.year, today.month):
        months.append('%04d%02d' % (y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    fresh = set(months[-REFRESH:])
    errs, calls = [], 0
    jobs = [(ym, reg, code) for ym in reversed(months) for reg, code in CODES.items() if ym in fresh or ym not in st.get(reg, {})]
    # 한 번 부르는 데 몇 초씩 걸려 6개씩 함께 받음(최근 달부터, 시간이 모자라면 오래된 달은 다음 실행에서)
    from concurrent.futures import ThreadPoolExecutor
    def one(j):
        if time.time() - t0 > BUDGET:
            return j, None, None
        try:
            return j, _month(k, j[2], j[0]), None
        except Exception as e:  # noqa: BLE001
            return j, None, e
    with ThreadPoolExecutor(6) as ex:
        for (ym, reg, code), rows, e in ex.map(one, jobs):
            if e is not None:
                if len(errs) < 6:
                    errs.append('%s %s: %s' % (reg, ym, str(e)[:120]))
                continue
            if rows is None:
                continue
            calls += 1
            st.setdefault(reg, {})[ym] = _stat(rows)
            if reg == ME and ym in months[-LIST_M:]:
                lst[ym] = sorted(rows, key=lambda r: (r['d'].zfill(2), r['amt']), reverse=True)
    keep = set(months)
    st = {r: {m: v for m, v in d.items() if m in keep} for r, d in st.items()}
    lst = {m: v for m, v in lst.items() if m in months[-LIST_M:]}
    # 올해 1월~지난달, 지난해 같은 기간(이번 달은 신고가 덜 들어와 뺌)
    cy, cm = today.year, today.month - 1
    if cm < 1:
        cy, cm = cy - 1, 12
    ytd = {}
    for reg, d in st.items():
        cur = ['%04d%02d' % (cy, i) for i in range(1, cm + 1)]
        prv = ['%04d%02d' % (cy - 1, i) for i in range(1, cm + 1)]
        def agg(ms):
            if not all(m in d for m in ms):
                return None, None
            pa = [x for m in ms for x in (d[m].get('pa') or [])]
            return sum(d[m]['n'] for m in ms), _med(pa)
        n1, p1 = agg(cur); n0, p0 = agg(prv)
        ytd[reg] = {'n': n1, 'per': p1, 'n_prev': n0, 'per_prev': p0}
    if not any(st.values()):
        raise RuntimeError('아파트 실거래 없음 · ' + ' / '.join(errs))
    log('아파트 실거래: %d회 호출, 오류 %d' % (calls, len(errs)))
    return {'v': 1, 'me': ME, 'months': months, 'ytd': ytd, 'ytd_to': '%04d%02d' % (cy, cm), 'stat': st, 'list': lst, 'errors': errs, 'fetched': now().strftime('%Y-%m-%d %H:%M')}
