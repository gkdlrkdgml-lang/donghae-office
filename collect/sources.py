"""원천별 수집기. 각 함수는 성공하면 결과 dict, 실패하면 예외를 냅니다.

결과는 언제나 18개 시·군 이름({'동해': 값, ...})을 기준으로 맞춰 돌려줍니다.
"""
import json
import os
import urllib.parse

from common import (http_get, parse_body, find_items, check_error, pick, to_num,
                    match_region, read_manual, save_raw, ym_shift, now, log)


def _call(src, extra, raw_name):
    key = os.environ.get(src['key_env'], '').strip()
    if '%' in key:  # Encoding 키를 넣었어도 동작하도록 한 번 풀어 줍니다.
        key = urllib.parse.unquote(key)
    if not key:
        raise RuntimeError('%s 키가 없습니다(GitHub Secrets에 넣어 주세요)' % src['key_env'])
    if not src.get('url'):
        raise RuntimeError('요청 주소가 settings.json에 아직 없습니다')
    params = dict(src.get('params', {}))
    params.update(extra)
    params[src.get('key_param', 'serviceKey')] = key
    rows = []
    page = 1
    size = int(params.get('numOfRows', 100))
    while True:
        if 'numOfRows' in params:
            params['pageNo'] = str(page)
        text = http_get(src['url'], params)
        obj = parse_body(text)
        err = check_error(obj)
        if isinstance(obj, dict) and obj.get('err'):
            err = 'KOSIS 오류 %s %s' % (obj.get('err'), obj.get('errMsg', ''))
        if err:
            save_raw(raw_name + '_error', text)
            raise RuntimeError('API 오류 응답: %s' % err)
        items = find_items(obj)
        rows.extend(items)
        if page == 1:
            save_raw(raw_name, text)
        if 'numOfRows' not in params or len(items) < size or page >= 20:
            break
        page += 1
    return rows


# ---------------------------------------------------------------- 주민등록 인구(시·군)
def population_month(S, C, ym):
    src = S['sources']['population']
    rows = _call(src, {'stdgCd': C['sido']['stdg'], 'srchFrYm': ym, 'srchToYm': ym}, 'population_%s' % ym)
    f = src['fields']
    out = {}
    for r in rows:
        name = match_region(pick(r, f['sgg_name']), C['regions'])
        if not name:
            continue
        tot = to_num(pick(r, f['total']))
        if tot is None:
            continue
        # 같은 시·군이 여러 줄(읍면동)로 오면 더합니다.
        cur = out.setdefault(name, {'total': 0, 'hh': 0, 'male': 0, 'female': 0})
        cur['total'] += tot
        for k in ('hh', 'male', 'female'):
            v = to_num(pick(r, f[k]))
            if v is not None:
                cur[k] += v
    return out


def population(S, C):
    """가장 최근 공표 달과 그 1년 전 달의 시·군 인구를 가져옵니다."""
    today = now()
    base = '%04d%02d' % (today.year, today.month)
    last_err = None
    for back in (1, 2, 3):
        ym = ym_shift(base, -back)
        try:
            cur = population_month(S, C, ym)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
        if len(cur) >= 15:
            prev = population_month(S, C, ym_shift(ym, -12))
            try:
                prev_m = population_month(S, C, ym_shift(ym, -1))
            except Exception:  # noqa: BLE001
                prev_m = {}
            return {'ym': ym, 'prev_ym': ym_shift(ym, -12), 'prevm_ym': ym_shift(ym, -1), 'cur': cur, 'prev': prev, 'prev_m': prev_m}
        last_err = RuntimeError('%s 응답에서 시·군을 %d곳만 찾음' % (ym, len(cur)))
    raise last_err or RuntimeError('인구 자료 없음')


def dong_population(S, C, ym):
    src = S['sources']['dong_population']
    me = [r for r in C['regions'] if r['name'] == C['me']][0]
    rows = _call(src, {'stdgCd': me['stdg'], 'srchFrYm': ym, 'srchToYm': ym}, 'dong_%s' % ym)
    f = src['fields']
    out = {}
    for r in rows:
        name = pick(r, f['dong_name'])
        tot = to_num(pick(r, f['total']))
        if not name or tot is None:
            continue
        cur = out.setdefault(str(name), {'total': 0, 'hh': 0})
        cur['total'] += tot
        hh = to_num(pick(r, f['hh']))
        if hh is not None:
            cur['hh'] += hh
    return out


