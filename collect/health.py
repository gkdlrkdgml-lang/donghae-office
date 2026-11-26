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


DIGEST = '📬 대시보드 매일 아침 갱신 소식'
SKIP = {'weather', 'air', 'cnctr', 'wq', 'wx_year', 'air_year', 'bus', 'parking', 'ev', 'taxi', 'events', 'festivals', 'places', 'licenses'}   # 실시간·매일 조금씩 바뀌는 것은 뺌
NAME = {'population': '인구 현황', 'vital': '출생·사망 신고', 'youth': '청년·고령 인구', 'migration': '전입·전출', 'dong_population': '행정동 인구', 'age': '연령별 인구',
        'stores': '상가 신규·폐업', 'cars': '자동차 등록', 'power': '전력 사용', 'demand': '전력 수요', 'tasis': '교통 통계', 'employ': '고용', 'economy': '지역 경제(GRDP)',
        'eco_ind': '경제 지표', 'finance': '예산', 'finance_final': '결산', 'bokjiro': '복지 서비스', 'social': '복지 시설·수급', 'visitors': '관광 방문자', 'attr': '관광지 방문',
        'water': '상하수도 통계', 'ordin': '조례', 'hospitals': '의료기관', 'tsafe': '교통안전', 'death': '사망 분석', 'apt': '아파트 거래', 'port': '항만', 'rail': '철도',
        'waterq': '수돗물 수질검사', 'waterfee': '상하수도 요금'}


def digest():
    p = '/tmp/digest.json'
    if not os.path.exists(p):
        return
    d = json.load(open(p, encoding='utf-8'))
    items = [x for x in d['items'] if x[0] not in SKIP]
    lines = ['- **%s**: %s → %s' % (NAME.get(k, k), a or '-', b) for k, a, b in items]
    body = '### %s 아침 · 대시보드에서 바뀐 자료\n\n' % d['date'] + ('\n'.join(lines) if lines else '어제 아침 이후 새로 바뀐 자료는 없습니다.') + \
        '\n\n<sub>날씨·대기·주차 등 실시간 항목은 뺐습니다 · https://gkdlrkdgml-lang.github.io/donghae-office/</sub>'
    print(body)
    try:   # 카카오톡 나에게 보내기(설정돼 있으면)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kakao
        d8 = d['date'][5:].replace('-', '/')
        kt = '📬 %s 대시보드 갱신\n' % d8 + ('\n'.join('· %s → %s' % (NAME.get(k, k), b) for k, a, b in items) if items else '어제 이후 바뀐 자료 없음')
        if kakao.send(kt):
            print('카카오 보냄')
    except Exception as e:  # noqa: BLE001
        print('카카오 실패: %s' % e)
    if not os.environ.get('GH_TOKEN'):
        return
    num = gh('issue', 'list', '--state', 'open', '--search', DIGEST + ' in:title', '--json', 'number', '-q', '.[0].number').stdout.strip()
    if not num:
        r = gh('issue', 'create', '--title', DIGEST, '--body', '매일 아침 첫 수집이 끝나면, 대시보드에서 새 기간·값으로 바뀐 자료만 이 이슈에 댓글로 남깁니다. 이 이슈를 닫지 마세요.')
        num = r.stdout.strip().rsplit('/', 1)[-1]
    gh('issue', 'comment', num, '--body', body)


if __name__ == '__main__':
    digest()
    if '--stale' in sys.argv:   # 감시: 수집이 오래 안 돌았을 때
        report(['정상 수집이 %s시간째 없습니다. GitHub 예약 실행이 밀린 것으로 보여 감시가 수집을 다시 시작했습니다.' % sys.argv[-1]])
    else:
        report(problems())
