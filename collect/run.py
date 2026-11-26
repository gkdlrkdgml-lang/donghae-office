"""매일 실행: 수집 → 지표 계산 → 순위 → web/data/data.js 저장.

한 원천이 실패해도 나머지는 계속 진행하고, 실패한 지표는 '지난번 값'을 그대로 둡니다.
사용법:  python collect/run.py          (실제 수집)
        python collect/run.py --demo   (키 없이 시연용 가짜 값으로 화면 확인)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (settings, codes, load_env, save_json, load_json, log, now, read_manual, WEB_DATA, ym_shift)  # noqa: E402
import sources  # noqa: E402
import life
import tour  # noqa: E402
import power  # noqa: E402
import socket  # noqa: E402
socket.setdefaulttimeout(120)   # 응답 없는 서버에 무한정 매달리지 않게
import rail  # noqa: E402
import port  # noqa: E402
import apt  # noqa: E402
import waterq  # noqa: E402
import death  # noqa: E402
import admin_sync  # noqa: E402
import landlaw  # noqa: E402
import agri  # noqa: E402
import wipan  # noqa: E402
import ncpms  # noqa: E402
from rank import rank  # noqa: E402

STATE = os.path.join(WEB_DATA, 'state.json')


def load_state():
    if os.path.exists(STATE):
        try:
            return load_json(STATE)
        except Exception:  # noqa: BLE001
            pass
    return {'indicators': {}, 'admin': None, 'status': {}}


def ok(state, name, msg=''):
    state['status'][name] = {'ok': True, 'at': now().strftime('%Y-%m-%d %H:%M'), 'msg': msg}


def fail(state, name, e):
    prev = state['status'].get(name, {})
    state['status'][name] = {'ok': False, 'at': now().strftime('%Y-%m-%d %H:%M'), 'msg': str(e),
                             'last_ok': prev.get('at') if prev.get('ok') else prev.get('last_ok')}
    log('실패 · %s · %s' % (name, e))


def set_ind(state, iid, values, basis, src_from='api'):
    state['indicators'][iid] = {'values': values, 'basis': basis, 'from': src_from, 'at': now().strftime('%Y-%m-%d %H:%M')}


def collect(state, S, C):
    # 1) 시·군 인구 → 1번 인구 증감률
    pop = None
    try:
        pop = sources.population(S, C)
        vals = {}
        for name, cur in pop['cur'].items():
            prev = pop['prev'].get(name)
            if prev and prev['total']:
                vals[name] = (cur['total'] - prev['total']) / prev['total'] * 100
        set_ind(state, 'pop_change', vals, '%s년 %s월 (전년 같은 달 대비)' % (pop['ym'][:4], int(pop['ym'][4:])))
        ok(state, 'population', '%s 기준 %d개 시·군' % (pop['ym'], len(pop['cur'])))
    except Exception as e:  # noqa: BLE001
        fail(state, 'population', e)

    # 2) 동해시 행정동 인구
    if pop:
        try:
            dongs = sources.dong_population(S, C, pop['ym'])
            state['admin'] = {
                'ym': pop['ym'], 'prev_ym': pop['prev_ym'], 'prevm_ym': pop.get('prevm_ym'),
                'regions': {k: {'total': v['total'], 'hh': v['hh'], 'male': v['male'], 'female': v['female'],
                                'prev': pop['prev'].get(k, {}).get('total'),
                                'prev_m': pop.get('prev_m', {}).get(k, {}).get('total'),
                                'prev_m_hh': pop.get('prev_m', {}).get(k, {}).get('hh'),
                                'prev_m_male': pop.get('prev_m', {}).get(k, {}).get('male'),
                                'prev_m_female': pop.get('prev_m', {}).get(k, {}).get('female')} for k, v in pop['cur'].items()},
                'dongs': dongs,
            }
            ok(state, 'dong_population', '%d개 동' % len(dongs))
        except Exception as e:  # noqa: BLE001
            fail(state, 'dong_population', e)

    # 3) 연령 → 2번 생산연령, 3번 고령 (정확한 연령 경계, 추정 없음)
    try:
        ages, basis_ym, mode = sources.age(S, C)
        b = basis_ym or (pop['ym'] if pop else '')
        basis = ('%s년 %s월' % (b[:4], int(b[4:6]))) if b else '최근 공표'
        set_ind(state, 'working_age', {k: v['working_age'] for k, v in ages.items()}, basis)
        set_ind(state, 'elderly', {k: v['elderly'] for k, v in ages.items()}, basis)
        if state.get('admin'):
            mine = ages.get(C['me'], {})
            state['admin']['age_bands'] = mine.get('bands')
            if mine.get('total'):
                state['admin']['age_counts'] = {'total': round(mine['total']),
                                                'working': round(mine['total'] * mine['working_age'] / 100),
                                                'elderly': round(mine['total'] * mine['elderly'] / 100)}
            state['admin']['ages'] = {k: {'bands': v.get('bands'), 'total': round(v['total']),
                                          'working': round(v['total'] * v['working_age'] / 100),
                                          'elderly': round(v['total'] * v['elderly'] / 100)}
                                      for k, v in ages.items() if v.get('total')}
        ok(state, 'age', '%s · %d개 시·군' % (mode, len(ages)))
        if mode == 'kosis' and state.get('admin'):
            try:
                admm, aym, cityg = sources.admm_kosis(S, C)
                state['admin']['admm'] = admm
                state['admin']['admm_ym'] = aym
                state['admin']['groups'] = cityg
            except Exception as e2:  # noqa: BLE001
                state['admin'].pop('admm', None)
                print('행정동 인구 실패:', e2)
    except Exception as e:  # noqa: BLE001
        fail(state, 'age', e)
        for iid in ('working_age', 'elderly'):
            man, mb = read_manual(iid)
            if man:
                set_ind(state, iid, man, mb or '수기 입력', 'manual')

    # 3-2) 전입·전출(KOSIS 국내인구이동), 청년·고령 인원(1세별), 출생·사망·1인세대(행안부)
    if state.get('admin'):
        vy = state['admin'].get('ym')
        for tryym in [vy, ym_shift(vy, -1)] if vy else []:
            try:
                state['admin']['vital'] = sources.vital(S, C, tryym)
                ok(state, 'vital', tryym)
                break
            except Exception as e:  # noqa: BLE001
                fail(state, 'vital', e)
        try:   # 월별 출생·사망 신고(행안부 주민등록, 18개 시·군) 지난해 1월부터 쌓음 — 지난 달은 다시 안 받음
            vm = state.setdefault('life', {}).setdefault('vitalm', {'birth': {}, 'death': {}})
            last = (state['admin'].get('vital') or {}).get('ym')
            if last:
                yms, y0 = [], '%d01' % (int(last[:4]) - 1)
                while y0 <= last:
                    yms.append(y0); y0 = ym_shift(y0, 1)
                t0 = time.time()
                for kind in ('birth', 'death'):
                    for m in yms:
                        if m in vm[kind] and m < ym_shift(last, -1):
                            continue
                        if time.time() - t0 > 240:
                            break
                        r = sources.mois_monthly(S, C, kind, m, '2')
                        if len(r) >= 15:
                            vm[kind][m] = {k: v['total'] for k, v in r.items()}
                for kind in vm:
                    for m in [m for m in vm[kind] if m < yms[0]]:
                        vm[kind].pop(m)
                vm['ym'] = last
                log('월별 출생·사망: %s' % {k: len(vm[k]) for k in ('birth', 'death')})
        except Exception as e:  # noqa: BLE001
            log('월별 출생·사망 실패: %s' % e)
        try:
            state['admin']['youth'] = sources.youth_elderly(S, C)
            ok(state, 'youth', state['admin']['youth']['ym'])
        except Exception as e:  # noqa: BLE001
            fail(state, 'youth', e)
        try:
            state['admin']['migration'] = sources.migration(S, C)
            ok(state, 'migration', state['admin']['migration']['ym'])
        except Exception as e:  # noqa: BLE001
            fail(state, 'migration', e)

    # 5) 2단계 생활 분야: 의료기관·충전기(주 1회), 대기질(매번), 방문자(새 달만)
    L = state.setdefault('life', {})
    pops = {k: v.get('total') for k, v in ((state.get('admin') or {}).get('regions') or {}).items()}

    def stale(key, days):
        r = _stale(key, days)
        if r:
            log('받기 시작: %s' % key)      # 어느 단계가 오래 걸리는지 로그 시각으로 알 수 있게
        return r

    def _stale(key, days):
        if '--force-all' in sys.argv:   # 수동 실행 mode=force: 캐시 무시하고 모든 API 다시 호출
            return True
        at = (L.get(key) or {}).get('at')
        try:
            return (now().date() - __import__('datetime').date.fromisoformat(at)).days >= days
        except Exception:  # noqa: BLE001
            return True

    def per(vals, mult):
        return {k: v / pops[k] * mult for k, v in vals.items() if pops.get(k)}
    for key, fn, days in (('hospitals', life.hospitals, 6), ('ev', life.ev_chargers, 6)):
        nopharm = key == 'hospitals' and not any('약국' in (v.get('kinds') or {}) and 'top' in v for v in ((L.get('hospitals') or {}).get('regions') or {}).values())
        if stale(key, days) or nopharm or '--force-life' in sys.argv:
            try:
                L[key] = fn(C)
                ok(state, key, '%d개 시·군' % len(L[key]['regions']))
            except Exception as e:  # noqa: BLE001
                fail(state, key, e)
    if L.get('hospitals'):
        set_ind(state, 'medical', {k: v['total'] for k, v in L['hospitals']['regions'].items()}, L['hospitals']['at'] + ' 기준 요양기관(약국 포함)')
        _A = state.get('admin') or {}
        _pop = {k: (v or {}).get('total') for k, v in (_A.get('regions') or {}).items()}
        _ym = str(_A.get('ym') or '')
        set_ind(state, 'doc_per', {k: v['doctors'] / _pop[k] * 1000 for k, v in L['hospitals']['regions'].items() if v.get('doctors') is not None and _pop.get(k)},
                L['hospitals']['at'] + ' 기준 의사 수 ÷ ' + (_ym[:4] + '년 ' + str(int(_ym[4:])) + '월 ' if len(_ym) == 6 else '') + '주민등록인구')
    if L.get('ev'):
        set_ind(state, 'ev', {k: v['total'] for k, v in L['ev']['regions'].items()}, L['ev']['at'] + ' 기준 충전기')
    try:
        L['air'] = life.air(C)
        ok(state, 'air', L['air']['time'])
    except Exception as e:  # noqa: BLE001
        fail(state, 'air', e)
    try:
        months, last, vdays = life.visitors(C, L.get('visit_months'), L.get('visit_days'))
        L['visit_months'], L['visit_last'], L['visit_days'] = months, last, vdays
        ok(state, 'visitors', '%s까지' % last)
    except Exception as e:  # noqa: BLE001
        fail(state, 'visitors', e)
    try:
        L['cars'] = sources.vehicles(S, C)
        ok(state, 'cars', L['cars']['ym'])
    except Exception as e:  # noqa: BLE001
        fail(state, 'cars', e)
    if L.get('cars'):
        set_ind(state, 'cars', {k: v.get('total', {}).get('all') for k, v in L['cars']['regions'].items() if v.get('total', {}).get('all')},
                '%s년 %d월 자동차 등록대수' % (L['cars']['ym'][:4], int(L['cars']['ym'][4:])))
    if stale('tsafe', 6) or not (L.get('tsafe') or {}).get('road') or '--force-life' in sys.argv:
        try:
            L['tsafe'] = dict(sources.traffic_safety(S, C), at=now().strftime('%Y-%m-%d'))
            ok(state, 'tsafe', ', '.join(k for k in L['tsafe'] if k != 'at'))
        except Exception as e:  # noqa: BLE001
            fail(state, 'tsafe', e)
    if stale('parking', 6) or not L.get('parking') or any(v.get('private') for v in (L.get('parking') or {}).get('regions', {}).values()) or '--force-life' in sys.argv:
        try:
            L['parking'] = {'at': now().strftime('%Y-%m-%d'), 'regions': tour.parking(C)}
            ok(state, 'parking', '%d개 시·군' % len(L['parking']['regions']))
        except Exception as e:  # noqa: BLE001
            fail(state, 'parking', e)
    if L.get('parking'):
        set_ind(state, 'parking', {k: v['spaces'] for k, v in L['parking']['regions'].items() if v.get('spaces')}, '%s 기준 공영주차장(표준데이터)' % L['parking']['at'])
    if stale('taxi', 6) or not L.get('taxi') or '--force-life' in sys.argv:
        try:
            L['taxi'] = {'at': now().strftime('%Y-%m-%d'), 'regions': tour.taxi(C)}
            ok(state, 'taxi', '%d개 시·군' % len(L['taxi']['regions']))
        except Exception as e:  # noqa: BLE001
            fail(state, 'taxi', e)
    if L.get('taxi'):
        set_ind(state, 'taxi', {k: v['total'] for k, v in L['taxi']['regions'].items() if v.get('total')}, '%s 기준 택시업체 표준데이터(면허 대수)' % L['taxi']['at'])
    if stale('bus', 6) or not L.get('bus') or '--force-life' in sys.argv:
        try:
            L['bus'] = dict(tour.bus_stops(C), at=now().strftime('%Y-%m-%d'))
            ok(state, 'bus', '%s %d개 시·군' % (L['bus']['ymd'], len(L['bus']['regions'])))
        except Exception as e:  # noqa: BLE001
            fail(state, 'bus', e)
    if stale('buscorp', 7) or not L.get('buscorp') or '--force-life' in sys.argv:
        try:
            L['buscorp'] = {'at': now().strftime('%Y-%m-%d'), 'regions': tour.bus_corp(C)}
            ok(state, 'buscorp', '%d개 시·군(업체 표준데이터를 올린 곳)' % len(L['buscorp']['regions']))
        except Exception as e:  # noqa: BLE001
            fail(state, 'buscorp', e)
    if stale('busfirm', 7) or not L.get('busfirm') or '--force-life' in sys.argv:
        try:
            L['busfirm'] = dict(tour.bus_firms(C), at=now().strftime('%Y-%m-%d'))
            ok(state, 'busfirm', '%s년 %d개 시·군 · 농어촌버스 %d곳' % (L['busfirm']['year'], len(L['busfirm']['regions']), len(L['busfirm']['rural'])))
        except Exception as e:  # noqa: BLE001
            fail(state, 'busfirm', e)
    if L.get('bus'):
        set_ind(state, 'bus_stops', {k: v['stops'] for k, v in L['bus']['regions'].items()}, '%s 기준 시내버스 정류장(국토부)' % L['bus']['ymd'])
    T = L.get('tsafe') or {}
    if T.get('acc'):
        set_ind(state, 'accidents', {k: v.get('A1') for k, v in T['acc']['regions'].items() if v.get('A1') is not None},
                '%s년 교통사고(행정안전부)' % T['acc']['year'])
    # 경제: 국세청 사업자(연) — 30일마다
    if stale('economy', 7) or '--force-life' in sys.argv:
        try:
            L['economy'] = sources.economy(S, C)
            ok(state, 'economy', '%s년 %d개 시·군' % (L['economy']['year'], len(L['economy']['active'].get(L['economy']['year'], {}))))
        except Exception as e:  # noqa: BLE001
            fail(state, 'economy', e)
    if stale('eco_ind', 7) or '--force-life' in sys.argv:
        try:
            L['eco_ind'] = sources.economy_industry(S, C)
            ok(state, 'eco_ind', '%s년' % L['eco_ind']['year'])
        except Exception as e:  # noqa: BLE001
            fail(state, 'eco_ind', e)
    if stale('social', 3) or 'ltc' not in (L.get('social') or {}) or '--force-life' in sys.argv:
        try:
            L['social'] = sources.social(S, C)
            ok(state, 'social', '시설 %s · 수급 %s' % (L['social'].get('fac_year'), L['social'].get('rcp_year')))
        except Exception as e:  # noqa: BLE001
            fail(state, 'social', e)
    for key, fn, days in (('wx_year', lambda: sources.weather_year(), 1), ('air_year', lambda: sources.air_year(C), 1), ('wq', lambda: sources.water_quality(L.get('wq')), 7)):
        if stale(key, days) or ('--force-' + key) in sys.argv or (key == 'air_year' and not (L.get(key) or {}).get('start')):
            try:
                L[key] = fn()
                ok(state, key, '%s · %d곳' % (L[key].get('end', L[key]['at']), len(L[key].get('regions') or L[key].get('points') or {})))
            except Exception as e:  # noqa: BLE001
                fail(state, key, e)
    if stale('attr', 3) or '--force-attr' in sys.argv:
        try:
            L['attr'] = sources.attractions(C, L.get('attr'))
            ok(state, 'attr', '최신 %s · %d개월' % (L['attr']['latest'], len(L['attr']['months'])))
        except Exception as e:  # noqa: BLE001
            fail(state, 'attr', e)
    if stale('stores', 3) or '--force-stores' in sys.argv:
        try:
            L['stores'] = sources.stores(C, os.path.join(WEB_DATA, 'stores_snap.json'))
            ok(state, 'stores', '%s 기준 %d개 시·군' % (L['stores']['stdrYm'], len(L['stores']['regions'])))
        except Exception as e:  # noqa: BLE001
            fail(state, 'stores', e)
    if stale('water', 7) or '--force-life' in sys.argv or '--force-water' in sys.argv:
        try:
            L['water'] = sources.water(C)
            ok(state, 'water', ', '.join('%s %s' % (k, v['year']) for k, v in L['water']['tables'].items()) + (' · 실패 %s' % list(L['water']['errors']) if L['water']['errors'] else ''))
        except Exception as e:  # noqa: BLE001
            fail(state, 'water', e)
    # 국토·건축: 18개 시·군 도시계획 조례의 용도지역별 건폐율·용적률(주 1회, 개정된 조례만 다시 받음)
    if os.environ.get('LAW_OC') and (stale('ordin', 7) or '--force-ordin' in sys.argv or not (((L.get('ordin') or {}).get('regions') or {}).get(C['me']) or {}).get('uses_v') == 2):
        try:
            L['ordin'] = landlaw.collect(C, L.get('ordin'))
            ok(state, 'ordin', '%d개 시·군 조례' % len(L['ordin']['regions']) + (' · 실패 %s' % L['ordin']['errors'] if L['ordin']['errors'] else ''))
        except Exception as e:  # noqa: BLE001
            fail(state, 'ordin', e)
    # 에너지·전력(한전): 새 달은 보통 2달 뒤 공표 → 사흘마다 확인
    # 농업 및 수산(KOSIS: 2025 농림어업총조사·농림어업조사·경지면적·친환경 인증) — 주 1회
    if stale('agri', 3) or not (L.get('agri') or {}).get('tables') or '--force-agri' in sys.argv:
        try:
            L['agri'] = agri.collect(C)
            ok(state, 'agri', ', '.join('%s %s' % (k, v['year']) for k, v in L['agri']['tables'].items()) + (' · 실패 %s' % list(L['agri']['errors']) if L['agri']['errors'] else ''))
        except Exception as e:  # noqa: BLE001
            fail(state, 'agri', e)
    # 수협 위판(동해시수협 등 강원 7개 수협, 달마다) — 하루 1번 확인, 덜 받은 달이 있으면 이어서
    WP = L.get('wipan') or {}
    if stale('wipan', 1) or WP.get('errors') or len(WP.get('months') or {}) < wipan.KEEP_ME or '--force-wipan' in sys.argv:
        try:
            L['wipan'] = wipan.collect(WP)
            ok(state, 'wipan', '%s 기준 %d개월' % (L['wipan']['ym'], len(L['wipan']['months'])) + (' · 이어 받을 달 %s' % list(L['wipan']['errors']) if L['wipan']['errors'] else ''))
        except Exception as e:  # noqa: BLE001
            fail(state, 'wipan', e)
    # 농진청 병해충 예찰(강릉·삼척 — 동해는 조사 지역 아님) — 하루 1번
    if os.environ.get('NCPMS_KEY') and (stale('ncpms', 1) or '--force-ncpms' in sys.argv):
        try:
            L['ncpms'] = dict(ncpms.collect(), at=now().strftime('%Y-%m-%d'))
            ok(state, 'ncpms', ', '.join('%s %s' % (x['crop'], x.get('date', x.get('error', ''))) for x in L['ncpms']['survey']))
        except Exception as e:  # noqa: BLE001
            fail(state, 'ncpms', e)
    AG = (L.get('agri') or {}).get('tables') or {}
    def _ag(k, item, lab, f=None):
        t = AG.get(k)
        if not t:
            return
        d = t['data'][t['year']]
        vals = {r: (f(v) if f else v.get(item)) for r, v in d.items() if r != '강원'}
        vals = {r: x for r, x in vals.items() if x is not None}
        if vals:
            set_ind(state, lab[0], vals, lab[1] % t['year'])
    _ag('farm', '농가', ('ag_farms', '%s년 12월 1일 기준 농가(2025 농림어업총조사)'))
    _ag('land', '경지면적: 계', ('ag_land', '%s년 경지면적(논+밭, 농업면적조사)'))
    _ag('farm_age', None, ('ag_old', '%s년 경영주 65세 이상 농가 비율(2025 농림어업총조사)'),
        lambda v: (sum(x for a, x in v.items() if a[:2].isdigit() and int(a[:2]) >= 65) / sum(v.values()) * 100) if sum(v.values()) else None)
    _ag('eco', '농가수', ('ag_eco', '%s년 친환경농산물 인증 농가(국립농산물품질관리원)'))
    _ag('fish', '해수면 어가', ('fs_hh', '%s년 12월 1일 기준 해수면 어가(2025 농림어업총조사)'))
    log('철도 시작')
    try:   # 철도(동해시 역): 지난 날은 캐시, 최근 2일·오늘 시간표만 새로
        L['rail'] = rail.collect(L.get('rail'))
        R0 = L['rail']
        ok(state, 'rail', '정차 %d일 · 오늘 시간표 %s' % (len(R0['days']), ', '.join('%s %d편' % (k, len(v)) for k, v in ((R0.get('today') or {}).get('dep') or {}).items())))
    except Exception as e:  # noqa: BLE001
        fail(state, 'rail', e)
    if stale('port', 3) or not (L.get('port') or {}).get('items') or '--force-all' in sys.argv:
        log('항만 시작')
        try:   # 항만물류(해양수산부 PORT-MIS 월 통계)
            L['port'] = port.collect(L.get('port')); L['port']['at'] = now().date().isoformat()
            P0 = L['port']
            ok(state, 'port', '입출항 ~%s · 연안화물 ~%s' % (max(P0['vessel']) if P0['vessel'] else '-', max(P0['cargo']) if P0['cargo'] else '-'))
        except Exception as e:  # noqa: BLE001
            fail(state, 'port', e)
    if stale('death', 7) or '--force-all' in sys.argv:
        try:   # 사망원인통계(강원 18개 시·군, 최근 5년)
            L['death'] = death.collect(L.get('death')); L['death']['at'] = now().date().isoformat()
            ok(state, 'death', '%s년까지' % L['death']['years'][-1])
        except Exception as e:  # noqa: BLE001
            fail(state, 'death', e)
    if stale('waterq', 3) or '--force-all' in sys.argv:
        log('수질검사 시작')
        try:   # 수돗물 법정 수질검사(K-water, 강원 정수장 월별)
            L['waterq'] = waterq.collect(L.get('waterq')); L['waterq']['at'] = now().date().isoformat()
            ok(state, 'waterq', '최근 %s' % L['waterq']['latest'])
        except Exception as e:  # noqa: BLE001
            fail(state, 'waterq', e)
    if stale('waterfee', 7) or '--force-all' in sys.argv:
        log('요금표 시작')
        try:   # 동해시 상하수도 요금표(사업소 홈페이지, 주 1회)
            L['waterfee'] = waterq.fee(); L['waterfee']['at'] = now().date().isoformat()
            ok(state, 'waterfee', '표 %d개' % len(L['waterfee']['tables']))
        except Exception as e:  # noqa: BLE001
            fail(state, 'waterfee', e)
    if stale('apt', 1) or '--force-all' in sys.argv:
        log('아파트 시작')
        try:   # 아파트 매매 실거래(18개 시·군)
            L['apt'] = apt.collect(L.get('apt')); L['apt']['at'] = now().date().isoformat()
            ok(state, 'apt', '%s까지 · 오류 %d' % (L['apt']['months'][-1], len(L['apt']['errors'])))
        except Exception as e:  # noqa: BLE001
            fail(state, 'apt', e)
    if os.environ.get('KEPCO_KEY') and (stale('power', 3) or len((L.get('power') or {}).get('months') or {}) < power.KEEP - 1 or '--force-power' in sys.argv):
        try:
            L['power'] = power.collect(C, L.get('power'))
            ok(state, 'power', '%s 기준 · %d개월' % (L['power']['ym'], len(L['power']['months'])) + (' · 일부 실패 %d' % len(L['power']['errors']) if L['power']['errors'] else ''))
        except Exception as e:  # noqa: BLE001
            fail(state, 'power', e)
    PW = L.get('power') or {}
    if PW.get('ym') and PW['months'].get(PW['ym']):
        pym = PW['ym']
        cm, pm = PW['months'][pym], PW['months'].get(ym_shift(pym, -12)) or {}
        lab = '%s년 %d월' % (pym[:4], int(pym[4:]))
        set_ind(state, 'pw_total', {k: v['total'] / 1e6 for k, v in cm.items()}, lab + ' 한 달 · 한전')
        set_ind(state, 'pw_house', {k: v['house']['kwh'] for k, v in cm.items() if (v.get('house') or {}).get('kwh') is not None}, lab + ' 가구 평균 · 한전')
        set_ind(state, 'pw_house_bill', {k: v['house']['bill'] for k, v in cm.items() if (v.get('house') or {}).get('bill') is not None}, lab + ' 가구 평균 · 한전')
        set_ind(state, 'pw_ind_share', {k: v['by'].get('산업용', {}).get('kwh', 0) / v['total'] * 100 for k, v in cm.items() if v['total']}, lab + ' 전체 사용량 중 산업용 · 한전')
        if pm:
            set_ind(state, 'pw_yoy', {k: (v['total'] - pm[k]['total']) / pm[k]['total'] * 100 for k, v in cm.items() if pm.get(k) and pm[k]['total']},
                    lab + ' (전년 같은 달 대비) · 한전')
    if stale('employ', 3) or '--force-life' in sys.argv:
        try:
            L['employ'] = sources.employment(S, C)
            ok(state, 'employ', L['employ']['period'])
        except Exception as e:  # noqa: BLE001
            fail(state, 'employ', e)
    EM = L.get('employ') or {}
    if EM.get('period'):
        pdl = EM['period']
        set_ind(state, 'emp_rate', {k: v.get('rate_1564') for k, v in EM['data'][pdl].items() if v.get('rate_1564') is not None}, '%s년 %s반기 15~64세 고용률(통계청 지역별고용조사)' % (pdl[:4], '상' if pdl.endswith('01') or '1/2' in pdl else '하'))
    if stale('bokjiro', 3) or '--force-life' in sys.argv:
        try:
            L['bokjiro'] = sources.bokjiro(C)
            ok(state, 'bokjiro', L['bokjiro']['ym'])
        except Exception as e:  # noqa: BLE001
            fail(state, 'bokjiro', e)
    BJ = L.get('bokjiro') or {}
    pops = {k: v.get('total') for k, v in ((state.get('admin') or {}).get('regions') or {}).items()}
    if BJ.get('regions'):
        ylab = '%s년 %d월' % (BJ['ym'][:4], int(BJ['ym'][4:]))
        rc = {k: sum(x or 0 for x in v.get('basic', {}).values()) / pops[k] * 100 for k, v in BJ['regions'].items() if v.get('basic') and pops.get(k)}
        dr = {k: sum(x or 0 for x in v.get('disabled', {}).values()) / pops[k] * 100 for k, v in BJ['regions'].items() if v.get('disabled') and pops.get(k)}
        fc = {k: sum(x or 0 for x in v.get('facility', {}).values()) for k, v in BJ['regions'].items() if v.get('facility')}
        if rc:
            set_ind(state, 'soc_rcp', rc, '%s 기초생활보장 수급자 ÷ 주민등록인구(복지로 복지통계)' % ylab)
        if dr:
            set_ind(state, 'soc_dis', dr, '%s 등록장애인 ÷ 주민등록인구(복지로 복지통계)' % ylab)
        if fc:
            set_ind(state, 'soc_fac', fc, '%s 사회복지시설(복지로 복지통계)' % ylab)
    SO = L.get('social') or {}
    if SO.get('facilities') and not BJ.get('regions'):
        set_ind(state, 'soc_fac', {k: v.get('total') for k, v in SO['facilities'].items() if v.get('total') is not None}, '%s년 사회복지시설(행정안전부)' % SO.get('fac_year'))
    if SO.get('recipients') and not BJ.get('regions'):
        set_ind(state, 'soc_rcp', {k: v.get('recipients_rate') for k, v in SO['recipients'].items() if v.get('recipients_rate') is not None}, '%s년 기초생활보장 수급자 비율(행정안전부)' % SO.get('rcp_year'))
        set_ind(state, 'soc_dis', {k: v.get('disabled_rate') for k, v in SO['recipients'].items() if v.get('disabled_rate') is not None}, '%s년 등록장애인 비율(행정안전부)' % SO.get('rcp_year'))
    if SO.get('elderly'):
        set_ind(state, 'soc_old', {k: v.get('per1000') for k, v in SO['elderly'].items() if v.get('per1000') is not None}, '%s년 노인 천명당 노인여가복지시설(통계청)' % SO.get('old_year'))
    if stale('tasis', 2) or 'young' not in (L.get('tasis') or {}) or '--force-life' in sys.argv:
        try:
            L['tasis'] = sources.tasis(C)
            ok(state, 'tasis', L['tasis']['ym'])
        except Exception as e:  # noqa: BLE001
            fail(state, 'tasis', e)
    if stale('licenses', 1) or (L.get('licenses') or {}).get('stale') or any(v.get('total') == 100 for v in ((L.get('licenses') or {}).get('kinds') or {}).values()) or '--force-life' in sys.argv:
        try:
            L['licenses'] = sources.licenses(C, prev=L.get('licenses'))
            ok(state, 'licenses', ', '.join('%s %d' % (k, v['active']) for k, v in L['licenses']['kinds'].items()) + (' · 지난 값 유지: ' + ', '.join('%s(%s)' % kv for kv in L['licenses']['stale'].items()) if L['licenses'].get('stale') else ''))
        except Exception as e:  # noqa: BLE001
            fail(state, 'licenses', e)
    EC = L.get('economy') or {}
    if EC.get('year'):
        y = EC['year']
        set_ind(state, 'biz_active', {k: v.get('total') for k, v in EC['active'][y].items() if v.get('total')}, '%s년 말 가동사업자(국세청)' % y)
        set_ind(state, 'biz_new', {k: v.get('total') for k, v in EC['new'][y].items() if v.get('total')}, '%s년 신규 사업자(국세청)' % y)
        set_ind(state, 'biz_net', {k: v.get('total', 0) - (EC['closed'][y].get(k) or {}).get('total', 0) for k, v in EC['new'][y].items() if k in EC['closed'][y]}, '%s년 신규−폐업(국세청)' % y)
    WY = L.get('wx_year') or {}
    if WY.get('regions'):
        y = str(WY['year']); e = WY['end']
        lab = '%s년 1월 1일~%d월 %d일' % (y, int(e[4:6]), int(e[6:]))
        for iid, k, nm in (('wx_rain', 'rain', '강수량'), ('wx_heat', 'heat', '폭염일수(최고 33℃ 이상)'), ('wx_trop', 'tropical', '열대야(최저 25℃ 이상)')):
            set_ind(state, iid, {r: v[y][k] for r, v in WY['regions'].items() if y in v}, '%s %s(기상청 ASOS 관측소)' % (lab, nm))
    AY = L.get('air_year') or {}
    if AY.get('regions'):
        y = str(AY['year']); e = AY['end']; st = AY.get('start') or (y + '0101')
        lab = '%s년 %d월 %d일~%d월 %d일' % (y, int(st[4:6]), int(st[6:]), int(e[4:6]), int(e[6:]))
        set_ind(state, 'air_good', {r: v[y]['good'] for r, v in AY['regions'].items() if y in v}, lab + ' 초미세먼지 좋음 날수(에어코리아 일평균)')
        set_ind(state, 'air_bad', {r: v[y]['bad'] for r, v in AY['regions'].items() if y in v}, lab + ' 초미세먼지 나쁨 이상 날수(에어코리아 일평균)')
        set_ind(state, 'air_avg', {r: v[y]['pm25'] for r, v in AY['regions'].items() if y in v}, lab + ' 초미세먼지 평균(에어코리아 일평균)')
    AT = L.get('attr') or {}
    if AT.get('months'):
        full = [ym for ym, m in AT['months'].items() if len(m) >= 17]   # 18개 시·군이 다 올라온 달까지만 비교
        ly = max(full) if full else AT['latest']
        yr = ly[:4]
        tot = {}
        for ym, m in AT['months'].items():
            if ym[:4] == yr and ym <= ly:
                for g, sp in m.items():
                    tot[g] = tot.get(g, 0) + sum(v[0] for v in sp.values())
        set_ind(state, 'attr_visit', {k: v / 10000 for k, v in tot.items()}, '%s년 1~%d월 유료관광지 입장객(관광자원통계)' % (yr, int(ly[4:])))
    SR = L.get('stores') or {}
    if SR.get('regions'):
        sy = SR['stdrYm']
        set_ind(state, 'shop_total', {k: v['total'] for k, v in SR['regions'].items()}, '%s년 %d월 영업 중인 상가(소상공인 상가정보)' % (sy[:4], int(sy[4:])))
        set_ind(state, 'shop_new', {k: v['new'] for k, v in SR['regions'].items()}, '%s년 1~%d월 새로 등록된 상가(소상공인 상가정보)' % (sy[:4], int(sy[4:])))
        if SR.get('changes'):
            c = SR['changes'][-1]
            set_ind(state, 'shop_close', {k: v['close'] for k, v in c['regions'].items()}, '%s→%s 사라진 상가(소상공인 상가정보)' % (c['from'], c['to']))
    WT = (L.get('water') or {}).get('tables') or {}

    def wpick(tk, prefix, label):
        t = WT.get(tk)
        if not t:
            return None
        y = t['year']
        vals = {}
        for reg, cell in t['data'][y].items():
            if reg == '강원':
                continue
            k = next((k for k in cell if k.startswith(prefix)), None)
            if k is not None:
                vals[reg] = cell[k]
        return (vals, '%s년 %s' % (y, label)) if vals else None
    for iid, tk, pre, lab in (('sew_rate', 'sewer', '공공하수처리구역인구보급률', '하수도 보급률(환경부 하수도통계)'),
                              ('sup_rate', 'supply', '지방 및 광역상수도 보급률', '상수도 보급률(환경부 상수도통계)'),
                              ('old_pipe', 'sops', '경년관비율', '20년 넘은 하수관 비율(지방공기업 경영정보)'),
                              ('w_price', 'wfee', '전체 · ㎥당요금', '수도요금 ㎥당 평균(지방공기업 경영정보)'),
                              ('w_real', 'wcost', '요금현실화율', '수도요금 현실화율(요금 ÷ 생산원가, 지방공기업 경영정보)')):
        r = wpick(tk, pre, lab)
        if r:
            set_ind(state, iid, r[0], r[1])
    TS = L.get('tasis') or {}
    if TS.get('cur'):
        tl = '%s년 %d월' % (TS['ym'][:4], int(TS['ym'][4:]))
        set_ind(state, 'biz_active', {k: v.get('00') for k, v in TS['cur'].items() if v.get('00')}, '%s 가동사업자(국세통계포털 우리동네가게)' % tl)
        set_ind(state, 'biz_yoy', {k: (v['00'] / TS['prev_y'][k]['00'] - 1) * 100 for k, v in TS['cur'].items() if v.get('00') and (TS['prev_y'].get(k) or {}).get('00')}, '%s 가동사업자 전년 같은 달 대비 증감률' % tl)
        if TS.get('young'):
            set_ind(state, 'biz_new', {k: v.get('cur') for k, v in TS['young'].items() if v.get('cur') is not None}, '%s 문 연 지 6개월 미만 사업자(국세통계포털)' % tl)
        if TS.get('prev_ye'):
            set_ind(state, 'biz_net', {k: v['00'] - TS['prev_ye'][k]['00'] for k, v in TS['cur'].items() if v.get('00') is not None and (TS['prev_ye'].get(k) or {}).get('00') is not None},
                    '%s년 1~%d월 가동사업자 순증(작년 12월 대비, 국세통계포털)' % (TS['ym'][:4], int(TS['ym'][4:])))
    # 관광지 집중률·단기예보(매번), 관광지·축제 목록(주 1회)
    for key, fn in (('cnctr', tour.concentration), ('weather', tour.weather)):
        try:
            L[key] = fn()
            ok(state, key, L[key].get('at') or L[key].get('base'))
            if key == 'cnctr':
                # 관광지별 집중률을 날짜별로 쌓아 둠(그날 발표된 당일 값) — 행사 전후 비교용
                H = L.setdefault('cnctr_hist', {})
                td = now().strftime('%Y%m%d')
                for n, rows in (L[key].get('spots') or {}).items():
                    for d, v in rows:
                        if d == td:
                            H.setdefault(d, {})[n] = v
        except Exception as e:  # noqa: BLE001
            fail(state, key, e)
    if stale('places', 6) or not (L.get('places') or {}).get('items') or '--force-life' in sys.argv:
        try:
            L['places'] = {'at': now().strftime('%Y-%m-%d'), 'items': tour.places()}
            ok(state, 'places', '%d곳' % len(L['places']['items']))
        except Exception as e:  # noqa: BLE001
            fail(state, 'places', e)
    if stale('festivals', 6) or not (L.get('festivals') or {}).get('items') or '--force-life' in sys.argv:
        try:
            L['festivals'] = {'at': now().strftime('%Y-%m-%d'), 'items': tour.festivals()}
            ok(state, 'festivals', '%d건' % len(L['festivals']['items']))
        except Exception as e:  # noqa: BLE001
            fail(state, 'festivals', e)
    try:
        dm, dn = tour.demand(C, L.get('demand'))
        if dm:
            L['demand'], L['demand_names'] = dm, dict(L.get('demand_names') or {}, **dn)
            ok(state, 'demand', max(dm))
    except Exception as e:  # noqa: BLE001
        fail(state, 'demand', e)
    if L.get('demand'):
        last = max(L['demand'])
        set_ind(state, 'tour_exp', {k: v.get('22') for k, v in L['demand'][last].items() if k != '강원' and v.get('22') is not None},
                '%s년 %d월 관광소비강도(한국관광공사)' % (last[:4], int(last[4:])))
    if stale('events', 3) or not (L.get('events') or {}).get('items') or any(str(x.get('title', '')).startswith(('[', '연극 ')) for x in (L.get('events') or {}).get('items', [])) or '--force-life' in sys.argv:
        try:
            L['events'] = {'at': now().strftime('%Y-%m-%d'), 'items': tour.events()}
            ok(state, 'events', '%d건' % len(L['events']['items']))
        except Exception as e:  # noqa: BLE001
            fail(state, 'events', e)
    # 시가 직접 적는 행사(config/events.json)를 축제 목록에 합칩니다
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'events.json'), encoding='utf-8') as fp:
            extra = json.load(fp).get('items', [])
        F = L.setdefault('festivals', {'at': now().strftime('%Y-%m-%d'), 'items': []})
        F['items'] = [x for x in F['items'] if not x.get('manual')]
        import re as _re0

        def _nk(t):
            return _re0.sub(r'\s|동해시|동해|제\d+회|\d{4}년?|축제$', '', str(t or ''))
        have = {(_nk(x.get('title')), x.get('start')) for x in F['items']}
        for i, e in enumerate((L.get('events') or {}).get('items', [])):
            k = (_nk(e['title']), e['start'])
            if k not in have:
                have.add(k)
                F['items'].append({'id': 'e%d' % i, 'type': '15', 'title': e['title'], 'start': e['start'], 'end': e.get('end') or e['start'],
                                   'place': e.get('place', ''), 'addr': '', 'lat': e.get('lat'), 'lng': e.get('lng'), 'manual': True, 'kind': e.get('kind'), 'src': e.get('src')})
        for i, e in enumerate(extra):
            if (_nk(e['title']), e['start']) not in have:
                F['items'].append({'id': 'm%d' % i, 'type': '15', 'title': e['title'], 'start': e['start'], 'end': e.get('end') or e['start'],
                                   'place': e.get('place', ''), 'addr': '', 'lat': None, 'lng': None, 'manual': True})
        F['items'].sort(key=lambda x: x.get('start') or '0')
    except Exception as e:  # noqa: BLE001
        log('행사 파일 읽기 실패: %s' % e)
    vm = L.get('visit_months') or {}
    if vm:
        # 올해 1월부터 다 찬 마지막 달까지 누계(1월에는 지난해 1~12월)
        lastm = sorted(vm)[-1]
        ytd = [ym for ym in sorted(vm) if ym[:4] == lastm[:4]]
        tot = {}
        for ym in ytd:
            for k, d in vm[ym].items():
                tot[k] = tot.get(k, 0) + d.get('outside', 0) + d.get('foreign', 0)
        set_ind(state, 'visitors', {k: v / 10000 for k, v in tot.items() if v}, '%s년 1~%d월 누계 외지인·외국인 방문(연인원)' % (lastm[:4], int(lastm[4:])))

    # 4) 재정자립도 → 11번 (순위는 당초, 최종은 같은 해 비교용)
    try:
        fin = sources.finance(S, C)
        set_ind(state, 'fin_indep', fin['values'], fin['basis'], fin['from'])
        state.setdefault('finance', {})['initial'] = fin.get('by_year') or state.get('finance', {}).get('initial', {})
        ok(state, 'finance', fin['basis'])
    except Exception as e:  # noqa: BLE001
        fail(state, 'finance', e)
    try:
        state.setdefault('finance', {})['final'] = sources.finance_years(S, C, 'finance_final')
        ok(state, 'finance_final', '%s년까지' % max(state['finance']['final']))
    except Exception as e:  # noqa: BLE001
        fail(state, 'finance_final', e)
    if sources.AMOUNTS:
        state.setdefault('finance', {})['amounts'] = {'initial': sources.AMOUNTS.get('finance', {}), 'final': sources.AMOUNTS.get('finance_final', {})}
    # 회계별 세입예산(통합회계): 국내 PC에서 받은 파일 manual/budget_accounts_<연도>.json
    mdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'manual')
    acc = {}
    for fn in sorted(os.listdir(mdir)) if os.path.isdir(mdir) else []:
        if fn.startswith('budget_accounts_') and fn.endswith('.json'):
            with open(os.path.join(mdir, fn), encoding='utf-8') as fp:
                j = json.load(fp)
            acc[str(j['year'])] = j['regions']
    try:   # 지방재정365 세입예산(ARBGT) — 서울 중계로 자동, 못 받은 해만 위 파일
        api = sources.budget_accounts(S, C)
        acc.update(api)
        ok(state, 'budget_accounts', '세입예산(통합회계) %s년' % ', '.join(sorted(api)) if api else '파일 사용')
    except Exception as e:  # noqa: BLE001
        fail(state, 'budget_accounts', e)
    if acc:
        state.setdefault('finance', {})['accounts'] = acc
    if sources.AMOUNTS:
        ai = sources.AMOUNTS.get('finance', {})
        if ai:
            yy = max(ai)
            set_ind(state, 'budget', {k: v['budget'] / 1e8 for k, v in ai[yy].items()}, '%s년 당초예산(일반회계)' % yy, 'file')


def demo(state, S, C):
    """키 없이 화면을 확인하기 위한 가짜 값. 화면 상단에 '시연용' 표시가 뜹니다."""
    import random
    rnd = random.Random(7)
    names = [r['name'] for r in C['regions']]
    def gen(lo, hi, me_rank, rev=True):
        vals = sorted([round(rnd.uniform(lo, hi), 2) for _ in names], reverse=rev)
        others = [n for n in names if n != C['me']]
        rnd.shuffle(others)
        out = {}
        it = iter(others)
        for i, v in enumerate(vals):
            out[C['me'] if i == me_rank - 1 else next(it)] = v
        return out
    set_ind(state, 'pop_change', gen(-2.1, 1.4, 9), '시연용', 'demo')
    set_ind(state, 'working_age', gen(54, 68, 6), '시연용', 'demo')
    set_ind(state, 'elderly', gen(21, 38, 12), '시연용', 'demo')
    set_ind(state, 'fin_indep', gen(8, 28, 14), '시연용', 'demo')
    cur = state['indicators']['fin_indep']['values']
    prev_init = {k: round(v - rnd.uniform(-1.2, 1.0), 1) for k, v in cur.items()}
    prev_final = {k: round(v - rnd.uniform(0.5, 3.0), 1) for k, v in prev_init.items()}
    y = now().year
    state['finance'] = {'initial': {str(y): cur, str(y - 1): prev_init}, 'final': {str(y - 1): prev_final}, 'demo': True}
    pops = {'춘천': 286000, '원주': 361000, '강릉': 208000, '동해': 88000, '태백': 38500, '속초': 81000, '삼척': 61500, '홍천': 66500,
            '횡성': 46000, '영월': 37000, '평창': 40500, '정선': 34000, '철원': 41500, '화천': 23000, '양구': 20500, '인제': 31000,
            '고성': 26800, '양양': 28000}
    pc = state['indicators']['pop_change']['values']
    regions = {k: {'total': v, 'hh': int(v / 2.05), 'male': int(v * 0.5), 'female': v - int(v * 0.5),
                   'prev': round(v / (1 + pc[k] / 100)), 'prev_m': v + 97, 'prev_m_hh': int(v / 2.05) - 12} for k, v in pops.items()}
    dongs = {'천곡동': [17600, 8900], '송정동': [6200, 3100], '북삼동': [10400, 4600], '부곡동': [4800, 2500], '동호동': [5900, 3000],
             '발한동': [3900, 2100], '묵호동': [6800, 3500], '북평동': [7300, 3400], '망상동': [2400, 1300], '삼화동': [4100, 2000]}
    state['admin'] = {'ym': now().strftime('%Y%m'), 'prev_ym': '', 'regions': regions,
                      'dongs': {k: {'total': v[0], 'hh': v[1]} for k, v in dongs.items()},
                      'age_bands': {'0': 5300, '10': 6900, '20': 8700, '30': 8600, '40': 12100, '50': 15300, '60': 15100, '70': 9300, '80': 5300, '90': 900, '100': 30},
                      'age_counts': {'total': 88030, 'working': 54740, 'elderly': 25430},
                      'admm': {k: {'total': v[0], 'elderly': v[1]} for k, v in {'천곡동': [21300, 22.1], '송정동': [9000, 26.0], '북삼동': [16800, 19.5], '부곡동': [5100, 30.2], '동호동': [4600, 33.1], '발한동': [6900, 31.4], '묵호동': [3900, 41.2], '북평동': [6100, 32.5], '망상동': [3300, 38.9], '삼화동': [6400, 27.3]}.items()}}
    for s in ('population', 'dong_population', 'age', 'finance', 'finance_final'):
        ok(state, s, '시연용 가짜 값')


ADMIN_INPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'manual', 'admin_input.json')


def apply_admin_input(state, S):
    """관리자 화면(web/admin.html)에서 넣은 동해시 최신 자료를 화면용 값에 덮어씁니다.
    원본 state는 건드리지 않도록 build()에서 복사본에만 적용합니다."""
    import copy
    if not os.path.exists(ADMIN_INPUT):
        return state
    try:
        ent = (load_json(ADMIN_INPUT) or {}).get('entries') or []
    except Exception as e:  # noqa: BLE001
        log('관리자 입력 읽기 실패 %s' % e)
        return state
    if not ent:
        return state
    st = copy.deepcopy(state)
    me = codes().get('me') or '동해'
    ent = sorted(ent, key=lambda x: x.get('date', ''))
    live = {}
    for sec in ('pop', 'dong', 'vital', 'employ'):
        last = [x for x in ent if x.get(sec)]
        if last:
            live[sec] = {'date': last[-1]['date'], 'v': last[-1][sec], 'history': [{'date': x['date'], 'v': x[sec]} for x in last[-24:]]}
    A = st.get('admin')
    # 공식 자료가 입력 기준일보다 새로우면 그 입력은 쓰지 않음(→ API 값 그대로)
    off_end = (A['ym'] + '31') if A and A.get('ym') else ''
    for sec in ('pop', 'dong', 'vital'):
        if sec in live and off_end and live[sec]['date'].replace('-', '') <= off_end:
            del live[sec]
    ep = str(((st.get('life') or {}).get('employ') or {}).get('period') or '')
    if 'employ' in live and len(ep) == 6:
        e_end = ep[:4] + ('0630' if ep[4:] == '01' else '1231')   # 고용률 공식 반기 끝날
        if live['employ']['date'].replace('-', '') <= e_end:
            # 고용률·취업자는 공식 반기 자료가 더 최신 → 공식 값. 일자리 사업·창출은 공식 자료가 없어 입력값을 그대로 씀
            jv = {k: v for k, v in (live['employ']['v'] or {}).items() if k in ('job_people', 'jobs', 'note') and v not in (None, '')}
            if any(k in jv for k in ('job_people', 'jobs')):
                live['employ'] = dict(live['employ'], v=jv)
            else:
                del live['employ']
    if A and live.get('pop'):
        d, v = live['pop']['date'], live['pop']['v']
        if A['regions'].get(me):
            r = A['regions'][me]
            A['official_me'] = dict(r)
            for k in ('total', 'hh', 'male', 'female'):
                if v.get(k) is not None:
                    r['prev_m' if k == 'total' else 'prev_m_' + k] = r[k]
                    r[k] = float(v[k])
            A['live'] = {'date': d, 'official_ym': A['ym']}
            # 바로 전 입력(공식 최신 달보다 늦은 것)과 비교
            pv = [h for h in live['pop']['history'][:-1] if h['date'].replace('-', '') > off_end and (h['v'] or {}).get('total') is not None]
            if pv:
                A['live']['prev_in'] = dict(pv[-1]['v'], date=pv[-1]['date'])
            tot = r['total']
            Y = A.get('youth') or {}
            if Y.get('cur') and any(v.get(k) is not None for k in ('age65', 'age15_64', 'age19_34')):
                Y['prev'] = dict(Y['cur'])
                Y['cur']['total'] = tot
                if v.get('age65') is not None:
                    Y['cur']['elderly'] = float(v['age65'])
                if v.get('age19_34') is not None:
                    Y['cur']['youth'] = float(v['age19_34'])
                if v.get('age15_64') is not None:
                    Y['cur']['working'] = float(v['age15_64'])
            VH = (A.get('vital') or {}).get('hsmb') or {}
            if v.get('hh1') is not None and (VH.get('cur') or {}).get(me):
                A['vital'] = dict(A['vital']); VH = A['vital']['hsmb'] = dict(VH)
                VH['prev'] = dict(VH.get('prev') or {}); VH['prev'][me] = dict(VH['cur'][me])
                VH['cur'] = dict(VH['cur']); VH['cur'][me] = dict(VH['cur'][me], one=float(v['hh1']), total=float(r.get('hh') or VH['cur'][me].get('total') or 0))
                VH['live'] = d
            for iid, k in (('elderly', 'age65'), ('working_age', 'age15_64')):
                I = st['indicators'].get(iid)
                if I and v.get(k) is not None and tot:
                    I['values'] = dict(I['values'])
                    I['values'][me] = float(v[k]) / tot * 100
                    I['basis'] = I['basis'] + ' · 동해시는 %s 관리자 입력' % d
    if A and live.get('dong') and A.get('admm'):
        # 행정동(3D 지도·행정동 표): 인구, 65세 이상 → 고령 비율. 「지난달 대비」는 공식 최신 달 값과 비교
        A['admm'] = {k: dict(v) for k, v in A['admm'].items()}
        for nm, dv in ((live['dong']['v'] or {}).get('_admm') or {}).items():
            if nm in A['admm'] and dv.get('total') is not None:
                o = A['admm'][nm]
                o['prev_total'] = o.get('total')
                o['total'] = float(dv['total'])
                if dv.get('age65') is not None and o['total']:
                    o['elderly'] = float(dv['age65']) / o['total'] * 100
        _in = (live['dong']['v'] or {}).get('_admm') or {}
        if _in:
            A['admm_live'] = {'date': live['dong']['date'], 'official_ym': A.get('admm_ym') or A.get('ym')}
            for nm, o in A['admm'].items():   # 입력 안 한 동은 「공식 최신 달 대비」를 낼 수 없어 비움
                if nm not in _in or (_in[nm] or {}).get('total') is None:
                    o['prev_total'] = None
    if A and live.get('dong') and A.get('dongs'):
        for nm, dv in live['dong']['v'].items():
            if nm == '_admm' or not isinstance(dv, dict):
                continue
            if nm in A['dongs'] and dv.get('total') is not None:
                A['dongs'][nm] = {'total': float(dv['total']), 'hh': float(dv.get('hh') or A['dongs'][nm].get('hh') or 0)}
    st['admin_live'] = live
    return st


def build(state, S, C):
    state = apply_admin_input(state, S)
    out = {
        'generated_at': now().strftime('%Y-%m-%d %H:%M'),
        'demo': any(v.get('from') == 'demo' for v in state['indicators'].values()),
        'title': S['title'], 'slogan': S.get('slogan', ''), 'map': {'vworld': (S.get('map') or {}).get('vworld_key', '')}, 'me': C['me'], 'menu': [m for m in S['menu'] if m.get('show', True)],
        'frame': S.get('frame', {}), 'judge': S['judge'],
        'regions': [r['name'] for r in C['regions']],
        'indicators': [], 'admin': state.get('admin'), 'admin_live': state.get('admin_live'), 'status': state['status'],
        'finance': state.get('finance') or {},
        'life': {k: v for k, v in (state.get('life') or {}).items()},
    }
    for ind in S['indicators']:
        d = state['indicators'].get(ind['id'])
        if not ind.get('show') or not d or not d.get('values'):
            continue  # 실제 값이 없는 지표는 화면에 내보내지 않습니다(확정 결정 11번)
        ranking, by = rank(d['values'], ind['dir'], S['judge'])
        me = by.get(C['me'])
        out['indicators'].append(dict(ind, basis=d['basis'], src_from=d['from'], at=d['at'],
                                      ranking=ranking, me=me, n=len(ranking)))
    # 분야 화면이 비면 메뉴에서 숨김
    has_fin = any(i['id'] == 'fin_indep' for i in out['indicators'])
    L = out.get('life') or {}
    need = {'water': L.get('water') or L.get('waterq'), 'port': (L.get('port') or {}).get('vessel') or (L.get('port') or {}).get('cargo'), 'rail': L.get('rail'), 'wx_year': L.get('wx_year'), 'stores': L.get('stores'), 'water': L.get('water'), 'social': L.get('social'), 'economy': L.get('economy'), 'welfare': L.get('hospitals'), 'traffic': L.get('ev') or L.get('cars'), 'env': L.get('air'), 'power': L.get('power'), 'land': L.get('ordin'), 'tour': L.get('visit_months'), 'agri': (L.get('agri') or {}).get('tables') or (L.get('wipan') or {}).get('months')}
    out['menu'] = [m for m in out['menu'] if not (m['id'] == 'finance' and not has_fin) and not (m['id'] in ('admin', 'compare') and not out['admin'])
                   and not (m['id'] in need and not need[m['id']])]
    return out


def main():
    load_env()
    S, C = settings(), codes()
    state = load_state()
    if '--demo' in sys.argv:
        demo(state, S, C)
        state['admin_demo'] = True
    else:
        # 시연용 값이 남아 있으면 실제 수집 전에 지웁니다.
        state['indicators'] = {k: v for k, v in state['indicators'].items() if v.get('from') != 'demo'}
        if state.pop('admin_demo', False):
            state['admin'] = None
        if (state.get('finance') or {}).get('demo'):
            state['finance'] = {}
        if '--admin-only' not in sys.argv:   # 관리자 입력만 반영할 때는 수집을 건너뜀(1~2분)
            collect(state, S, C)
    try:   # 관리자 입력(Supabase) 받기
        sig = admin_sync.pull()
        if sig is not None:
            state['admin_sig'] = sig
            log('관리자 입력 받음 · ' + sig)
    except Exception as e:  # noqa: BLE001
        log('관리자 입력(Supabase) 받기 실패 · 지난 값 사용 · %s' % e)
    save_json(STATE, state)
    data = build(state, S, C)
    os.makedirs(WEB_DATA, exist_ok=True)
    with open(os.path.join(WEB_DATA, 'data.js'), 'w', encoding='utf-8') as f:
        f.write('window.DONGHAE_DATA = ' + json.dumps(data, ensure_ascii=False) + ';\n')
    n_ok = sum(1 for v in state['status'].values() if v['ok'])
    log('완료 · 지표 %d개 표시 · 원천 %d/%d 성공' % (len(data['indicators']), n_ok, len(state['status'])))


if __name__ == '__main__':
    main()
