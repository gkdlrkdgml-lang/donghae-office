"""점검 스크립트: 키를 넣은 뒤 한 번 실행합니다.

각 API를 동해시 기준으로 한 번씩 불러서
  - 성공/실패, 오류 코드
  - 응답에 들어 있는 항목 이름(영문) 목록
  - 첫 번째 줄 예시
를 화면에 보여주고 probe_결과.txt 로 저장합니다. 이 파일을 Claude에게 보내 주시면 settings.json을 맞춰 드립니다.
(키 값은 파일에 남기지 않습니다.)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (settings, codes, load_env, http_get, parse_body, find_items, check_error, ym_shift, now, ROOT)  # noqa: E402

lines = []


def say(s=''):
    print(s)
    lines.append(s)


def probe(name, src, extra):
    say('=' * 70)
    say('[%s] %s' % (name, src.get('url') or '(주소 없음)'))
    key = os.environ.get(src.get('key_env', ''), '')
    if not key:
        say('  → .env에 %s 가 없습니다' % src.get('key_env'))
        return
    if not src.get('url'):
        say('  → settings.json에 요청 주소가 아직 없습니다')
        return
    params = dict(src.get('params', {}))
    params.update(extra)
    params[src.get('key_param', 'serviceKey')] = key
    if 'numOfRows' in params:
        params['numOfRows'] = '5'
    try:
        text = http_get(src['url'], params, tries=1)
    except Exception as e:  # noqa: BLE001
        say('  → 호출 실패: %s' % e)
        return
    say('  응답 앞부분: ' + text[:300].replace(key, '***').replace('\n', ' '))
    try:
        obj = parse_body(text)
    except Exception as e:  # noqa: BLE001
        say('  → 응답을 읽지 못함: %s' % e)
        return
    err = check_error(obj)
    if err:
        say('  → 오류 코드: %s' % err)
        return
    items = find_items(obj)
    say('  목록 %d건' % len(items))
    if items:
        say('  항목 이름: ' + ', '.join(items[0].keys()))
        say('  첫 줄: ' + json.dumps(items[0], ensure_ascii=False)[:800])


def main():
    load_env()
    S, C = settings(), codes()
    ym = ym_shift('%04d%02d' % (now().year, now().month), -2)
    me = [r for r in C['regions'] if r['name'] == C['me']][0]
    say('점검 시각 %s · 기준월 %s' % (now().strftime('%Y-%m-%d %H:%M'), ym))
    probe('population', S['sources']['population'], {'stdgCd': C['sido']['stdg'], 'srchFrYm': ym, 'srchToYm': ym})
    probe('dong_population', S['sources']['dong_population'], {'stdgCd': me['stdg'], 'srchFrYm': ym, 'srchToYm': ym})
    probe('age_kosis', S['sources']['age']['kosis'], {})
    probe('age_mois', S['sources']['age']['mois'], {})
    probe('finance', S['sources']['finance'], {})
    probe('finance_final', S['sources']['finance_final'], {})
    path = os.path.join(ROOT, 'probe_결과.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('\n저장: %s' % path)


if __name__ == '__main__':
    main()