# ---------------------------------------------------------------- 성·연령별 인구 (정확한 값)
import re as _re

_RANGE = _re.compile(r'(\d+)\s*[-~]\s*(\d+)\s*세')
_OVER = _re.compile(r'(\d+)\s*(?:세\s*이상|세?\s*\+)')
_ONE = _re.compile(r'^(\d+)세(남자|여자)?$')


def _age_lower(label):
    """'15 - 19세' → (15, 19), '100세 이상' → (100, None), '계'·'합계' → None"""
    t = str(label)
    m = _RANGE.search(t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _OVER.search(t)
    if m:
        return int(m.group(1)), None
    return None


def _disjoint(groups):
    """'15~64세' 같은 묶음 칸이 5세 칸과 같이 오면 겹치므로, 좁은 칸부터 골라 겹치지 않게 만듭니다."""
    def width(g):
        return (g[1] if g[1] is not None else 999) - g[0]
    chosen = []
    for g in sorted(groups, key=width):
        hi = g[1] if g[1] is not None else 999
        if all(hi < c[0] or g[0] > (c[1] if c[1] is not None else 999) for c in chosen):
            chosen.append(g)
    return sorted(chosen)


def _ratios(groups):
    """groups: [(하한, 상한, 인원)] → 총인구, 15~64세, 65세 이상. 경계가 칸 사이에 정확히 걸릴 때만 계산합니다."""
    groups = _disjoint(groups)
    total = sum(g[2] for g in groups)
    working = elderly = 0.0
    for lo, hi, n in groups:
        top = hi if hi is not None else 200
        if lo >= 15 and top <= 64:
            working += n
        elif lo >= 65:
            elderly += n
        elif lo < 15 and top < 15:
            pass
        else:
            raise RuntimeError('연령 칸 %s~%s세가 15세·65세 경계에 걸쳐 있어 정확히 계산할 수 없습니다' % (lo, hi))
    if not total:
        raise RuntimeError('연령 인구 합계가 0')
    return total, working / total * 100, elderly / total * 100


def kosis_meta(src):
    """통계표의 분류·항목 코드 목록(getMeta type=ITM)."""
    key = os.environ.get(src['key_env'], '')
    if not key:
        raise RuntimeError('%s 키가 없습니다(GitHub Secrets에 넣어 주세요)' % src['key_env'])
    p = src['params']
    text = http_get(src['meta_url'], {'method': 'getMeta', 'type': 'ITM', 'orgId': p['orgId'], 'tblId': p['tblId'],
                                      'format': 'json', 'jsonVD': 'Y', 'apiKey': key})
    obj = parse_body(text)
    if isinstance(obj, dict) and obj.get('err'):
        raise RuntimeError('KOSIS 메타 오류 %s %s' % (obj.get('err'), obj.get('errMsg', '')))
    return obj if isinstance(obj, list) else find_items(obj)


def kosis_region_codes(meta, C, prefixes):
    """메타에서 강원 18개 시·군의 분류 코드와 그 분류의 objL 번호를 찾습니다."""
    by_obj = {}
    for m in meta:
        by_obj.setdefault(m.get('OBJ_ID'), []).append(m)
    for obj_id, items in by_obj.items():
        codes = {}
        for m in items:
            nm = str(m.get('ITM_NM', '')).strip()
            code = str(m.get('ITM_ID', ''))
            for r in C['regions']:
                if nm == r['full'] and (not prefixes or code.startswith(prefixes)):
                    codes[r['name']] = code
        if len(codes) >= 15:
            return obj_id, codes
    return None, {}


def age_kosis(S, C):
    src = S['sources']['age']['kosis']
    meta = kosis_meta(src)
    obj_id, codes = kosis_region_codes(meta, C, tuple(src.get('region_code_prefix', [])))
    if not codes:
        raise RuntimeError('KOSIS 메타에서 강원 시·군 코드를 찾지 못함')
    # 분류 순서(objL1, objL2 …)는 메타에 나온 OBJ_ID 순서를 따릅니다.
    order = []
    for m in meta:
        oid = m.get('OBJ_ID')
        if oid and oid != 'ITEM' and oid not in order:
            order.append(oid)
    extra = {}
    for i, oid in enumerate(order[:8]):
        extra['objL%d' % (i + 1)] = '+'.join(codes.values()) + '+' if oid == obj_id else 'ALL'
    # 항목은 '총인구' 하나만
    itm = [m for m in meta if m.get('OBJ_ID') == 'ITEM']
    tot = [m for m in itm if '총' in str(m.get('ITM_NM', '')) or str(m.get('ITM_NM', '')).strip() in ('계', '인구수')]
    if tot:
        extra['itmId'] = str(tot[0].get('ITM_ID')) + '+'
    rows = _call(src, extra, 'age_kosis')
    prefixes = tuple(src.get('region_code_prefix', []))
    # 총인구 항목만 씁니다(남·여 항목 제외).
    items = {}
    for r in rows:
        items.setdefault(r.get('ITM_ID'), r.get('ITM_NM', ''))
    pick_itm = None
    for k, v in items.items():
        if '총' in v or v.strip() in ('계', '인구수', '총인구수'):
            pick_itm = k
            break
    if pick_itm is None and items:
        pick_itm = list(items)[0]
    by = {}
    ym = None
    for r in rows:
        if r.get('ITM_ID') != pick_itm:
            continue
        code = str(r.get('C1', ''))
        if prefixes and not code.startswith(prefixes):
            continue
        name = match_region(r.get('C1_NM'), C['regions'])
        if not name:
            continue
        rng = _age_lower(r.get('C2_NM', ''))
        v = to_num(r.get('DT'))
        if rng is None or v is None:
            continue
        ym = r.get('PRD_DE') or ym
        by.setdefault(name, []).append((rng[0], rng[1], v))
    return by, ym


def admm_kosis(S, C):
    """우리 시 행정동별 인구와 고령인구 비율(KOSIS 같은 통계표, 5세 단위로 정확히 셈)."""
    src = S['sources']['age']['kosis']
    meta = kosis_meta(src)
    obj_id, rcodes = kosis_region_codes(meta, C, tuple(src.get('region_code_prefix', [])))
    mine = rcodes.get(C['me'])
    if not mine:
        raise RuntimeError('KOSIS 메타에서 우리 시 코드를 찾지 못함')
    kids = {str(m.get('ITM_ID')): str(m.get('ITM_NM', '')).strip() for m in meta
            if m.get('OBJ_ID') == obj_id and str(m.get('UP_ITM_ID', '')) == mine}
    if not kids:
        raise RuntimeError('KOSIS 메타에 행정동 코드가 없음')
    order = []
    for m in meta:
        oid = m.get('OBJ_ID')
        if oid and oid != 'ITEM' and oid not in order:
            order.append(oid)
    extra = {}
    for i, oid in enumerate(order[:8]):
        extra['objL%d' % (i + 1)] = '+'.join(kids) + '+' if oid == obj_id else 'ALL'
    itm = [m for m in meta if m.get('OBJ_ID') == 'ITEM' and ('총' in str(m.get('ITM_NM', '')) or str(m.get('ITM_NM', '')).strip() in ('계', '인구수'))]
    if itm:
        extra['itmId'] = str(itm[0].get('ITM_ID')) + '+'
    rows = _call(src, extra, 'admm_kosis')
    groups, ym = {}, None
    for r in rows:
        if itm and r.get('ITM_ID') != str(itm[0].get('ITM_ID')):
            continue
        name = kids.get(str(r.get('C1', '')))
        rng = _age_lower(r.get('C2_NM', ''))
        v = to_num(r.get('DT'))
        if not name or rng is None or v is None:
            continue
        ym = r.get('PRD_DE') or ym
        groups.setdefault(name, []).append((rng[0], rng[1], v))
    out = {}
    for name, g in groups.items():
        total, w, e = _ratios(g)
        out[name] = {'total': round(total), 'working_age': w, 'elderly': e}
    return out, ym


def age_mois(S, C):
    src = S['sources']['age']['mois']
    rows = _call(src, {}, 'age_mois')
    f = src['fields']
    by = {}
    for r in rows:
        sido = str(pick(r, f['sido_name']) or '')
        if sido and '강원' not in sido:
            continue
        name = match_region(pick(r, f['sgg_name']), C['regions'])
        if not name:
            continue
        acc = by.setdefault(name, {})
        for k, v in r.items():
            m = _ONE.match(str(k).replace(' ', ''))
            n = to_num(v)
            if n is None:
                continue
            if m:
                a = int(m.group(1))
            elif str(k).startswith('100세이상'):
                a = 100
            else:
                continue
            acc[a] = acc.get(a, 0) + n
    out = {}
    for name, acc in by.items():
        out[name] = [(a, a if a < 100 else None, n) for a, n in acc.items()]
    return out, None


def age(S, C, ym=None):
    """생산연령(15~64)·고령(65+) 비율. 정확한 연령 경계로만 계산하고, 추정은 하지 않습니다."""
    cfg = S['sources']['age']
    order = [cfg.get('mode', 'kosis')] + [m for m in ('kosis', 'mois') if m != cfg.get('mode', 'kosis')]
    errors = []
    for mode in order:
        try:
            by, basis = (age_kosis if mode == 'kosis' else age_mois)(S, C)
            if len(by) < 15:
                raise RuntimeError('시·군을 %d곳만 찾음' % len(by))
            res = {}
            for name, groups in by.items():
                total, w, e = _ratios(groups)
                bands = {}
                for lo, hi, n in _disjoint(groups):
                    b = str(min(lo // 10 * 10, 100))
                    bands[b] = bands.get(b, 0) + n
                res[name] = {'total': total, 'working_age': w, 'elderly': e, 'bands': bands}
            return res, basis, mode
        except Exception as e:  # noqa: BLE001
            errors.append('%s: %s' % (mode, e))
    raise RuntimeError(' / '.join(errors))


# ---------------------------------------------------------------- 재정자립도 (당초·최종)
def finance_years(S, C, key='finance'):
    """{연도: {시군: 값}} 전체를 돌려줍니다."""
    src = S['sources'][key]
    if not src.get('url'):
        raise RuntimeError('%s 요청 주소가 settings.json에 아직 없습니다' % key)
    code = src['url'].rstrip('/').rsplit('/', 1)[-1]
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'manual', 'lofin_%s.json' % code)
    rows = None
    try:
        rows = _call(src, {}, key)
    except Exception as e:  # noqa: BLE001
        if not os.path.exists(path):
            raise
        log('%s API 접속 불가(%s) → 저장 파일 %s 사용' % (key, e, os.path.basename(path)))
    if not rows and os.path.exists(path):
        with open(path, encoding='utf-8') as fp:
            rows = find_items(json.load(fp))
    f = src['fields']
    by = {}
    for r in rows or []:
        sido = pick(r, f.get('sido_name', []))
        if sido and '강원' not in str(sido):
            continue
        name = match_region(pick(r, f['region_name']), C['regions'])
        v = to_num(pick(r, f['fin_indep']))
        y = pick(r, f['year'])
        if name and v is not None and y:
            by.setdefault(str(y)[:4], {})[name] = v
    by = {y: d for y, d in by.items() if len(d) >= 15}
    if not by:
        raise RuntimeError('%s 응답에서 강원 시·군 값을 찾지 못함' % key)
    return by


def finance(S, C):
    """순위용: 가장 최근 연도의 당초 재정자립도. API가 안 되면 manual/fin_indep.csv."""
    manual, basis = read_manual('fin_indep')
    try:
        by = finance_years(S, C, 'finance')
        y = max(by)
        return {'values': by[y], 'basis': '%s년 당초예산' % y, 'from': 'api', 'by_year': by}
    except Exception as e:  # noqa: BLE001
        if manual:
            log('재정 API 대신 수기 입력값을 씁니다(%s)' % e)
            return {'values': manual, 'basis': basis or '수기 입력', 'from': 'manual', 'by_year': {}}
        raise
