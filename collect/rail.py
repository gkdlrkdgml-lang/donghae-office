"""철도: 기본은 동해시 역(동해·묵호·망상해변·추암), 강원 다른 역도 볼 수 있게.

- 한국철도공사 열차운행정보(B551457/run/v2): 역별 실제 정차 기록(약 3개월 전~어제), 날짜별 열차 계획(출발역·종착역)
- 국토교통부 TAGO 열차정보(1613000/TrainInfo): 오늘 역 출발 시간표(등급·요금)
지난 날짜는 바뀌지 않으므로 받아 둔 날은 건너뛰고, 최근 2일과 빈 날만 다시 받습니다.
"""
import datetime
import json
import os
import time
import urllib.parse

from common import http_get, log, now

RUN = 'https://apis.data.go.kr/B551457/run/v2/'
TAGO = 'https://apis.data.go.kr/1613000/TrainInfo/GetStrtpntAlocFndTrainInfo'
STATIONS = {'동해': 'NAT601485', '묵호': 'NAT601545', '망상해변': 'NAT601602', '추암': 'NAT630064'}
# 오늘 시간표를 찾을 도착역(동해선·강릉선·영동선 방면)
DEST = {'서울': 'NAT010000', '청량리': 'NAT130126', '강릉': 'NAT601936', '정동진': 'NAT601774', '삼척': 'NAT630129',
        '부전': 'NAT750046', '태화강': 'NAT750726', '포항': 'NAT8B0351', '영덕': 'NAT8B0737', '울진': 'NAT752540',
        '태백': 'NAT650978', '영주': 'NAT022188', '제천': 'NAT021549'}
KEEP_DAYS = 92      # 하루 정차 수(역별)는 92일
ROW_DAYS = 30       # 열차별 기록(노선·구간 계산용)은 30일
BUDGET = 420        # 한 번에 7분까지만 받고, 못 받은 날은 다음 실행에서
# 오늘 시간표를 만들 강원 주요 역(동해시 역 + 손님이 많은 역)
TT_EXTRA = ['강릉', '정동진', '삼척', '태백', '원주', '서원주', '만종', '횡성', '둔내', '평창', '진부', '춘천', '남춘천', '영월', '도계', '철암', '고한', '사북', '민둥산']


def _key():
    k = urllib.parse.unquote(os.environ.get('DATA_GO_KR_KEY', '').strip())
    if not k:
        raise RuntimeError('DATA_GO_KR_KEY 없음')
    return k


def _items(t):
    j = json.loads(t)
    bd = (j.get('response') or {}).get('body') or {}
    it = (bd.get('items') or {}).get('item') or [] if isinstance(bd.get('items'), dict) else []
    return (it if isinstance(it, list) else [it]), int(bd.get('totalCount') or 0)


def _hm(s):
    s = str(s or '')
    return s[11:16] if len(s) >= 16 else (s[8:10] + ':' + s[10:12] if len(s) >= 12 else '')


def gw_stations(key, cache):
    if (cache or {}).get('stations'):
        return cache['stations']
    it, _ = _items(http_get('https://apis.data.go.kr/1613000/TrainInfo/GetCtyAcctoTrainSttnList',
                            {'serviceKey': key, '_type': 'json', 'numOfRows': '200', 'pageNo': '1', 'cityCode': '32'}, tries=2, timeout=40))
    return {x['nodename']: x['nodeid'] for x in it if x.get('nodename')}


