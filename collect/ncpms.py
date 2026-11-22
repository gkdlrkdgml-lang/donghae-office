"""농촌진흥청 국가농작물병해충관리시스템(NCPMS) — 병해충 예찰·예측 경보.

동해시는 예찰 조사 지역이 아님(2026-11 확인) → 강원 영동 이웃 시·군(강릉·삼척) 예찰 값 + 전국 병해충 예측 모델 경보.
화면에는 「동해시 자료 아님」을 밝힘. 키: GitHub Secret NCPMS_KEY.
"""
import html
import json
import os
import urllib.parse
import urllib.request

from common import now

URL = 'https://ncpms.rda.go.kr/npmsAPI/service'
GW = 42                                      # NCPMS 시도 코드: 강원특별자치도
NEAR = {'4215': '강릉시', '4223': '삼척시'}   # 동해 이웃(영동)
CROPS = (('FC010101', '논벼'), ('VC011205', '고추'), ('VC021001', '배추'), ('VC031101', '무'), ('FT010601', '사과'), ('FC030301', '콩'))


def _dec(x):
    return ' '.join(html.unescape(urllib.parse.unquote(str(x or ''))).split())


def call(**p):
    key = urllib.parse.quote(os.environ.get('NCPMS_KEY', '').strip(), safe='')
    if not key:
        raise RuntimeError('NCPMS_KEY 없음')
    u = URL + '?apiKey=' + key + '&' + urllib.parse.urlencode(dict({'serviceType': 'AA003'}, **p))
    t = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'donghae-office-collector/1.0'}), timeout=60).read().decode('utf-8', 'replace')
    s = json.loads(t).get('service') or {}
    if s.get('errorCode'):
        raise RuntimeError('%s %s' % (s.get('errorCode'), _dec(s.get('errorMsg'))[:80]))
    return s


def alerts():
    """SVC31 전국 병해충 예측 모델: 작물·병해충·위험 단계(1이 가장 높음)·안내."""
    s = call(serviceCode='SVC31', proxyUrl='http://localhost', div_id='r')
    out = []
    for m in s.get('pestModelByKncrList') or []:
        try:
            lv = int(m.get('validAlarmRiskIdex'))
        except Exception:  # noqa: BLE001
            continue
        segs = [x.split('!+@+!') for x in str(m.get('pestConfigStr') or '').split('|')]
        msg, col = '', ''
        for sg in segs:
            if len(sg) >= 3 and sg[0].strip() and str(lv) in sg[0] or (len(sg) >= 3 and not msg and sg[1].strip()):
                msg, col = _dec(sg[1]), sg[2].strip()
        out.append({'crop': _dec(m.get('kncrNm')), 'pest': _dec(m.get('dbyhsMdlNm')), 'lv': lv, 'msg': msg[:120], 'col': col, 'at': str(m.get('nowDrveDatetm') or '')})
    out.sort(key=lambda x: (x['lv'], x['crop']))
    return out


def survey():
    """작물마다 가장 최근 예찰 회차 → 강원 시·군 값(강릉·삼척 표시, 강원 전체 개수)."""
    out = []
    for code, nm in CROPS:
        try:
            L = call(serviceCode='SVC51', searchKncrCode=code, displayCount=5, startPoint=1).get('list') or []
            if not L:
                continue
            r = L[0]
            rows = call(serviceCode='SVC53', insectKey=r['insectKey'], sidoCode=GW).get('structList') or []
            sites, allg = {}, set()
            for x in rows:
                sg = str(x.get('sigunguCode'))
                if x.get('inqireValue') is None or sg == '9999':
                    continue
                allg.add(_dec(x.get('sigunguNm')))
                if sg in NEAR:
                    sites.setdefault(NEAR[sg], {})[_dec(x.get('dbyhsNm'))] = x.get('inqireValue')
            out.append({'crop': nm, 'code': code, 'kind': _dec(r.get('examinSpchcknNm')), 'year': r.get('examinYear'), 'round': r.get('examinTmrd'),
                        'date': str(r.get('inputStdrDatetm') or ''), 'sites': sites, 'gw_sites': sorted(allg)})
        except Exception as e:  # noqa: BLE001
            out.append({'crop': nm, 'code': code, 'error': str(e)[:150]})
    return out


def collect():
    return {'at': now().strftime('%Y-%m-%d %H:%M'), 'alerts': alerts(), 'survey': survey(), 'near': list(NEAR.values())}
