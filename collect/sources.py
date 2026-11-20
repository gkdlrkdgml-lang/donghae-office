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
    extra = {'newEstPrdCnt': '2'}
    kids_all = dict(kids)
    kids_all[mine] = '__city__'
    for i, oid in enumerate(order[:8]):
        extra['objL%d' % (i + 1)] = '+'.join(kids_all) + '+' if oid == obj_id else 'ALL'
    itm = [m for m in meta if m.get('OBJ_ID') == 'ITEM' and ('총' in str(m.get('ITM_NM', '')) or str(m.get('ITM_NM', '')).strip() in ('계', '인구수'))]
    if itm:
        extra['itmId'] = str(itm[0].get('ITM_ID')) + '+'
    rows = _call(src, extra, 'admm_kosis')
    groups, periods = {}, set()
    for r in rows:
        if itm and r.get('ITM_ID') != str(itm[0].get('ITM_ID')):
            continue
        name = kids_all.get(str(r.get('C1', '')))
        rng = _age_lower(r.get('C2_NM', ''))
        v = to_num(r.get('DT'))
        pd = r.get('PRD_DE')
        if not name or rng is None or v is None or not pd:
            continue
        periods.add(pd)
        groups.setdefault((pd, name), []).append((rng[0], rng[1], v))
    if not periods:
        raise RuntimeError('KOSIS 행정동 응답이 비었음')
    ym = max(periods)
    pv = max([p for p in periods if p != ym] or [None]) if len(periods) > 1 else None
    out, city = {}, {}
    for (pd, name), g in groups.items():
        total, w, e = _ratios(g)
        if name == '__city__':
            city[pd] = {'total': round(total), 'g': g}
            continue
        if pd == ym:
            out.setdefault(name, {}).update({'total': round(total), 'working_age': w, 'elderly': e})
        elif pd == pv:
            out.setdefault(name, {})['prev_total'] = round(total)
    out = {k: v for k, v in out.items() if 'total' in v}

    def cnt(g, lo, hi):  # lo~hi세 인구(5세 칸이 경계에 걸치면 None)
        t = 0
        for a, b, v in g:
            if b is None:
                b = 999
            if a >= lo and b <= hi:
                t += v
            elif a <= hi and b >= lo:
                return None
        return round(t)
    cm = {}
    for pd, c in city.items():
        cm[pd] = {'elderly': cnt(c['g'], 65, 999), 'youth20_34': cnt(c['g'], 20, 34)}
    return out, ym, {'ym': ym, 'prev_ym': pv, 'cur': cm.get(ym), 'prev': cm.get(pv)}


def _kosis_rows(tbl, extra, raw):
    src = {'key_env': 'KOSIS_KEY', 'key_param': 'apiKey', 'url': 'https://kosis.kr/openapi/Param/statisticsParameterData.do',
           'params': {'method': 'getList', 'format': 'json', 'jsonVD': 'Y', 'orgId': '101', 'tblId': tbl, 'prdSe': 'M'}}
    return _call(src, extra, raw)


def migration(S, C, code='51170'):
    """KOSIS 국내인구이동: 우리 시 총전입·총전출·순이동(최근 2개월)과 어디서 와서 어디로 갔는지(최근 1개월)."""
    rows = _kosis_rows('DT_1B26001_A01', {'objL1': code + '+', 'itmId': 'T10+T20+T25+', 'newEstPrdCnt': '2'}, 'migration_total')
    tot = {}
    for r in rows:
        tot.setdefault(r.get('PRD_DE'), {})[{'T10': 'in', 'T20': 'out', 'T25': 'net'}.get(r.get('ITM_ID'))] = to_num(r.get('DT'))
    if not tot:
        raise RuntimeError('이동자수 응답이 비었음')
    ym = max(tot)
    pv = max([p for p in tot if p != ym] or [None])

    def od(direction, pd):
        if direction == 'in':   # 어디서 왔나: 전출지 ALL → 전입지 우리 시
            ex = {'objL1': 'ALL', 'objL2': code + '+', 'objL3': '0+', 'itmId': 'T70+', 'startPrdDe': pd, 'endPrdDe': pd}
            key = 'C1'
        else:                   # 어디로 갔나: 전출지 우리 시 → 전입지 ALL
            ex = {'objL1': code + '+', 'objL2': 'ALL', 'objL3': '0+', 'itmId': 'T70+', 'startPrdDe': pd, 'endPrdDe': pd}
            key = 'C2'
        rr = _kosis_rows('DT_1B26003_A02', ex, 'migration_od_%s_%s' % (direction, pd))
        sido_nm = {str(r.get(key)): str(r.get(key + '_NM', '')).strip() for r in rr if len(str(r.get(key, ''))) == 2}
        sgg, sido = [], {}
        for r in rr:
            c = str(r.get(key, '')); nm = str(r.get(key + '_NM', '')).strip(); v = to_num(r.get('DT'))
            if not v or len(c) != 5 or c == code or c.endswith('000'):
                continue  # 시·군·구만, 우리 시 안 이동은 뺍니다
            sn = sido_nm.get(c[:2], c[:2])
            sgg.append([nm, v, c, sn])
            sido[sn] = sido.get(sn, 0) + v
        return sorted(sgg, key=lambda x: -x[1]), sorted([[k, v] for k, v in sido.items()], key=lambda x: -x[1])
    res = {'ym': ym, 'prev_ym': pv, 'total_cur': tot.get(ym), 'total_prev': tot.get(pv)}
    res['from_sgg'], res['from_sido'] = od('in', ym)
    res['to_sgg'], res['to_sido'] = od('out', ym)
    res['in'] = sum(x[1] for x in res['from_sgg']); res['out'] = sum(x[1] for x in res['to_sgg'])
    if pv:
        try:
            pi, _ = od('in', pv); po, _ = od('out', pv)
            res['prev_in'] = sum(x[1] for x in pi); res['prev_out'] = sum(x[1] for x in po)
        except Exception:  # noqa: BLE001
            pass
    # 시내(동 사이) 이동 = 총전입 - 관외 전입
    if tot.get(ym, {}).get('in') is not None:
        res['inner'] = tot[ym]['in'] - res['in']
    return res


