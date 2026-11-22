"""농업 및 수산: 강원 18개 시·군 KOSIS 통계(국가데이터처).

- 2025 농림어업총조사(확정, 2026-09-29 공표, 2025.12.1 기준): 농가·전겸업·경영주 연령·가축·과수, 해수면 어가·어법·어획 품종·어선
- 농림어업조사(해마다): 시군별 농가·농가인구(2024년까지), 시군별 논밭 경지면적(2025년까지)
- 친환경농산물 인증(해마다, 2025년까지)
숫자는 표 그대로(추정 없음). 표마다 실패해도 나머지는 받습니다.
"""
import sources
from sources import kosis_meta, _call, match_region, to_num, now

# key, orgId, tblId, 설명, B분류 고르기('계' 또는 'age'), 최근 몇 해, 항목 이름(None=전부)
TABLES = (
    ('farm', '101', 'DT_1AG25102', '전·겸업별 농가(2025 농림어업총조사)', '계', 1, ['농가', '전업 농가', '겸업 농가']),
    ('farm_age', '101', 'DT_1AG25102', '경영주 연령별 농가(2025 농림어업총조사)', 'age', 1, ['농가']),
    ('farm_pop', '101', 'DT_1EA1011', '행정구역별 농가·농가인구(농림어업조사)', None, 6, ['농가', '농가인구']),
    ('land', '101', 'DT_1EB002', '시군별 논밭별 경지면적(농업면적조사)', None, 6, None),
    ('livestock', '101', 'DT_1AG25501', '가축 사육 농가 및 사육 규모(2025 농림어업총조사)', None, 1, None),
    ('fruit', '101', 'DT_1AG25411', '과수 재배 농가 및 면적(2025 농림어업총조사)', '계', 1, None),
    ('eco', '101', 'DT_1YL20121', '친환경농산물 인증현황(국립농산물품질관리원)', '계', 6, None),
    ('fish', '101', 'DT_1FS25103', '해수면 어가(2025 농림어업총조사)', '계', 1, ['해수면 어가', '총 가구원 수', '평균 가구원 수']),
    ('fish_age', '101', 'DT_1FS25103', '경영주 연령별 해수면 어가(2025 농림어업총조사)', 'age', 1, ['해수면 어가']),
    ('fish_method', '101', 'DT_1FS25113', '어법 종류별 해수면 어가(2025 농림어업총조사)', '계', 1, None),
    ('fish_species', '101', 'DT_1FS25115', '어획 품종별 해수면 어가(2025 농림어업총조사)', '계', 1, None),
    ('fish_boat', '101', 'DT_1FS25120', '어선 보유 해수면 어가(2025 농림어업총조사)', '계', 1, None),
)


def _region_obj(items, C):
    """행정구역 분류에서 강원 + 18개 시·군 코드."""
    gw = [x for x in items if str(x.get('ITM_NM', '')).strip().startswith('강원')]
    if not gw:
        return None
    g = gw[0].get('ITM_ID')
    kids = [x.get('ITM_ID') for x in items if x.get('UP_ITM_ID') == g and match_region(str(x.get('ITM_NM')), C['regions'])]
    if not kids:   # 한 단계 아래가 아니라 평평한 목록인 표
        kids = [x.get('ITM_ID') for x in items if match_region(str(x.get('ITM_NM')), C['regions']) and x.get('ITM_ID') != g]
    return [g] + kids


def _b_codes(items, mode):
    if mode == '계':
        k = [x.get('ITM_ID') for x in items if str(x.get('ITM_NM', '')).strip() == '계']
        return k[:1] or [items[0].get('ITM_ID')]
    if mode == 'age':
        top = [x for x in items if '연령' in str(x.get('ITM_NM', ''))]
        if not top:
            raise RuntimeError('연령 분류 없음')
        t = top[0].get('ITM_ID')
        return [x.get('ITM_ID') for x in items if x.get('UP_ITM_ID') == t]
    return None


def one(C, org, tbl, bmode, years, names):
    meta = kosis_meta({'key_env': 'KOSIS_KEY', 'meta_url': 'https://kosis.kr/openapi/statisticsData.do', 'params': {'orgId': org, 'tblId': tbl}})
    od = {}
    for m in meta:
        od.setdefault(m.get('OBJ_ID'), []).append(m)
    params = {'method': 'getList', 'format': 'json', 'jsonVD': 'Y', 'orgId': org, 'tblId': tbl, 'prdSe': 'F' if tbl.startswith(('DT_1AG25', 'DT_1FS25')) else 'Y', 'newEstPrdCnt': str(years)}   # 총조사는 5년 주기(F)
    it = od.get('ITEM') or []
    if names:
        ids = [x.get('ITM_ID') for x in it if str(x.get('ITM_NM', '')).strip() in names]
        if not ids:
            raise RuntimeError('항목 없음 %s' % names)
        params['itmId'] = '+'.join(ids) + '+'
    else:
        params['itmId'] = 'ALL'
    i = 0
    has_b = False
    for oid, items in od.items():
        if oid == 'ITEM':
            continue
        i += 1
        reg = _region_obj(items, C) if any('동해' in str(x.get('ITM_NM')) for x in items) else None
        if reg:
            params['objL%d' % i] = '+'.join(reg) + '+'
        else:
            b = _b_codes(items, bmode or '계')
            has_b = True
            params['objL%d' % i] = '+'.join(b) + '+'
    rows = _call({'key_env': 'KOSIS_KEY', 'key_param': 'apiKey', 'url': 'https://kosis.kr/openapi/Param/statisticsParameterData.do', 'params': params}, {}, 'agri_' + tbl)
    data, units = {}, {}
    for r in rows:
        nm = str(r.get('C1_NM', '')).strip()
        reg = '강원' if nm.startswith('강원') else match_region(nm, C['regions'])
        if not reg:
            continue
        v = to_num(r.get('DT'))
        if v is None:
            continue
        item = str(r.get('ITM_NM', '')).strip()
        key = str(r.get('C2_NM', '')).strip() if (bmode == 'age' and has_b) else item
        cell = data.setdefault(str(r.get('PRD_DE')), {}).setdefault(reg, {})
        cell[key] = v
        units[key] = str(r.get('UNIT_NM', '') or '').strip()
    if not data:
        raise RuntimeError('응답이 비었음')
    return data, units


def collect(C):
    out = {'at': now().strftime('%Y-%m-%d'), 'tables': {}, 'errors': {}}
    for key, org, tbl, desc, bmode, years, names in TABLES:
        try:
            data, units = one(C, org, tbl, bmode, years, names)
            out['tables'][key] = {'desc': desc, 'tbl': tbl, 'year': max(data), 'data': data, 'units': units}
        except Exception as e:  # noqa: BLE001
            out['errors'][key] = str(e)[:300]
    if not out['tables']:
        raise RuntimeError('농업·수산 표를 하나도 받지 못함: %s' % out['errors'])
    return out
