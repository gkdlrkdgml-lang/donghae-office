"""3D 지도 바닥 그림을 미리 받아 web/img/tiles/ 에 둡니다(보는 PC가 외부 지도 서버에 못 붙어도 나오도록).

한 번 받아 두면 다시 받지 않습니다. 지도 © OpenStreetMap · © CARTO / © 국토교통부 브이월드.
"""
import json, math, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'web', 'img', 'tiles')
Z = 13
BOXES = [(37.452, 37.600, 129.000, 129.160), (37.455, 37.600, 129.000, 129.170)]


def px(lat, lng):
    n = 2 ** Z * 256
    r = math.radians(lat)
    return (lng + 180) / 360 * n, (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n


def tiles():
    out = set()
    for la0, la1, lo0, lo1 in BOXES:
        tl, br = px(la1, lo0), px(la0, lo1)
        for x in range(int(tl[0] // 256), int(br[0] // 256) + 1):
            for y in range(int(tl[1] // 256), int(br[1] // 256) + 1):
                out.add((x, y))
    return sorted(out)


def get(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 500:
        return True
    try:
        rq = urllib.request.Request(url, headers={'User-Agent': 'donghae-office/1.0', 'Referer': 'https://gkdlrkdgml-lang.github.io/'})
        with urllib.request.urlopen(rq, timeout=30) as r:
            b = r.read()
        if len(b) < 500:
            return False
        with open(path, 'wb') as f:
            f.write(b)
        time.sleep(0.2)
        return True
    except Exception as e:  # noqa: BLE001
        print('지도 그림 실패', url.split('/req/')[0][:40], e)
        return False


def main():
    os.makedirs(OUT, exist_ok=True)
    s = json.load(open(os.path.join(ROOT, 'config', 'settings.json'), encoding='utf-8'))
    key = (s.get('map') or {}).get('vworld_key', '')
    ok = {'carto': 0, 'sat': 0}
    for x, y in tiles():
        if get('https://a.basemaps.cartocdn.com/rastertiles/voyager/%d/%d/%d@2x.png' % (Z, x, y), os.path.join(OUT, 'c_%d_%d_%d.png' % (Z, x, y))):
            ok['carto'] += 1
        if key and get('https://api.vworld.kr/req/wmts/1.0.0/%s/Satellite/%d/%d/%d.jpeg' % (key, Z, y, x), os.path.join(OUT, 's_%d_%d_%d.jpg' % (Z, x, y))):
            ok['sat'] += 1
    print('지도 그림', ok, '/', len(tiles()))


if __name__ == '__main__':
    main()
