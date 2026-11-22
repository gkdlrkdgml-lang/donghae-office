"""Supabase 비공개 저장소(dash) ↔ 수집기.

전체 잠금 이후 수집 자료는 GitHub(공개)에 올리지 않고 Supabase 비공개 저장소에만 둡니다.
- cache/state.json, cache/stores_snap.json : 수집 캐시(서버만 읽음)
- data/data.json.gz, data/version.txt       : 화면 자료(로그인한 승인 계정만 읽음)

python collect/store.py pull        # 수집 전: 캐시 내려받기(없으면 저장소에 남은 파일 그대로)
python collect/store.py push        # 수집 후: 캐시·화면 자료 올리기
python collect/store.py push-cache  # 캐시만 올리기
"""
import gzip
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'web', 'data')
BUCKET = 'dash'
CACHE = ['state.json', 'stores_snap.json']


def _url():
    t = open(os.path.join(ROOT, 'web', 'admin-config.js'), encoding='utf-8').read()
    return re.search(r"url:\s*'([^']+)'", t).group(1).rstrip('/')


def _headers(extra=None):
    key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
    if not key:
        raise RuntimeError('SUPABASE_SERVICE_KEY 없음')
    h = {'apikey': key, 'User-Agent': 'donghae-office-collector/1.0'}
    if not key.startswith('sb_'):
        h['Authorization'] = 'Bearer ' + key
    h.update(extra or {})
    return h


def get(path):
    req = urllib.request.Request('%s/storage/v1/object/%s/%s' % (_url(), BUCKET, path), headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return None
        raise RuntimeError('내려받기 %s → %s %s' % (path, e.code, e.read()[:200]))


def put(path, body, ctype):
    req = urllib.request.Request('%s/storage/v1/object/%s/%s' % (_url(), BUCKET, path), data=body, method='POST',
                                 headers=_headers({'Content-Type': ctype, 'x-upsert': 'true', 'Cache-Control': 'no-cache'}))
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError('올리기 %s → %s %s' % (path, e.code, e.read()[:300]))


def pull():
    os.makedirs(DATA, exist_ok=True)
    for f in CACHE:
        b = get('cache/' + f + '.gz')
        if b:
            open(os.path.join(DATA, f), 'wb').write(gzip.decompress(b))
            print('캐시 받음', f, len(b))
        else:
            print('캐시 없음(저장소 파일 사용)', f, os.path.exists(os.path.join(DATA, f)))


def push_cache():
    for f in CACHE:
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            put('cache/' + f + '.gz', gzip.compress(open(p, 'rb').read(), 6), 'application/gzip')
            print('캐시 올림', f)


def push_data():
    p = os.path.join(DATA, 'data.js')
    t = open(p, encoding='utf-8').read()
    j = t[t.index('=') + 1:].rstrip().rstrip(';')
    json.loads(j)   # 깨진 자료는 올리지 않음
    put('data/data.json.gz', gzip.compress(j.encode('utf-8'), 9), 'application/gzip')
    ver = json.loads(j).get('generated_at', '')
    put('data/version.txt', ver.encode('utf-8'), 'text/plain')
    print('화면 자료 올림', len(j), ver)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'pull':
        pull()
    elif cmd == 'push':
        push_cache()
        push_data()
    elif cmd == 'push-cache':
        push_cache()
    else:
        print(__doc__)
