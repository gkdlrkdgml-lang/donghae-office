"""카카오톡 「나에게 보내기」 알림.

비밀값: GitHub Secrets KAKAO_REST_KEY(REST API 키), KAKAO_CLIENT_SECRET(쓰는 경우만).
리프레시 토큰은 Supabase 비공개 저장소 dash/cache/kakao.json 에만 두고, 갱신될 때마다 다시 저장합니다(화면·로그에 안 찍음).

python collect/kakao.py setup <인증코드>   # 처음 한 번: 코드로 토큰 받고 시험 메시지 보냄
"""
import json
import os
import sys
import urllib.parse
import urllib.request

import store

REDIRECT = 'https://gkdlrkdgml-lang.github.io/donghae-office/kakao.html'
SITE = 'https://gkdlrkdgml-lang.github.io/donghae-office/'
PATH = 'cache/kakao.json'


def _post(url, data, token=None):
    h = {'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'}
    if token:
        h['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError('카카오 %s %s' % (e.code, e.read()[:200].decode('utf-8', 'ignore')))


def _base():
    d = {'client_id': os.environ['KAKAO_REST_KEY'].strip()}
    if os.environ.get('KAKAO_CLIENT_SECRET', '').strip():
        d['client_secret'] = os.environ['KAKAO_CLIENT_SECRET'].strip()
    return d


def _save(rt):
    store.put(PATH, json.dumps({'refresh_token': rt}).encode(), 'application/json')


def access():
    raw = store.get(PATH)
    if not raw:
        raise RuntimeError('카카오 토큰 없음(처음 설정 필요)')
    rt = json.loads(raw)['refresh_token']
    j = _post('https://kauth.kakao.com/oauth/token', dict(_base(), grant_type='refresh_token', refresh_token=rt))
    if j.get('refresh_token'):   # 만료 1달 전부터 새 토큰이 옴 → 바로 저장
        _save(j['refresh_token'])
    return j['access_token']


def send(text, tok=None):
    if not os.environ.get('KAKAO_REST_KEY', '').strip():
        return False
    if len(text) > 195:
        text = text[:192] + '…'
    tpl = {'object_type': 'text', 'text': text, 'link': {'web_url': SITE, 'mobile_web_url': SITE}, 'button_title': '대시보드 열기'}
    _post('https://kapi.kakao.com/v2/api/talk/memo/default/send', {'template_object': json.dumps(tpl, ensure_ascii=False)}, tok or access())
    return True


if __name__ == '__main__' and len(sys.argv) > 2 and sys.argv[1] == 'setup':
    j = _post('https://kauth.kakao.com/oauth/token', dict(_base(), grant_type='authorization_code', redirect_uri=REDIRECT, code=sys.argv[2].strip()))
    _save(j['refresh_token'])
    send('✅ 동해시 AI 시장실 알림이 연결됐습니다.\n매일 아침 대시보드에서 바뀐 자료만 여기로 보내 드립니다.', j['access_token'])
    print('카카오 연결 완료 · 시험 메시지 보냄')