MOIS_MONTHLY = {
    'birth': 'https://apis.data.go.kr/1741000/admmSexdBrthReg/selectAdmmSexdBrthReg',
    'death': 'https://apis.data.go.kr/1741000/admmSexdAgeErsr/selectAdmmSexdAgeErsr',
    'hsmb': 'https://apis.data.go.kr/1741000/admmHsmbHh/selectAdmmHsmbHh',
}


def mois_monthly(S, C, kind, ym, lv):
    """행안부 행정동별 월간 자료(출생·사망·세대원수별 세대). lv=2 시·군 18개, lv=3 우리 시 행정동."""
    src = {'url': MOIS_MONTHLY[kind], 'key_env': 'DATA_GO_KR_KEY',
           'params': {'type': 'JSON', 'numOfRows': '100', 'pageNo': '1', 'lv': lv, 'regSeCd': '1'}}
    me = [r for r in C['regions'] if r['name'] == C['me']][0]
    rows = _call(src, {'admmCd': me['stdg'], 'srchFrYm': ym, 'srchToYm': ym}, '%s_%s_lv%s' % (kind, ym, lv))
    out = {}
    for r in rows:
        key = str(r.get('dongNm') or '').strip() if lv == '3' else match_region(r.get('sggNm'), C['regions'])
        if not key:
            continue
        if kind == 'hsmb':
            out[key] = {'one': to_num(r.get('hhNmprCnt1')), 'two': to_num(r.get('hhNmprCnt2')), 'total': to_num(r.get('totHhCnt'))}
        else:
            out[key] = {'total': to_num(r.get('totNmprCnt')), 'male': to_num(r.get('maleNmprCnt')), 'female': to_num(r.get('femlNmprCnt'))}
    return out


def vital(S, C, ym):
    """출생·사망·1인세대: 이번 달과 지난달(시·군 18개), 이번 달 행정동별."""
    pv = ym_shift(ym, -1)
    res = {'ym': ym, 'prev_ym': pv}
    for kind in ('birth', 'death', 'hsmb'):
        cur = mois_monthly(S, C, kind, ym, '2')
        if len(cur) < 15:  # 이번 달이 아직 안 나왔으면 한 달 앞으로
            raise RuntimeError('%s %s 자료 부족(%d)' % (kind, ym, len(cur)))
        res[kind] = {'cur': cur, 'prev': mois_monthly(S, C, kind, pv, '2'), 'dong': mois_monthly(S, C, kind, ym, '3')}
    return res


def youth_elderly(S, C):
    """KOSIS 1세별 주민등록인구(DT_1B04006): 우리 시 청년(19~34세)·고령(65세+) 정확한 인원, 최근 2개월."""
    src = {'key_env': 'KOSIS_KEY', 'meta_url': 'https://kosis.kr/openapi/statisticsData.do', 'params': {'orgId': '101', 'tblId': 'DT_1B04006'}}
    meta = kosis_meta(src)
    full = [r['full'] for r in C['regions'] if r['name'] == C['me']][0]
    reg = [m for m in meta if str(m.get('ITM_NM', '')).strip() == full and str(m.get('ITM_ID', ''))[:2] in ('51', '32', '42')]
    if not reg:
        raise RuntimeError('1세별 표에서 %s 코드를 찾지 못함' % full)
    robj, rcode = reg[0]['OBJ_ID'], str(reg[0]['ITM_ID'])
    order = []
    for m in meta:
        if m.get('OBJ_ID') and m['OBJ_ID'] != 'ITEM' and m['OBJ_ID'] not in order:
            order.append(m['OBJ_ID'])
    extra = {'newEstPrdCnt': '2'}
    for i, oid in enumerate(order[:8]):
        extra['objL%d' % (i + 1)] = rcode + '+' if oid == robj else 'ALL'
    itm = [m for m in meta if m.get('OBJ_ID') == 'ITEM' and '총' in str(m.get('ITM_NM', ''))]
    if itm:
        extra['itmId'] = str(itm[0]['ITM_ID']) + '+'
    rows = _kosis_rows('DT_1B04006', extra, 'age_1y')
    by = {}
    for r in rows:
        if itm and r.get('ITM_ID') != str(itm[0]['ITM_ID']):
            continue
        lab = ''
        for k in ('C2_NM', 'C3_NM', 'C4_NM'):
            if _re.search(r'\d+\s*세', str(r.get(k, ''))):
                lab = str(r.get(k)).strip()
                break
        m1 = _re.match(r'^(\d+)\s*세$', lab)
        m2 = _OVER.search(lab)
        v = to_num(r.get('DT'))
        if v is None or not (m1 or m2):
            continue  # 1세 칸과 'N세 이상'만(합계·묶음 제외)
        by.setdefault(r.get('PRD_DE'), {})[int((m1 or m2).group(1))] = v
    if not by:
        raise RuntimeError('1세별 응답이 비었음')
    out = {}
    for pd, ages in by.items():
        out[pd] = {'youth': round(sum(v for k, v in ages.items() if 19 <= k <= 34)),
                   'elderly': round(sum(v for k, v in ages.items() if k >= 65)), 'total': round(sum(ages.values()))}
    ym = max(out)
    pv = max([p for p in out if p != ym] or [None])
    return {'ym': ym, 'prev_ym': pv, 'cur': out[ym], 'prev': out.get(pv)}


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
AMOUNTS = {}  # 예산 규모·자체수입(원): {'finance'|'finance_final': {연도: {시군: {...}}}}


