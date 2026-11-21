"""관리자 입력(Supabase) → manual/admin_input.json.

관리자 화면(web/admin.html)에서 로그인한 관리자가 넣은 값은 Supabase 'entries' 표에 쌓입니다.
여기서는 그 값을 받아 기준일별 최신 값으로 묶어, 예전과 같은 admin_input.json 형식으로 저장합니다.
(run.py의 apply_admin_input()이 이 파일을 읽어 화면에 반영)

필요한 것: GitHub Secret SUPABASE_SERVICE_KEY (Supabase → Project Settings → API Keys 의 service_role/secret 키)
          주소(url)는 web/admin-config.js 에서 읽습니다.

python collect/admin_sync.py --check   → 바뀐 게 있으면 'changed', 없으면 'same' 출력(10분마다 도는 감시용)
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'manual', 'admin_input.json')
STATE = os.path.join(ROOT, 'web', 'data', 'state.json')


def _url():
    try:
        t = open(os.path.join(ROOT, 'web', 'admin-config.js'), encoding='utf-8').read()
        m = re.search(r"url:\s*'([^']+)'", t)
        return m.group(1).rstrip('/') if m else ''
    except OSError:
        return ''


def fetch():
    url, key = _url(), os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
    if not url or not key:
        return None   # 아직 연결 안 함 → 예전 파일 그대로 사용
    q = url + '/rest/v1/entries?select=id,ref_date,section,data,author_name,created_at&deleted=eq.false&order=created_at.desc&limit=5000'
    req = urllib.request.Request(q, headers={'apikey': key, 'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def signature(rows):
    ids = sorted(r['id'] for r in rows)
    return hashlib.sha1(json.dumps(ids).encode()).hexdigest()[:16]


def to_entries(rows):
    by = {}
    for r in rows:   # 최신 것부터 옴 → 기준일·분야마다 처음 나온 값이 최신
        d = by.setdefault(r['ref_date'], {'date': r['ref_date']})
        if r['section'] not in d:
            d[r['section']] = r['data']
            d.setdefault('saved_at', r['created_at'][:16].replace('T', ' '))
            d.setdefault('by', r.get('author_name') or '')
    return [by[k] for k in sorted(by)]


def pull():
    """run.py에서 부름. 성공하면 서명(signature)을, 연결 전이면 None을 돌려줌."""
    rows = fetch()
    if rows is None:
        return None
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'entries': to_entries(rows), 'source': 'supabase'}, f, ensure_ascii=False, indent=1)
    return signature(rows)


if __name__ == '__main__':
    if '--check' in sys.argv:
        rows = fetch()
        if rows is None:
            print('same')
            sys.exit(0)
        try:
            old = (json.load(open(STATE, encoding='utf-8')) or {}).get('admin_sig')
        except Exception:  # noqa: BLE001
            old = None
        print('changed' if signature(rows) != old else 'same')