def collect(cache=None):
    key = _key()
    t0 = time.time()
    cache = cache if (cache or {}).get('v') == 2 else {}
    out = {'v': 2, 'at': now().strftime('%Y-%m-%d %H:%M'), 'days': dict(cache.get('days') or {}), 'cnt': dict(cache.get('cnt') or {}),
           'plan': dict(cache.get('plan') or {}), 'today': cache.get('today') or {}, 'errors': []}
    gw = gw_stations(key, cache)
    out['stations'] = gw
    names = set(gw)
    today = now().date()
    # 1) 지난 날짜 정차 실적: 그날 전국 기록을 받아 강원 역만 남김
    for back in range(1, KEEP_DAYS + 1):
        if time.time() - t0 > BUDGET:
            out['errors'].append('시간 제한 — 남은 날은 다음 실행에서')
            break
        d = (today - datetime.timedelta(days=back)).strftime('%Y%m%d')
        if d in out['cnt'] and back > 2:
            continue
        day, page = {}, 1
        try:
            while True:
                it, tot = _items(http_get(RUN + 'travelerTrainRunInfo2', {'serviceKey': key, 'returnType': 'json', 'numOfRows': '1000', 'pageNo': str(page),
                                                                         'cond[run_ymd::EQ]': d}, tries=2, timeout=60))
                for x in it:
                    st = x.get('stn_nm') or ''
                    if st not in names or str(x.get('stop_se_nm', '')).find('통과') >= 0:
                        continue
                    day.setdefault(st, []).append([str(x.get('trn_no', '')).lstrip('0'), _hm(x.get('trn_arvl_dt')), _hm(x.get('trn_dptre_dt')),
                                                   x.get('mrnt_nm') or '', x.get('uppln_dn_se_cd') or ''])
                if page * 1000 >= tot or not it:
                    break
                page += 1
        except Exception as e:  # noqa: BLE001
            out['errors'].append('%s %s' % (d, str(e)[:120]))
            continue
        if not day:
            continue
        out['cnt'][d] = {st: len(v) for st, v in day.items()}
        if back <= ROW_DAYS:
            out['days'][d] = {st: sorted(v, key=lambda r: r[2] or r[1]) for st, v in day.items()}
            try:
                want = set(r[0] for rows in day.values() for r in rows)
                pl, pg = {}, 1
                while True:
                    it, tot = _items(http_get(RUN + 'travelerTrainRunPlan2', {'serviceKey': key, 'returnType': 'json', 'numOfRows': '1000', 'pageNo': str(pg),
                                                                              'cond[run_ymd::EQ]': d}, tries=2, timeout=60))
                    for x in it:
                        n = str(x.get('trn_no', '')).lstrip('0')
                        if n in want:
                            pl[n] = [x.get('dptre_stn_nm') or '', x.get('arvl_stn_nm') or '']
                    if pg * 1000 >= tot or not it or not (want - set(pl)):
                        break
                    pg += 1
                out['plan'][d] = pl
            except Exception as e:  # noqa: BLE001
                out['errors'].append('plan %s %s' % (d, str(e)[:120]))
    c1 = (today - datetime.timedelta(days=KEEP_DAYS + 1)).strftime('%Y%m%d')
    c2 = (today - datetime.timedelta(days=ROW_DAYS + 1)).strftime('%Y%m%d')
    out['cnt'] = {k: v for k, v in sorted(out['cnt'].items()) if k >= c1}
    out['days'] = {k: v for k, v in sorted(out['days'].items()) if k >= c2}
    out['plan'] = {k: v for k, v in out['plan'].items() if k >= c2}
    # 2) 오늘 시간표(TAGO): 하루 한 번, 동해시 역 + 강원 주요 역
    td = today.strftime('%Y%m%d')
    if out['today'].get('date') != td or not out['today'].get('dep'):
        dep = {}
        for st in list(STATIONS) + [x for x in TT_EXTRA if x in gw]:
            sid = gw.get(st) or STATIONS.get(st)
            trains = {}
            for dn, did in DEST.items():
                if dn == st:
                    continue
                try:
                    it, _ = _items(http_get(TAGO, {'serviceKey': key, '_type': 'json', 'numOfRows': '100', 'pageNo': '1',
                                                   'depPlaceId': sid, 'arrPlaceId': did, 'depPlandTime': td}, tries=2, timeout=40))
                except Exception as e:  # noqa: BLE001
                    out['errors'].append('tago %s→%s %s' % (st, dn, str(e)[:80]))
                    continue
                for x in it:
                    n = str(x.get('trainno', '')).lstrip('0')
                    t = str(x.get('depplandtime', ''))
                    if not n or len(t) < 12:
                        continue
                    r = trains.setdefault(n, {'no': n, 'grade': x.get('traingradename') or '', 'dep': t[8:10] + ':' + t[10:12], 'to': [], 'fare': x.get('adultcharge')})
                    r['to'].append([dn, str(x.get('arrplandtime', ''))[8:12]])
            if trains:
                dep[st] = sorted(trains.values(), key=lambda r: r['dep'])
        if dep:
            out['today'] = {'date': td, 'dep': dep}
    if not out['cnt'] and not (out['today'] or {}).get('dep'):
        raise RuntimeError('열차 자료를 받지 못함: %s' % out['errors'][:3])
    out['errors'] = out['errors'][:8]
    return out