def finance_years(S, C, key='finance'):
    """{연도: {시군: 값}} 전체를 돌려줍니다."""
    src = S['sources'][key]
    if not src.get('url'):
        raise RuntimeError('%s 요청 주소가 settings.json에 아직 없습니다' % key)
    code = src['url'].rstrip('/').rsplit('/', 1)[-1]
    mdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'manual')
    files = sorted(fn for fn in (os.listdir(mdir) if os.path.isdir(mdir) else [])
                   if fn.startswith('lofin_%s' % code) and fn.endswith('.json'))
    rows = None
    try:
        rows = _call(src, {}, key)
    except Exception as e:  # noqa: BLE001
        if not files:
            raise
        log('%s API 접속 불가(%s) → 저장 파일 %s 사용' % (key, e, ', '.join(files)))
    if not rows and files:
        rows = []
        for fn in files:
            with open(os.path.join(mdir, fn), encoding='utf-8') as fp:
                rows += find_items(json.load(fp))
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
            bud, own = to_num(r.get('pfa_amt2')), to_num(r.get('pfa_amt3'))
            if bud:
                AMOUNTS.setdefault(key, {}).setdefault(str(y)[:4], {})[name] = {'budget': bud, 'own': own}
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


# ---------------------------------------------------------------- 자동차 등록(국토교통부, KOSIS 116/DT_MLTM_5498, 월)
CAR_TBL, CAR_GW = 'DT_MLTM_5498', '13102873443A.0011'
CAR_KIND = {'승용': 'passenger', '승합': 'van', '화물': 'truck', '특수': 'special', '총계': 'total'}
CAR_USE = {'T1': 'gov', 'T2': 'own', 'T3': 'biz', 'T4': 'all'}


def vehicles(S, C):
    """강원 시·군 자동차 등록대수: 최근 13개월(차종×용도) + 동해 37개월 총계 추이."""
    base = {'orgId': '116', 'objL1': CAR_GW + '+', 'objL2': 'ALL', 'objL3': 'ALL', 'itmId': 'ALL'}
    rows = _kosis_rows(CAR_TBL, dict(base, newEstPrdCnt='2'), 'cars')
    last = max((str(r.get('PRD_DE')) for r in rows), default=None)
    if last:
        ya = ym_shift(last, -12)
        try:
            rows += _kosis_rows(CAR_TBL, dict(base, startPrdDe=ya, endPrdDe=ya), 'cars_year')
        except Exception as e:  # noqa: BLE001
            log('자동차 1년 전 실패: %s' % e)
    by = {}
    me_code = None
    for r in rows:
        name = match_region(str(r.get('C2_NM', '')).strip(), C['regions'])
        kind = CAR_KIND.get(str(r.get('C3_NM', '')).strip())
        use = CAR_USE.get(str(r.get('ITM_ID', ''))[-2:])
        v = to_num(r.get('DT'))
        if not name or not kind or not use or v is None:
            continue
        if name == C['me']:
            me_code = r.get('C2')
        ym = str(r.get('PRD_DE'))
        by.setdefault(ym, {}).setdefault(name, {}).setdefault(kind, {})[use] = v
    if not by:
        raise RuntimeError('자동차 등록 응답에서 강원 시·군을 찾지 못함')
    yms = sorted(by)
    ym = yms[-1]
    if len(by[ym]) < 15:
        raise RuntimeError('자동차 등록 %s: 시·군 %d곳만 있음' % (ym, len(by[ym])))
    pm, ya = ym_shift(ym, -1), ym_shift(ym, -12)
    res = {'ym': ym, 'prev_ym': pm, 'year_ym': ya, 'regions': by[ym],
           'prev': {k: v.get('total', {}).get('all') for k, v in by.get(pm, {}).items()},
           'year': {k: v.get('total', {}).get('all') for k, v in by.get(ya, {}).items()}}
    if me_code:
        try:
            tr = _kosis_rows(CAR_TBL, {'orgId': '116', 'objL1': CAR_GW + '+', 'objL2': me_code + '+', 'objL3': 'ALL', 'itmId': '13103873443T4+', 'newEstPrdCnt': '37'}, 'cars_trend')
            t = {}
            for r in tr:
                kind = CAR_KIND.get(str(r.get('C3_NM', '')).strip())
                if kind:
                    t.setdefault(str(r.get('PRD_DE')), {})[kind] = to_num(r.get('DT'))
            res['trend'] = [[k, t[k]] for k in sorted(t)]
        except Exception as e:  # noqa: BLE001
            log('자동차 추이 실패: %s' % e)
    return res


