"""항만물류: 해양수산부 PORT-MIS 통계(월별).

- 항만별 선박입출항실적(1192000/SsopVsslEtryndHarbor2/YM): 항만·선박 구분(국적선·외국선·연안선)별 입출항 척수·톤수
- 연안화물 수송실적(1192000/SsopCargFrghtCoastal2/Ym): 항만별 연안화물 톤수
지난해 1월부터 받습니다. 지난 달 통계는 바뀌지 않으므로 최근 3개월만 다시 받습니다.
"""
import os
import re
import urllib.parse

from common import http_get, log, now

B = 'https://apis.data.go.kr/1192000/'
ME = '동해.묵호'


def _key():
    k = urllib.parse.unquote(os.environ.get('DATA_GO_KR_KEY', '').strip())
    if not k:
        raise RuntimeError('DATA_GO_KR_KEY 없음')
    return k


def _tag(x, t):
    m = re.search(r'<%s>(.*?)</%s>' % (t, t), x, re.S)
    return m.group(1).strip() if m else ''


def _num(v):
    try:
        return float(v.replace(',', ''))
    except (ValueError, AttributeError):
        return 0.0


def _pages(url, prm):
    """전 페이지의 <item> 본문을 돌려줍니다."""
    out, page = [], 1
    while page <= 40:
        q = dict(prm); q.update({'pageNo': str(page), 'numOfRows': '100'})
        t = http_get(url, q, tries=2, timeout=60)
        code = _tag(t, 'resultCode')
        if code and code not in ('00', '000'):
            raise RuntimeError('%s %s' % (code, _tag(t, 'resultMsg')))
        it = re.findall(r'<item>(.*?)</item>', t, re.S)
        out += it
        tot = int(_tag(t, 'totalCount') or 0)
        if not it or len(out) >= tot:
            break
        page += 1
    return out


def collect(cache):
    k = _key()
    today = now().date()
    y0 = today.year - 1
    old = cache if isinstance(cache, dict) and cache.get('v') == 1 else {}
    vs, cg = dict(old.get('vessel') or {}), dict(old.get('cargo') or {})
    # 다시 받을 시작 달: 받아 둔 마지막 달의 3개월 전(처음이면 지난해 1월)
    have = sorted(set(vs) & set(cg))
    if have:
        ly, lm = int(have[-1][:4]), int(have[-1][4:])
        lm -= 3
        while lm < 1:
            lm += 12; ly -= 1
        sym = '%04d%02d' % (max(ly, y0), lm if ly >= y0 else 1)
    else:
        sym = '%04d01' % y0
    eym = '%04d%02d' % (today.year, today.month)
    errs = []
    try:
        for x in _pages(B + 'SsopVsslEtryndHarbor2/YM', {'serviceKey': k, 'sym': sym, 'eym': eym}):
            ym, pt = _tag(x, 'useYm'), _tag(x, 'prtAgNm')
            if not ym or not pt:
                continue
            row = {}
            for d in re.findall(r'<detail>(.*?)</detail>', x, re.S):
                nm = _tag(d, 'nm') or '계'
                row[nm] = [_num(_tag(d, 'etrVsslCo')), _num(_tag(d, 'etrGrtg')), _num(_tag(d, 'satVsslCo')), _num(_tag(d, 'satGrtg'))]
            if row:
                vs.setdefault(ym, {})[pt] = row
    except Exception as e:  # noqa: BLE001
        errs.append('입출항: %s' % str(e)[:160]); log('항만 입출항 실패: %s' % e)
    try:
        for x in _pages(B + 'SsopCargFrghtCoastal2/Ym', {'serviceKey': k, 'sym': sym, 'eym': eym}):
            ym = _tag(x, 'useYm')
            if not ym:
                continue
            for d in re.findall(r'<detail>(.*?)</detail>', x, re.S):
                pt = _tag(d, 'prtAgNm')
                if pt:
                    cg.setdefault(ym, {})[pt] = _num(_tag(d, 'prtAgTon'))
    except Exception as e:  # noqa: BLE001
        errs.append('연안화물: %s' % str(e)[:160]); log('항만 연안화물 실패: %s' % e)
    # 지난해 1월 이전은 버림, 값이 하나도 없는 달은 버림
    vs = {m: v for m, v in vs.items() if m >= '%04d01' % y0 and v}
    cg = {m: v for m, v in cg.items() if m >= '%04d01' % y0 and any(v.values())}
    if not vs and not cg:
        raise RuntimeError('항만 통계 없음 · ' + ' / '.join(errs))
    log('항만: 입출항 %s~%s, 연안화물 %s~%s' % (min(vs) if vs else '-', max(vs) if vs else '-', min(cg) if cg else '-', max(cg) if cg else '-'))
    return {'v': 1, 'me': ME, 'vessel': vs, 'cargo': cg, 'errors': errs[:4], 'fetched': now().strftime('%Y-%m-%d %H:%M')}
