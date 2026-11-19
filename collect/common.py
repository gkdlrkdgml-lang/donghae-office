"""공통 도구: 설정 읽기, API 호출, 응답에서 목록 꺼내기, 저장, 기록.

외부 패키지 없이 파이썬 기본 기능만 씁니다(미니PC에 설치할 것이 파이썬 하나뿐이도록).
"""
import csv
import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, 'config')
MANUAL = os.path.join(ROOT, 'manual')
RAW = os.path.join(ROOT, 'raw')
LOGS = os.path.join(ROOT, 'logs')
WEB_DATA = os.path.join(ROOT, 'web', 'data')

KST = dt.timezone(dt.timedelta(hours=9))


def now():
    return dt.datetime.now(KST)


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def settings():
    return load_json(os.path.join(CONFIG, 'settings.json'))


def codes():
    return load_json(os.path.join(CONFIG, 'codes.json'))


def load_env():
    """ROOT/.env 의 KEY=VALUE 줄을 환경변수로 읽습니다. 키는 이 파일에만 둡니다."""
    path = os.path.join(ROOT, '.env')
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def log(msg):
    os.makedirs(LOGS, exist_ok=True)
    line = '[%s] %s' % (now().strftime('%Y-%m-%d %H:%M:%S'), msg)
    print(line)
    with open(os.path.join(LOGS, now().strftime('%Y-%m') + '.log'), 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def http_get(url, params, tries=3, timeout=30):
    """GET 호출. 실패하면 5초, 15초 쉬고 다시 시도합니다. 응답 본문(문자열)을 돌려줍니다."""
    # serviceKey는 포털에서 받은 '디코딩' 키를 넣고 여기서 한 번만 인코딩합니다.
    q = urllib.parse.urlencode(params, safe='')
    full = url + ('&' if '?' in url else '?') + q
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(full, headers={'User-Agent': 'donghae-office/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            for enc in ('utf-8', 'euc-kr'):
                try:
                    return body.decode(enc)
                except UnicodeDecodeError:
                    pass
            return body.decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001 - 어떤 오류든 다시 시도
            last = e
            time.sleep([5, 15, 30][min(i, 2)])
    raise RuntimeError('호출 실패: %s (%s)' % (url, last))


def parse_body(text):
    """JSON이면 JSON으로, 아니면 XML을 dict로 바꿉니다."""
    t = text.strip()
    if t.startswith('{') or t.startswith('['):
        return json.loads(t)
    root = ET.fromstring(t)

    def conv(el):
        kids = list(el)
        if not kids:
            return (el.text or '').strip()
        out = {}
        for k in kids:
            v = conv(k)
            if k.tag in out:
                if not isinstance(out[k.tag], list):
                    out[k.tag] = [out[k.tag]]
                out[k.tag].append(v)
            else:
                out[k.tag] = v
        return out
    return {root.tag: conv(root)}


def find_items(obj):
    """응답 안에서 가장 긴 '딕셔너리 목록'을 찾아 돌려줍니다. 기관마다 감싸는 모양이 달라서 이렇게 찾습니다."""
    best = []

    def walk(o):
        nonlocal best
        if isinstance(o, list):
            if o and all(isinstance(x, dict) for x in o) and len(o) > len(best):
                best = o
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            # item 이 딕셔너리 하나로만 온 경우(결과 1건)
            if 'item' in o and isinstance(o['item'], dict) and not best:
                best = [o['item']]
            for v in o.values():
                walk(v)
    walk(obj)
    return best


def check_error(obj):
    """공공데이터포털 오류 응답이면 메시지를 돌려줍니다."""
    s = json.dumps(obj, ensure_ascii=False)
    for key in ('SERVICE_KEY_IS_NOT_REGISTERED_ERROR', 'SERVICE_ACCESS_DENIED_ERROR', 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR',
                'SERVICE_KEY_IS_NULL', 'DEADLINE_HAS_EXPIRED_ERROR', 'INVALID_REQUEST_PARAMETER_ERROR', 'NO_OPENAPI_SERVICE_ERROR',
                'PERMISSION_DENIED', 'APPLICATION_ERROR'):
        if key in s:
            return key
    return None


def pick(row, candidates):
    """후보 이름 중 응답에 있는 첫 번째 값을 돌려줍니다."""
    for c in candidates:
        if c in row and row[c] not in (None, ''):
            return row[c]
    return None


def to_num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(',', '').replace('%', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def match_region(text, regions):
    """'강원특별자치도 동해시', '동해시', '동해' 같은 글자에서 18개 시·군 중 하나를 찾습니다."""
    if not text:
        return None
    t = str(text)
    for r in regions:
        if r['full'] in t:
            return r['name']
    for r in regions:
        if t.strip() == r['name']:
            return r['name']
    return None


def read_manual(name):
    """manual/<name>.csv (시군,값) 이 있으면 {시군: 값} 으로 돌려줍니다. API가 안 될 때 사람이 넣는 값입니다."""
    path = os.path.join(MANUAL, name + '.csv')
    if not os.path.exists(path):
        return None, None
    out = {}
    basis = None
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.reader(f):
            if not row or row[0].startswith('#'):
                if row and row[0].startswith('#기준'):
                    basis = row[0].split(':', 1)[-1].strip()
                continue
            if row[0] in ('시군', '시·군'):
                continue
            v = to_num(row[1]) if len(row) > 1 else None
            if v is not None:
                out[row[0].replace('시', '').replace('군', '') if len(row[0]) > 2 else row[0]] = v
    return out, basis


def save_raw(name, text):
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, '%s_%s.txt' % (name, now().strftime('%Y%m%d_%H%M')))
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def ym_shift(ym, months):
    y, m = int(ym[:4]), int(ym[4:])
    m += months
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return '%04d%02d' % (y, m)