# ---------------------------------------------------------------- 교통안전(KOSIS): 교통사고·교통단속·도로·운수업체
SIDO_NAMES = ('서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충청', '충북', '충남', '전라', '전북', '전남', '경상', '경북', '경남', '제주')


def _gw_rows(rows, name_key, code_key):
    """시·도 머리행 다음에 오는 시·군 행 가운데 강원 것만 고릅니다(고성군처럼 이름이 겹치는 경우 대비)."""
    out, in_gw = [], False
    for r in sorted(rows, key=lambda x: str(x.get(code_key))):
        nm = str(r.get(name_key, '')).strip()
        if nm.startswith(SIDO_NAMES) and (nm.endswith('도') or nm.endswith('시') and ('특별' in nm or '광역' in nm)):
            in_gw = nm.startswith('강원')
            continue
        if in_gw:
            out.append(r)
    return out


def traffic_safety(S, C):
    res = {}
    # 1) 교통사고(행안부, 시군구, 연)
    try:
        rows = _kosis_rows('DT_110001_A046', {'orgId': '110', 'objL1': 'ALL', 'objL2': 'ALL', 'itmId': 'ALL', 'newEstPrdCnt': '1'}, 'acc')
        acc = {}
        for r in _gw_rows(rows, 'C1_NM', 'C1'):
            name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
            if name:
                acc.setdefault(name, {})[str(r.get('C2'))] = to_num(r.get('DT'))
        if len(acc) >= 15:
            res['acc'] = {'year': str(rows[0].get('PRD_DE')), 'regions': acc}
        else:
            log('교통사고: 강원 %d곳만 찾음' % len(acc))
    except Exception as e:  # noqa: BLE001
        log('교통사고 실패: %s' % e)
    # 2) 교통단속 위반(강원 경찰서별, 연)
    try:
        rows = _kosis_rows('DT_211002_P029', {'orgId': '211', 'objL1': 'ALL', 'objL2': 'ALL', 'itmId': 'ALL', 'newEstPrdCnt': '1'}, 'enf')
        enf = {}
        for r in rows:
            st = str(r.get('C1_NM', '')).replace('경찰서', '').strip()
            name = match_region(st, C['regions'])
            v = to_num(r.get('DT'))
            if name and v is not None:
                enf.setdefault(name, {})[str(r.get('C2_NM', '')).strip()] = v
        if enf:
            res['enf'] = {'year': str(rows[0].get('PRD_DE')), 'regions': enf}
    except Exception as e:  # noqa: BLE001
        log('교통단속 실패: %s' % e)
    # 3) 도로(강원 시군, 연): 도로종류 × 시군 × 항목
    try:
        rows = _kosis_rows('DT_211002_I011', {'orgId': '211', 'objL1': 'ALL', 'objL2': 'ALL', 'objL3': 'ALL', 'itmId': 'T001', 'newEstPrdCnt': '1'}, 'road')
        road = {}
        for r in rows:
            a, b = str(r.get('C1_NM', '')).strip(), str(r.get('C2_NM', '')).strip()
            reg, kind = (a, b) if match_region(a, C['regions']) else (b, a)
            name = match_region(reg, C['regions'])
            if not name or reg.endswith('군') and name in ('춘천', '원주', '삼척'):  # 옛 춘천군·원주군·삼척군 제외
                continue
            v = to_num(r.get('DT'))
            if v is not None:
                road.setdefault(name, {}).setdefault(kind, {})[str(r.get('C3_NM') or r.get('ITM_NM', '')).strip()] = v
        if road:
            res['road'] = {'year': str(rows[0].get('PRD_DE')), 'regions': road}
    except Exception as e:  # noqa: BLE001
        log('도로 실패: %s' % e)
    # 4) 운수업 사업체수(통계청, 시군구, 연)
    try:
        rows = _kosis_rows('DT_1YL5902', {'orgId': '101', 'objL1': 'ALL', 'itmId': 'T10', 'newEstPrdCnt': '1'}, 'transport_biz')
        gw = [r for r in rows if str(r.get('C1', '')).startswith(('32', '51')) and len(str(r.get('C1', ''))) == 5]
        biz = {}
        for r in gw:
            name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
            if name:
                biz[name] = to_num(r.get('DT'))
        if len(biz) >= 15:
            res['biz'] = {'year': str(rows[0].get('PRD_DE')), 'regions': biz}
        else:
            log('운수업: 강원 %d곳만 찾음' % len(biz))
    except Exception as e:  # noqa: BLE001
        log('운수업 실패: %s' % e)
    if not res:
        raise RuntimeError('교통안전 통계를 하나도 받지 못함')
    return res


ECO_TBL = {'active': ('DT_133N_A9811', '15133JYB0A'), 'new': ('DT_133001N_9822', 'A04'), 'closed': ('DT_133001N_9816', 'A04')}
ECO_KIND = {'총계': 'total', '법인': 'corp', '개인사업자': 'indiv', '일반사업자': 'general', '간이사업자': 'simple', '면세사업자': 'exempt'}


