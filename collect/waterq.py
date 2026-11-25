"""수돗물 법정 수질검사(월별): 한국수자원공사 상수도법정수질정보(qltWtrSvc/MonPurification).

강원특별자치도 전체 정수장(약 70곳)을 달마다 받아 18개 시·군 비교와 동해시 정수장 표에 씁니다.
지난 달 결과는 바뀌지 않으므로 최근 2개월만 다시 받고, 13개월을 보관합니다.
"""
import json
import os
import urllib.parse

from common import http_get, log, now

URL = 'https://apis.data.go.kr/B500001/qltWtrSvc/MonPurification'
BSI = '강원특별자치도'
KEEP = 13
# 화면에 쓰는 항목만(그 밖의 60여 항목은 버림)
F = {'SIGNGU_NM': 'sg', 'FCLT_NAM': 'f', 'COLL_DAT': 'd', 'RC': 'rc', 'TU': 'tu', 'PH': 'ph', 'HR': 'hr',
     'TC': 'tc', 'EFC': 'ec', 'TW': 'tw', 'ODOR': 'od', 'CL': 'cl', 'INORG_NAM': 'lab', 'UPDATE_DAT': 'up'}


def _key():
    k = urllib.parse.unquote(os.environ.get('DATA_GO_KR_KEY', '').strip())
    if not k:
        raise RuntimeError('DATA_GO_KR_KEY 없음')
    return k


def _month(k, y, m):
    rows, page = [], 1
    while page <= 5:
        t = http_get(URL, {'serviceKey': k, 'viewType': 'json', 'pageNo': str(page), 'numOfRows': '200',
                           'year': str(y), 'month': '%02d' % m, 'BSI': BSI}, tries=2, timeout=60)
        j = json.loads(t)
        bd = (j.get('response') or {}).get('body') or {}
        it = bd.get('items') or []
        for x in it:
            r = {}
            for a, b in F.items():
                v = x.get(a)
                if v is None:
                    continue
                if b in ('rc', 'tu', 'ph', 'hr', 'cl'):
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        continue
                r[b] = v
            if r.get('sg') and r.get('f'):
                rows.append(r)
        tot = int(((bd.get('itemsInfo') or {}).get('totalCount')) or 0)
        if not it or page * 200 >= tot:
            break
        page += 1
    return rows


def collect(cache):
    k = _key()
    today = now().date()
    old = dict((cache or {}).get('months') or {}) if isinstance(cache, dict) else {}
    ms = []
    y, m = today.year, today.month
    for _ in range(KEEP + 1):          # 이번 달은 아직 없을 수 있어 하나 더
        ms.append((y, m))
        m -= 1
        if m < 1:
            m, y = 12, y - 1
    errs = []
    for i, (y, m) in enumerate(ms):
        key = '%04d%02d' % (y, m)
        if key in old and i > 2:       # 최근 3개월(이번 달 포함)만 다시
            continue
        try:
            rows = _month(k, y, m)
            if rows:
                old[key] = rows
        except Exception as e:  # noqa: BLE001
            if len(errs) < 4:
                errs.append('%s: %s' % (key, str(e)[:120]))
    keep = sorted(old)[-KEEP:]
    out = {mk: old[mk] for mk in keep}
    if not out:
        raise RuntimeError('수질검사 자료 없음 · ' + ' / '.join(errs))
    log('수질검사: %s~%s, 최근 달 %d곳' % (keep[0], keep[-1], len(out[keep[-1]])))
    return {'v': 1, 'months': out, 'latest': keep[-1], 'errors': errs, 'fetched': now().strftime('%Y-%m-%d %H:%M')}


FEE_URL = 'https://www.dh.go.kr/sudo/waterpay/ncoe/fee/feeCalcStand.do'


def fee():
    """동해시 상하수도사업소 요금 산정기준 페이지의 표(상수도·구경별 정액·하수도)를 그대로 읽음."""
    import re
    import ssl
    import urllib.request as ur
    ctx = ssl.create_default_context()
    ctx.set_ciphers('DEFAULT:@SECLEVEL=1')      # 사이트가 예전 암호 방식만 받음
    h = ur.urlopen(ur.Request(FEE_URL, headers={'User-Agent': 'Mozilla/5.0'}), timeout=40, context=ctx).read().decode('utf-8', 'ignore')
    tabs = []
    for t in re.findall(r'<table.*?</table>', h, re.S):
        cap = re.search(r'<caption>(.*?)</caption>', t, re.S)
        cap = re.sub(r'\s+', ' ', cap.group(1)).strip() if cap else ''
        if not any(w in cap for w in ('상수도 요금', '정액요금', '하수도 요금')):
            continue
        rows = []
        for tr in re.findall(r'<tr.*?</tr>', t, re.S):
            cells = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', c)).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', tr, re.S)]
            if cells:
                rows.append(cells)
        kind = 'sewer' if '하수도 요금' in cap else 'base' if '정액' in cap else 'water'
        tabs.append({'kind': kind, 'cap': cap, 'rows': rows})
    if not any(x['kind'] == 'water' for x in tabs):
        raise RuntimeError('요금표를 찾지 못함')
    return {'url': FEE_URL, 'tables': tabs, 'fetched': now().strftime('%Y-%m-%d')}
