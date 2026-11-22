"""수협 위판 실적(해양수산부_위판장별위탁판매현황, 공공데이터포털 15102792 · 달마다 파일 → 자동 API).

- 강원 8개 수협(산지조합코드 305~312): 강원고성·동해시·삼척·속초·양양·대포·강릉시·원덕
- 동해시수협: 최근 25개월(어종별·일별), 나머지 강원 수협: 최근 13개월(합계·어종별)
- 지난 달은 다시 받지 않음(캐시). 한 번에 6분까지만 받고 나머지는 다음 실행에서 채움.
금액은 원, 중량은 위판중량 합계(kg).
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

from common import now, log

DOCS = 'https://infuser.odcloud.kr/oas/docs?namespace=15102792/v1'
API = 'https://api.odcloud.kr/api'
ME = 306          # 동해시수산업협동조합
KEEP_ME, KEEP_GW = 25, 13
BUDGET = 360      # 초


def _get(url, timeout=120):
    req = urllib.request.Request(url, headers={'User-Agent': 'donghae-office-collector/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def months_index():
    """{'YYYYMM': '/15102792/v1/uddi:...'} — 파일 이름 끝 날짜(YYYYMMDD)의 달."""
    d = _get(DOCS, 60)
    out = {}
    for path, v in (d.get('paths') or {}).items():
        m = re.search(r'_(\d{8})$', ((v.get('get') or {}).get('summary') or ''))
        if m:
            ym = m.group(1)[:6]
            if ym not in out or path > out[ym]:
                out[ym] = path
    return out


def _rows(path, key, cond, deadline):
    page, per, got = 1, 5000, []
    while True:
        if time.time() > deadline:
            raise TimeoutError('시간 초과')
        prm = dict({'page': page, 'perPage': per, 'serviceKey': key}, **cond)
        for i in range(3):
            try:
                j = _get(API + path + '?' + urllib.parse.urlencode(prm))
                break
            except Exception:  # noqa: BLE001
                if i == 2:
                    raise
                time.sleep(4 * (i + 1))
        got += j.get('data') or []
        if len(got) >= int(j.get('matchCount') or 0) or not j.get('data'):
            return got
        page += 1


def _num(x):
    try:
        return float(str(x).replace(',', ''))
    except Exception:  # noqa: BLE001
        return 0.0


def summarize(rows, with_days):
    by = {}
    for r in rows:
        c = int(_num(r.get('산지조합코드')))
        o = by.setdefault(c, {'name': r.get('산지조합명'), 'amt': 0.0, 'kg': 0.0, 'sp': {}, 'days': {}})
        a, w = _num(r.get('위판금액')), _num(r.get('위판중량'))
        o['amt'] += a
        o['kg'] += w
        nm = str(r.get('수산물표준코드명') or '기타').strip()
        s = o['sp'].setdefault(nm, [0.0, 0.0])
        s[0] += a
        s[1] += w
        if with_days and c == ME:
            dd = str(r.get('위판일자') or '')[:10]
            t = o['days'].setdefault(dd, [0.0, 0.0])
            t[0] += a
            t[1] += w
    for o in by.values():
        o['amt'], o['kg'] = round(o['amt']), round(o['kg'], 1)
        o['sp'] = {k: [round(v[0]), round(v[1], 1)] for k, v in sorted(o['sp'].items(), key=lambda kv: -kv[1][0])[:40]}
        o['days'] = {k: [round(v[0]), round(v[1], 1)] for k, v in sorted(o['days'].items())}
    return {str(k): v for k, v in by.items()}


def collect(prev=None):
    key = urllib.parse.unquote(os.environ.get('DATA_GO_KR_KEY', '').strip())
    if not key:
        raise RuntimeError('DATA_GO_KR_KEY 없음')
    out = dict(prev or {})
    months = dict(out.get('months') or {})
    idx = months_index()
    yms = sorted(idx)[-KEEP_ME:]
    latest = yms[-1]
    deadline = time.time() + BUDGET
    errors = {}
    for ym in reversed(yms):   # 최신 달부터
        rec = months.get(ym) or {}
        gw_need = ym in yms[-KEEP_GW:] and not rec.get('gw')
        me_need = not rec.get('me')
        if ym == latest and rec.get('path') != idx[ym]:   # 최신 달 파일이 바뀌면(정정) 다시
            gw_need, me_need = ym in yms[-KEEP_GW:], True
        if not (gw_need or me_need):
            continue
        try:
            if gw_need:
                rows = _rows(idx[ym], key, {'cond[산지조합코드::GTE]': 305, 'cond[산지조합코드::LTE]': 312}, deadline)
                rec = {'coops': summarize(rows, True), 'gw': True, 'me': True, 'path': idx[ym]}
            else:
                rows = _rows(idx[ym], key, {'cond[산지조합코드::EQ]': ME}, deadline)
                rec = dict(rec, coops=dict(rec.get('coops') or {}, **summarize(rows, True)), me=True, path=idx[ym])
            months[ym] = rec
            log('위판 %s 받음 %d건' % (ym, len(rows)))
        except TimeoutError:
            errors[ym] = '시간 초과(다음 실행에서 이어서)'
            break
        except Exception as e:  # noqa: BLE001
            errors[ym] = str(e)[:200]
    for ym in list(months):
        if ym not in yms:
            del months[ym]
    # 동해 이외 수협은 최근 13개월만 어종 보관(용량)
    for ym, rec in months.items():
        if ym not in yms[-KEEP_GW:]:
            rec['coops'] = {k: v for k, v in (rec.get('coops') or {}).items() if k == str(ME)}
    out.update({'at': now().strftime('%Y-%m-%d'), 'ym': max(m for m in months) if months else None, 'months': months, 'errors': errors, 'me': str(ME)})
    if not months:
        raise RuntimeError('위판 자료를 하나도 받지 못함: %s' % errors)
    return out