def economy(S, C, years=5):
    """국세청(KOSIS) 시·군·구 가동·신규·폐업 사업자(연): 강원 18개 시·군, 최근 years년."""
    res = {}
    for key, (tbl, gw) in ECO_TBL.items():
        rows = _kosis_rows(tbl, {'orgId': '133', 'prdSe': 'Y', 'objL1': 'ALL', 'objL2': 'ALL', 'itmId': 'ALL', 'newEstPrdCnt': str(years)}, 'eco_' + key)
        by = {}
        for r in rows:
            code = str(r.get('C1', ''))
            if not code.startswith(gw) or code == gw:
                continue
            name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
            kind = ECO_KIND.get(str(r.get('C2_NM', '')).strip())
            v = to_num(r.get('DT'))
            if name and kind and v is not None:
                by.setdefault(str(r.get('PRD_DE')), {}).setdefault(name, {})[kind] = v
        if not by:
            raise RuntimeError('%s: 강원 시·군 자료 없음' % tbl)
        res[key] = by
    yrs = sorted(set(res['active']) & set(res['new']) & set(res['closed']))
    return {'at': now().strftime('%Y-%m-%d'), 'years': yrs, 'year': yrs[-1] if yrs else None, 'active': res['active'], 'new': res['new'], 'closed': res['closed']}


def _gw5(rows, key='C1'):
    """시군구 코드 5자리(32xxx)인 강원 행만."""
    return [r for r in rows if str(r.get(key, '')).startswith('32') and len(str(r.get(key, ''))) == 5]


def economy_industry(S, C):
    """통계청 기업생멸행정통계: 강원 시·군 산업대분류별 활동·신생·소멸 기업 수(최근 2년)."""
    rows = _kosis_rows('DT_6BD1132', {'orgId': '101', 'prdSe': 'Y', 'objL1': 'ALL', 'objL2': 'ALL', 'itmId': 'T01+T02+T03+', 'newEstPrdCnt': '1'}, 'eco_ind')
    last = max((str(r.get('PRD_DE')) for r in rows), default=None)
    if last:
        try:
            p = str(int(last) - 1)
            rows += _kosis_rows('DT_6BD1132', {'orgId': '101', 'prdSe': 'Y', 'objL1': 'ALL', 'objL2': 'ALL', 'itmId': 'T01+T02+T03+', 'startPrdDe': p, 'endPrdDe': p}, 'eco_ind_prev')
        except Exception as e:  # noqa: BLE001
            log('업종 전년 실패: %s' % e)
    by = {}
    K = {'T01': 'active', 'T02': 'born', 'T03': 'died'}
    for r in _gw5(rows):
        name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
        ind_ = str(r.get('C2_NM', '')).strip()
        v = to_num(r.get('DT'))
        k = K.get(str(r.get('ITM_ID')))
        if name and k and v is not None:
            by.setdefault(str(r.get('PRD_DE')), {}).setdefault(name, {}).setdefault(ind_, {})[k] = v
    if not by:
        raise RuntimeError('업종별 기업 자료 없음')
    return {'at': now().strftime('%Y-%m-%d'), 'year': max(by), 'years': sorted(by), 'data': by}


