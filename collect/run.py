"""매일 실행: 수집 → 지표 계산 → 순위 → web/data/data.js 저장.

한 원천이 실패해도 나머지는 계속 진행하고, 실패한 지표는 '지난번 값'을 그대로 둡니다.
사용법:  python collect/run.py          (실제 수집)
        python collect/run.py --demo   (키 없이 시연용 가짜 값으로 화면 확인)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (settings, codes, load_env, save_json, load_json, log, now, read_manual, WEB_DATA)  # noqa: E402
import sources  # noqa: E402
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
                                'prev_m_hh': pop.get('prev_m', {}).get(k, {}).get('hh')} for k, v in pop['cur'].items()},
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
        ok(state, 'age', '%s · %d개 시·군' % (mode, len(ages)))
        if mode == 'kosis' and state.get('admin'):
            try:
                admm, aym = sources.admm_kosis(S, C)
                state['admin']['admm'] = admm
                state['admin']['admm_ym'] = aym
            except Exception as e2:  # noqa: BLE001
                state['admin'].pop('admm', None)
                print('행정동 인구 실패:', e2)
    except Exception as e:  # noqa: BLE001
        fail(state, 'age', e)
        for iid in ('working_age', 'elderly'):
            man, mb = read_manual(iid)
            if man:
                set_ind(state, iid, man, mb or '수기 입력', 'manual')

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
             '발한동': [3900, 2100], '묵호동': [6800, 3500], '북평동': [7300, 3400], '망상동': [2400, 1300], '삼화동': [4100, 2000],
             '동해시 기타': [18600, 8700]}
    state['admin'] = {'ym': now().strftime('%Y%m'), 'prev_ym': '', 'regions': regions,
                      'dongs': {k: {'total': v[0], 'hh': v[1]} for k, v in dongs.items()},
                      'age_bands': {'0': 5300, '10': 6900, '20': 8700, '30': 8600, '40': 12100, '50': 15300, '60': 15100, '70': 9300, '80': 5300, '90': 900, '100': 30},
                      'age_counts': {'total': 88030, 'working': 54740, 'elderly': 25430},
                      'admm': {k: {'total': v[0], 'elderly': v[1]} for k, v in {'천곡동': [21300, 22.1], '송정동': [9000, 26.0], '북삼동': [16800, 19.5], '부곡동': [5100, 30.2], '동호동': [4600, 33.1], '발한동': [6900, 31.4], '묵호동': [3900, 41.2], '북평동': [6100, 32.5], '망상동': [3300, 38.9], '삼화동': [6400, 27.3]}.items()}}
    for s in ('population', 'dong_population', 'age', 'finance', 'finance_final'):
        ok(state, s, '시연용 가짜 값')


def build(state, S, C):
    out = {
        'generated_at': now().strftime('%Y-%m-%d %H:%M'),
        'demo': any(v.get('from') == 'demo' for v in state['indicators'].values()),
        'title': S['title'], 'me': C['me'], 'menu': [m for m in S['menu'] if m.get('show', True)],
        'frame': S.get('frame', {}), 'judge': S['judge'],
        'regions': [r['name'] for r in C['regions']],
        'indicators': [], 'admin': state.get('admin'), 'status': state['status'],
        'finance': state.get('finance') or {},
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
    out['menu'] = [m for m in out['menu'] if not (m['id'] == 'finance' and not has_fin) and not (m['id'] == 'admin' and not out['admin'])]
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
        collect(state, S, C)
    save_json(STATE, state)
    data = build(state, S, C)
    os.makedirs(WEB_DATA, exist_ok=True)
    with open(os.path.join(WEB_DATA, 'data.js'), 'w', encoding='utf-8') as f:
        f.write('window.DONGHAE_DATA = ' + json.dumps(data, ensure_ascii=False) + ';\n')
    n_ok = sum(1 for v in state['status'].values() if v['ok'])
    log('완료 · 지표 %d개 표시 · 원천 %d/%d 성공' % (len(data['indicators']), n_ok, len(state['status'])))


if __name__ == '__main__':
    main()
