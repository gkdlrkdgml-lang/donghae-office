"""자동 갱신 점검: 수집 결과(state.json)를 보고 오래 실패한 자료가 있으면 GitHub 이슈로 알립니다.

- 실패했고 마지막 성공이 2일 넘게 지난 자료 → 「⚠ AI 시장실 자동 갱신 점검」 이슈를 열거나 갱신(저장소 주인에게 메일이 갑니다)
- 모두 정상이면 열린 이슈를 닫습니다.
GH_TOKEN 이 없으면 결과만 출력합니다.
"""
import datetime as dt
import json
import os
import subprocess
import sys

TITLE = '⚠ AI 시장실 자동 갱신 점검'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gh(*a):
    return subprocess.run(['gh'] + list(a), capture_output=True, text=True)


def problems():
    p = os.path.join(ROOT, 'web', 'data', 'state.json')
    if not os.path.exists(p):
        return ['수집 결과 파일이 없습니다(수집이 중간에 멈춤)']
    st = json.load(open(p, encoding='utf-8')).get('status', {})
    now = dt.datetime.now()
    out = []
    for k, v in sorted(st.items()):
        if v.get('ok'):
            continue
        lo = v.get('last_ok')
        try:
            age = (now - dt.datetime.strptime(lo, '%Y-%m-%d %H:%M')).days if lo else 999
        except ValueError:
            age = 999
        if age >= 2:
            out.append('`%s` — 마지막 성공 %s · 오류: %s' % (k, lo or '없음', str(v.get('msg', ''))[:160]))
    return out


def report(items, extra=''):
    body = '\n'.join(['자동 수집에서 2일 넘게 갱신되지 않은 자료가 있습니다. 확인 시각 %s' % dt.datetime.now().strftime('%Y-%m-%d %H:%M'), ''] + ['- ' + x for x in items] + ([extra] if extra else []))
    print(body if items else '자동 갱신 점검: 모두 정상')
    sm = os.environ.get('GITHUB_STEP_SUMMARY')
    if sm:
        open(sm, 'a', encoding='utf-8').write('## 자동 갱신 점검\n\n' + (body if items else '모두 정상') + '\n')
    if not os.environ.get('GH_TOKEN'):
        return
    r = gh('issue', 'list', '--state', 'open', '--search', TITLE + ' in:title', '--json', 'number', '-q', '.[0].number')
    num = r.stdout.strip()
    if items:
        if num:
            gh('issue', 'edit', num, '--body', body)
        else:
            gh('issue', 'create', '--title', TITLE, '--body', body)
    elif num:
        gh('issue', 'close', num, '--comment', '모두 정상으로 돌아와 닫습니다 (%s)' % dt.datetime.now().strftime('%Y-%m-%d %H:%M'))


if __name__ == '__main__':
    if '--stale' in sys.argv:   # 감시: 수집이 오래 안 돌았을 때
        report(['정상 수집이 %s시간째 없습니다. GitHub 예약 실행이 밀린 것으로 보여 감시가 수집을 다시 시작했습니다.' % sys.argv[-1]])
    else:
        report(problems())