def social(S, C):
    """복지: 사회복지시설(행안부), 기초수급자·등록장애인 비율(행안부), 등록장애인 정도·성별(복지부), 노인여가복지시설(통계청)."""
    res = {'at': now().strftime('%Y-%m-%d')}
    # 1) 사회복지시설 수·생활인원
    rows = _kosis_rows('DT_110001_A043', {'orgId': '110', 'prdSe': 'Y', 'objL1': 'ALL', 'objL2': 'ALL', 'itmId': 'ALL', 'newEstPrdCnt': '1'}, 'soc_fac')
    F = {}
    cur = None
    for r in _gw_rows(rows, 'C1_NM', 'C1'):
        name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
        v = to_num(r.get('DT'))
        if name and v is not None:
            F.setdefault(name, {})[str(r.get('C2'))] = v
            res['fac_year'] = str(r.get('PRD_DE'))
    FK = {'B002': 'total', 'B003': 'residents', 'B005': '아동', 'B008': '노인', 'B011': '장애인', 'B014': '한부모가족', 'B017': '정신요양', 'B020': '노숙인',
          'B006': '아동_인원', 'B009': '노인_인원', 'B012': '장애인_인원', 'B015': '한부모가족_인원', 'B018': '정신요양_인원', 'B021': '노숙인_인원'}
    res['facilities'] = {n: {FK[k]: v for k, v in d.items() if k in FK} for n, d in F.items()}
    # 2) 기초생활보장 수급자·등록장애인 수·비율
    rows = _kosis_rows('DT_110001_A045', {'orgId': '110', 'prdSe': 'Y', 'objL1': 'ALL', 'objL2': 'ALL', 'itmId': 'ALL', 'newEstPrdCnt': '1'}, 'soc_rcp')
    RK = {'H002': 'recipients', 'H003': 'recipients_rate', 'H005': 'disabled', 'H006': 'disabled_rate', 'H007': 'pop'}
    R = {}
    for r in _gw_rows(rows, 'C1_NM', 'C1'):
        name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
        k = RK.get(str(r.get('C2')))
        v = to_num(r.get('DT'))
        if name and k and v is not None:
            R.setdefault(name, {})[k] = v
            res['rcp_year'] = str(r.get('PRD_DE'))
    res['recipients'] = R
    # 3) 등록장애인 장애정도·성별(복지부, 더 최신)
    try:
        rows = _kosis_rows('DT_11761_N009', {'orgId': '117', 'prdSe': 'Y', 'objL1': 'ALL', 'objL2': 'ALL', 'objL3': 'ALL', 'itmId': 'ALL', 'newEstPrdCnt': '1'}, 'soc_dis')
        Dd = {}
        for r in _gw5(rows):
            name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
            v = to_num(r.get('DT'))
            if name and v is not None:
                Dd.setdefault(name, {})['%s_%s' % (r.get('C2'), r.get('C3'))] = v
                res['dis_year'] = str(r.get('PRD_DE'))
        res['disabled'] = {n: {'total': d.get('TT_T001'), 'severe': d.get('01_T001'), 'mild': d.get('02_T001'), 'male': d.get('TT_T002'), 'female': d.get('TT_T003')} for n, d in Dd.items()}
    except Exception as e:  # noqa: BLE001
        log('등록장애인 실패: %s' % e)
    # 4) 노인여가복지시설
    try:
        rows = _kosis_rows('DT_1YL20961', {'orgId': '101', 'prdSe': 'Y', 'objL1': 'ALL', 'itmId': 'ALL', 'newEstPrdCnt': '1'}, 'soc_old')
        O = {}
        for r in _gw5(rows):
            name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
            v = to_num(r.get('DT'))
            k = {'T10': 'per1000', 'T001': 'facilities', 'T002': 'pop60'}.get(str(r.get('ITM_ID')))
            if name and k and v is not None:
                O.setdefault(name, {})[k] = v
                res['old_year'] = str(r.get('PRD_DE'))
        res['elderly'] = O
    except Exception as e:  # noqa: BLE001
        log('노인여가복지시설 실패: %s' % e)
    # 5) 장기요양기관(건강보험공단): 계·재가·노인의료복지시설, 기관수·정원
    try:
        rows = _kosis_rows('DT_35006_N021', {'orgId': '350', 'prdSe': 'Y', 'objL1': 'ALL', 'objL2': '001+002+003+', 'itmId': '002+003+', 'newEstPrdCnt': '1'}, 'soc_ltc')
        LT = {}
        for r in rows:
            code = str(r.get('C1', ''))
            if not code.startswith('15350AC400I1') or code == '15350AC400I1':
                continue
            name = match_region(str(r.get('C1_NM', '')).strip(), C['regions'])
            v = to_num(r.get('DT'))
            if name and v is not None:
                k = {'001': 'all', '002': 'home', '003': 'facility'}.get(str(r.get('C2')), str(r.get('C2')))
                LT.setdefault(name, {})[k + ('_n' if str(r.get('ITM_ID')) == '002' else '_cap')] = v
                res['ltc_year'] = str(r.get('PRD_DE'))
        res['ltc'] = LT
    except Exception as e:  # noqa: BLE001
        log('장기요양기관 실패: %s' % e)
    if not res['facilities'] and not R:
        raise RuntimeError('복지 자료 없음')
    return res


def employment(S, C):
    """지역별고용조사(반기): 강원 시·군 취업자·고용률(전체, 15~64세, 15~29세), 최근 4개 반기."""
    rows = _kosis_rows('DT_1ES3A03_A01S', {'orgId': '101', 'prdSe': 'H', 'objL1': 'ALL', 'objL2': '000+060+010+', 'itmId': 'T00+T12+', 'newEstPrdCnt': '4'}, 'emp')
    by = {}
    AG = {'000': 'all', '060': '1564', '010': '1529'}
    for r in rows:
        code = str(r.get('C1', ''))
        if not (code.startswith('32') and len(code) == 4):
            continue
        name = match_region(str(r.get('C1_NM', '')).strip().split()[-1], C['regions'])
        ag = AG.get(str(r.get('C2')))
        v = to_num(r.get('DT'))
        if not name or not ag or v is None:
            continue
        k = ('emp_' if str(r.get('ITM_ID')) == 'T00' else 'rate_') + ag
        by.setdefault(str(r.get('PRD_DE')), {}).setdefault(name, {})[k] = v
    if not by:
        raise RuntimeError('고용 자료 없음')
    ps = sorted(by)
    return {'at': now().strftime('%Y-%m-%d'), 'period': ps[-1], 'periods': ps, 'data': by}


BOKJIRO = 'https://www.bokjiro.go.kr/ssis-tbu/twatga/sociGuaStat/'
BJ_SETS = {  # 키: (datsNo, datsClNo, datTbl, 분류열, 값열)
    'disabled': (22, 1004, 'TIP_DPWL_DSRT_DSTP_DSPSN_STN', 'DSDGR_NM', 'REG_DSPSN_NT'),
    'basic': (1, 1001, 'TIP_NBLG_PNR_STN', 'PNR_DNM', 'PNR_NT'),
    'basic_hh': (1, 1001, 'TIP_NBLG_PNR_STN', 'PNR_DNM', 'SFML_NT'),
    'pension': (56, 1007, 'TIP_BSPN_TRGT_SPDM_STN', 'SEX_NM', 'PNR_NT'),
    'facility': (62, 1008, 'TIP_WLFCL_TYP_DIV_FACL_STN', 'WLFCL_TNM', 'WLFCL_NT'),
    'single': (16, 1003, 'TIP_OPRN_FAM_FAM_TYP_SPDM_STN', 'OPRN_FAM_TNM', 'PNR_NT'),
    'medaid': (59, 1002, 'TIP_MDSL_CLSF_PNR_STN', 'MDSL_CLSF_NM', 'PNR_NT'),
}


