"""사망 분석: 국가데이터처 사망원인통계 「시군구/사망원인(50항목)/성/사망자수, 사망률, 연령표준화 사망률」(KOSIS 101/DT_1B34E13).

강원 18개 시·군과 강원·전국을 최근 5년 받아, 사망원인별 사망자 수·조사망률·연령표준화 사망률을 둡니다.
해마다 9월에 지난해 자료가 나오므로 1주일마다 확인합니다.
"""
import json
import os

from common import http_get, log, now

URL = 'https://kosis.kr/openapi/Param/statisticsParameterData.do'
TBL = 'DT_1B34E13'
GW = ['32'] + ['32%03d' % i for i in range(10, 450, 10)]   # 강원 + 시·군 코드(없는 코드는 응답에 안 나옴)


def collect(cache):
    k = os.environ.get('KOSIS_KEY', '').strip()
    if not k:
        raise RuntimeError('KOSIS_KEY 없음')
    rows = []
    for reg in (['00'] + GW,):
        prm = {'method': 'getList', 'format': 'json', 'jsonVD': 'Y', 'orgId': '101', 'tblId': TBL, 'prdSe': 'Y',
               'newEstPrdCnt': '5', 'itmId': 'T1+T4+T7', 'objL1': 'ALL', 'objL2': '+'.join(reg) + '+', 'objL3': '0', 'apiKey': k}
        t = http_get(URL, prm, tries=2, timeout=120)
        j = json.loads(t)
        if isinstance(j, dict):
            raise RuntimeError('KOSIS 오류 %s' % str(j)[:200])
        rows += j
    causes, regs = {}, {}
    for r in rows:
        try:
            v = float(r.get('DT'))
        except (TypeError, ValueError):
            continue
        cc, cn = r.get('C1'), (r.get('C1_NM') or '').strip()
        rn = (r.get('C2_NM') or '').strip().replace('강원특별자치도', '강원').replace('강원도', '강원')
        rn = {'전국': '전국', '강원': '강원'}.get(rn, rn.replace('시', '') if rn.endswith('시') else rn[:-1] if rn.endswith('군') else rn)
        y = r.get('PRD_DE')
        i = {'T1': 0, 'T4': 1, 'T7': 2}.get(r.get('ITM_ID'))
        if i is None:
            continue
        causes[cc] = cn
        regs.setdefault(rn, {}).setdefault(y, {}).setdefault(cc, [None, None, None])[i] = v
    years = sorted({y for d in regs.values() for y in d})
    if '동해' not in regs or not years:
        raise RuntimeError('동해 사망원인 자료 없음')
    log('사망원인: %s~%s, 지역 %d, 원인 %d' % (years[0], years[-1], len(regs), len(causes)))
    return {'v': 1, 'table': TBL, 'years': years, 'causes': causes, 'regions': regs, 'fetched': now().strftime('%Y-%m-%d')}