def _bj_post(path, body, ref):
    import urllib.request as _ur
    import time as _t
    last = None
    for i in range(3):
        try:
            rq = _ur.Request(BOKJIRO + path, data=urllib.parse.urlencode(body).encode(), headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'User-Agent': 'Mozilla/5.0', 'Referer': ref})
            with _ur.urlopen(rq, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001
            last = e
            _t.sleep(2 + i * 3)
    raise RuntimeError('복지로 호출 실패 %s: %s' % (path, last))


def _bj_query(key, ym, sgg):
    n, cl, tbl, dim, mea = BJ_SETS[key]
    ref = BOKJIRO + 'SociGuaStatDetailIframe.do?datsNo=%d&datsClNo=%d&datsClCrit=WS' % (n, cl)
    body = {'datsClCrit': 'WS', 'datsClNo': cl, 'datsNo': n, 'datTbl': tbl, 'radioType': '1', 'statYm': ym, 'statYy': ym[:4], 'statMm': ym[4:],
            'selbox': '해당월', 'statCtprvCd': '51', 'statSggCd': sgg, 'meaCol': mea, 'chartType': 'bar', 'spdmRtYN': 'N',
            'dimCols': '%s AS DIMCOL0' % dim, 'grpCol0': dim, 'DIMCOL0': dim, 'ordCol0': dim + '_ORD0'}
    d = _bj_post('selectChartData.do', body, ref)
    if not isinstance(d, dict) or 'chartData' not in d:
        raise RuntimeError('복지로 %s 응답 오류: %s' % (key, str(d)[:200]))
    return {str(r.get('DIMCOL0', '')).strip(): to_num(r.get('meaCol')) for r in d['chartData']}


def bokjiro(C):
    """복지로 복지통계(사회보장정보시스템 행복이음, 월별): 강원 18개 시·군 최신 월 + 동해 전년 같은 달."""
    n, cl, tbl, _, _ = BJ_SETS['disabled']
    yms = _bj_post('selectParamStatYm.do', {'datsClCrit': 'WS', 'datsClNo': cl, 'datsNo': n, 'datTbl': tbl},
                   BOKJIRO + 'SociGuaStatDetailIframe.do?datsNo=22&datsClNo=1041&datsClCrit=WS')
    ym = str(((yms or {}).get('paramStatYm') or [{}])[0].get('statYm') or '')
    if len(ym) != 6:
        raise RuntimeError('복지로 최신 연월을 찾지 못함')
    out, errs = {}, []
    import time as _t
    for reg in C['regions']:
        sgg = reg.get('stdg')
        if not sgg:
            continue
        d = {}
        for key in BJ_SETS:
            try:
                d[key] = _bj_query(key, ym, sgg)
            except Exception as e:  # noqa: BLE001
                errs.append('%s %s' % (reg['name'], key))
            _t.sleep(0.2)
        out[reg['name']] = d
    me = [r for r in C['regions'] if r['name'] == C['me']][0]
    prev = {}
    py = ym_shift(ym, -12)
    for key in ('disabled', 'basic', 'pension', 'facility'):
        try:
            prev[key] = _bj_query(key, py, me['stdg'])
        except Exception as e:  # noqa: BLE001
            errs.append('prev %s' % key)
    if not any(v.get('basic') for v in out.values()):
        raise RuntimeError('복지로 자료 없음 (%s)' % ', '.join(errs[:5]))
    if errs:
        log('복지로 일부 실패: %s' % ', '.join(errs[:10]))
    return {'at': now().strftime('%Y-%m-%d'), 'ym': ym, 'prev_ym': py, 'regions': out, 'prev': prev}


TASIS_BC = ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12', '13', '14']
TASIS_BC_NM = {'00': '전체', '01': '농·임·어업', '02': '광업', '03': '제조업', '04': '전기·가스·수도업', '05': '도매업', '06': '소매업', '07': '부동산매매업',
               '08': '건설업', '09': '음식업', '10': '숙박업', '11': '운수·창고·통신업', '12': '부동산임대업', '13': '대리·중개·도급업', '14': '서비스업(기타포함)'}


def _tasis_map(ym, bc):
    import urllib.request as _ur
    bd = json.dumps({'dc_search': {'STT_OFR_TBL_NM': 'TTQSNAI01T082143', 'STT_PBL_YR': ym[:4], 'STT_PBL_MM': ym[4:], 'SCH_TFB_BC_CL': 'BC', 'SCH_CLUS_CL': 'sex',
                                   'SCH_TFB_BC_CD': bc, 'SCH_TFB_BC_NM': '', 'SCH_SIDO_CD': '51', 'SCH_SIDO_NM': '강원특별자치도', 'SCH_SGG_CD': '00000', 'SCH_SGG_NM': '전체'}}, ensure_ascii=False).encode()
    last = None
    for i in range(3):
        try:
            rq = _ur.Request('https://tasis.nts.go.kr/wqAction.do?actionId=ATWEPFFA001R04', data=bd, headers={
                'Content-Type': 'application/json; charset=UTF-8', 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://tasis.nts.go.kr/websquare/websquare.html?w2xPath=/cm/index.xml'})
            with _ur.urlopen(rq, timeout=30) as r:
                j = json.loads(r.read().decode('utf-8'))
            return {str(x.get('LABEL', '')).strip(): to_num(x.get('VAL')) for x in (j.get('dc_mapDataList') or [])}
        except Exception as e:  # noqa: BLE001
            last = e
            __import__('time').sleep(2 + 3 * i)
    raise RuntimeError('국세통계포털 호출 실패 %s %s: %s' % (ym, bc, last))


def tasis(C):
    """국세통계포털 우리동네가게(월별 공개): 강원 18개 시·군 14개 업태 가동사업자 — 최신 월·전월·전년 같은 달 + 13개월 추이."""
    ym = None
    t = now().strftime('%Y%m')
    for k in range(1, 6):
        c = ym_shift(t, -k)
        if _tasis_map(c, '00'):
            ym = c
            break
    if not ym:
        raise RuntimeError('국세통계포털 최신 월을 찾지 못함')

    def grab(m):
        out = {}
        for bc in TASIS_BC:
            vals = _tasis_map(m, bc)
            for lab, v in vals.items():
                name = match_region(lab, C['regions'])
                if name and v is not None:
                    out.setdefault(name, {})[bc] = v
        return out
    cur, pm, py = grab(ym), grab(ym_shift(ym, -1)), grab(ym_shift(ym, -12))
    ye = str(int(ym[:4]) - 1) + '12'
    pye = py if ye == ym_shift(ym, -12) else grab(ye)
    trend = []
    for k in range(12, -1, -1):
        m = ym_shift(ym, -k)
        try:
            v = _tasis_map(m, '00')
            trend.append([m, {match_region(a, C['regions']): b for a, b in v.items() if match_region(a, C['regions'])}])
        except Exception as e:  # noqa: BLE001
            log('국세통계 추이 %s 실패: %s' % (m, e))
    return {'at': now().strftime('%Y-%m-%d'), 'ym': ym, 'names': TASIS_BC_NM, 'cur': cur, 'prev_m': pm, 'prev_y': py, 'year_end': ye, 'prev_ye': pye, 'trend': trend}


LICENSE_SVCS = [('general_restaurants', '일반음식점'), ('rest_cafes', '휴게음식점'), ('bakeries', '제과점'), ('lodgings', '숙박업'), ('rural_homestays', '농어촌민박')]


def licenses(C, code='4211000'):
    """행정안전부 지방행정 인허가(공공데이터포털): 동해시 업종별 개업(인허가일)·폐업(폐업일) 월별 건수와 영업 중 업소 수, 최근 개업 업소."""
    key = urllib.parse.unquote(os.environ.get('DATA_GO_KR_KEY', '').strip())
    res = {'at': now().strftime('%Y-%m-%d'), 'kinds': {}, 'recent': []}
    y0 = str(int(now().strftime('%Y')) - 1)
    for svc, nm in LICENSE_SVCS:
        rows, page = [], 1
        while page <= 80:
            t = http_get('https://apis.data.go.kr/1741000/%s/info' % svc, {'serviceKey': key, 'pageNo': str(page), 'numOfRows': '300', 'returnType': 'json',
                                                                         'cond[OPN_ATMY_GRP_CD::EQ]': code}, tries=3, timeout=90)
            body = (json.loads(t).get('response') or {}).get('body') or {}
            items = (body.get('items') or {}).get('item') or []
            if isinstance(items, dict):
                items = [items]
            rows += items
            if len(items) < 300 or len(rows) >= int(body.get('totalCount') or 0):
                break
            page += 1
        rows = [r for r in rows if str(r.get('OPN_ATMY_GRP_CD')) == code]
        op, cl, active = {}, {}, 0
        for r in rows:
            a = str(r.get('LCPMT_YMD') or '').replace('-', '')
            c = str(r.get('CLSBIZ_YMD') or '').replace('-', '')
            if a[:4] >= y0:
                op[a[:6]] = op.get(a[:6], 0) + 1
                if a >= now().strftime('%Y') + '0101':
                    res['recent'].append([a, nm, r.get('BPLC_NM'), r.get('SNTTN_BZSTAT_NM') or r.get('BZSTAT_SE_NM') or '', (r.get('ROAD_NM_ADDR') or r.get('LOTNO_ADDR') or '').replace('강원특별자치도 동해시 ', '')])
            if c[:4] >= y0:
                cl[c[:6]] = cl.get(c[:6], 0) + 1
            if str(r.get('SALS_STTS_CD')) == '01':
                active += 1
        res['kinds'][nm] = {'open': op, 'close': cl, 'active': active, 'total': len(rows)}
    res['recent'].sort(key=lambda x: x[0], reverse=True)
    res['recent'] = res['recent'][:20]
    if not any(v['total'] for v in res['kinds'].values()):
        raise RuntimeError('인허가 자료 없음')
    return res
