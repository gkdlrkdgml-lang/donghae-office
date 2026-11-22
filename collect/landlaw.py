"""도시계획 조례: 강원 18개 시·군의 용도지역별 건폐율·용적률을 조례 원문에서 뽑습니다.

국가법령정보 공동활용 OPEN API (GitHub Secret LAW_OC)
- 검색: lawSearch.do?target=ordin  → 시·군 「○○시 도시계획 조례」/「○○군 군계획 조례」
- 본문: lawService.do?target=ordin&MST=…  → 조문 중 「용도지역안에서의 건폐율」「용도지역안에서의 용적률」
조례 조회 방식 참고: chrisryugj/korean-law-mcp (MIT License)
"""
import json
import os
import re
import time

from common import http_get, log, now

SEARCH = 'https://www.law.go.kr/DRF/lawSearch.do'
SERVICE = 'https://www.law.go.kr/DRF/lawService.do'
ITEM = re.compile(r'\d+\.\s*((?:제\d종)?[가-힣ㆍ·\s]+?지역)\s*:\s*([\d,]+(?:\.\d+)?)\s*퍼센트')


def _get(url, prm):
    oc = os.environ.get('LAW_OC', '').strip()
    if not oc:
        raise RuntimeError('LAW_OC 없음')
    q = dict(prm, OC=oc, type='JSON')
    t = http_get(url, q, tries=3, timeout=60)
    return json.loads(t)


def _as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def find_ordinance(full):
    """「동해시 도시계획 조례」 같은 시·군 본 조례를 찾습니다(특별회계·위원회 조례 제외)."""
    for q in ('%s 도시계획 조례' % full, '%s 군계획 조례' % full, '%s 계획 조례' % full):
        j = _get(SEARCH, {'target': 'ordin', 'query': q, 'display': '20'})
        for it in _as_list((j.get('OrdinSearch') or {}).get('law')):
            nm, org = it.get('자치법규명', ''), it.get('지자체기관명', '')
            if not org.endswith(full) or it.get('자치법규종류') != '조례':
                continue
            if re.fullmatch(r'%s\s*(도시|군)?계획\s*조례' % re.escape(full), nm):
                return it
        time.sleep(0.5)
    return None


def _zones(text):
    out = {}
    for z, v in ITEM.findall(text):
        z = re.sub(r'\s+', '', z)
        out.setdefault(z, float(v.replace(',', '')))
    return out


def parse(svc):
    """조례 본문에서 용도지역별 건폐율·용적률과 근거 조문을 뽑습니다."""
    L = svc.get('LawService') or {}
    info = L.get('자치법규기본정보') or {}
    arts = _as_list((L.get('조문') or {}).get('조'))
    res = {'name': info.get('자치법규명'), 'mst': info.get('자치법규일련번호'), 'date': info.get('시행일자'),
           'no': info.get('공포번호'), 'dept': info.get('담당부서명'), 'bcr': {}, 'far': {}}
    for a in arts:
        title, body = a.get('조제목') or '', a.get('조내용') or ''
        if a.get('조문여부') != 'Y':
            continue
        key = None
        if '용도지역' in title and '건폐율' in title and not re.search(r'완화|강화|지구단위', title):
            key = 'bcr'
        elif '용도지역' in title and '용적률' in title and not re.search(r'완화|강화|지구단위', title):
            key = 'far'
        if key and not res[key]:
            res[key] = _zones(body)
            m = re.match(r'(제\d+조(?:의\d+)?)', body)
            res[key + '_art'] = {'no': m.group(1) if m else '', 'title': title, 'text': body[:3000]}
    # 동해시 조례의 다른 건폐율·용적률 관련 조문(경관지구·완화 등)과 별표(용도지역별 건축 가능 건축물)
    res['related'] = [{'title': a.get('조제목'), 'text': (a.get('조내용') or '')[:2500]} for a in arts
                      if a.get('조문여부') == 'Y' and re.search(r'건폐율|용적률|높이|경관지구|건축할 수', a.get('조제목') or '')
                      and (a.get('조제목') or '') not in ((res.get('bcr_art') or {}).get('title'), (res.get('far_art') or {}).get('title'))][:20]
    res['annex'] = [{'title': b.get('별표제목'), 'url': (b.get('별표첨부파일명') or '').replace('http://', 'https://')}
                    for b in _as_list((L.get('별표') or {}).get('별표단위'))][:40]
    return res


HO = re.compile(r'별표\s*(?:1\s*)?제(\d+)호(의\d+)?')
ITEM_RE = re.compile(r'^([가-힣])\s*[.,]\s*(.+)$')


def parse_uses(md, title):
    """kordoc 마크다운 → {zone, kind(can/cannot), note, items:[{t, subs, ho}]}"""
    m = re.search(r'\]\s*(.+?)\s*안에서\s*건축할\s*수\s*(있는|없는)', title or '')
    if not m:
        return None
    out = {'zone': re.sub(r'\s+', '', m.group(1)), 'kind': 'can' if m.group(2) == '있는' else 'cannot',
           'title': re.sub(r'\s*<.*$', '', title).strip(), 'note': '', 'items': []}
    for ln in md.split('\n'):
        ln = re.sub(r'\*\*', '', ln).strip()
        if not ln or ln.startswith('#'):
            continue
        if ln.startswith('※'):
            out['note'] = ln.lstrip('※ ').strip()
            continue
        mi = ITEM_RE.match(ln)
        if mi and len(ln) > 6:
            t = mi.group(2).strip()
            out['items'].append({'k': mi.group(1), 't': t, 'subs': [],
                                 'ho': sorted(set(a + (b or '') for a, b in HO.findall(t)))})
        elif re.match(r'^\(\d+\)', ln) and out['items']:
            out['items'][-1]['subs'].append(ln)
        elif out['items'] and not re.match(r'^[\[■]', ln):
            it = out['items'][-1]                    # 앞 줄에 이어지는 글(줄바꿈된 조문)
            if it['subs']:
                it['subs'][-1] += ' ' + ln
            else:
                it['t'] += ' ' + ln
    return out


def fetch_uses(annex):
    import urllib.request
    import hwp
    res = []
    for a in annex:
        if '건축할 수' not in (a.get('title') or '') or not a.get('url'):
            continue
        d = urllib.request.urlopen(urllib.request.Request(a['url'], headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()
        u = parse_uses(hwp.hwp_text(d), a['title'])
        if u and u['items']:
            u['url'] = a['url']
            res.append(u)
        time.sleep(0.3)
    return res


def collect(C, prev=None):
    prev = prev or {}
    regs, errs = {}, []
    for r in C['regions']:
        try:
            it = find_ordinance(r['full'])
            if not it:
                errs.append('%s 조례 못 찾음' % r['name'])
                continue
            mst = it.get('자치법규일련번호')
            old = (prev.get('regions') or {}).get(r['name'])
            if old and old.get('mst') == mst and old.get('bcr') and (r['name'] != C['me'] or old.get('uses_v') == 2):
                regs[r['name']] = old           # 개정 없으면 그대로
                continue
            regs[r['name']] = parse(_get(SERVICE, {'target': 'ordin', 'MST': mst}))
            if r['name'] == C['me']:
                try:   # 별표(용도지역별 건축 가능·불가 건축물) 한글 파일 → kordoc
                    regs[r['name']]['uses'] = fetch_uses(regs[r['name']].get('annex') or [])
                    regs[r['name']]['uses_v'] = 2
                except Exception as e:  # noqa: BLE001
                    errs.append('별표 읽기 실패 %s' % str(e)[:150])
            time.sleep(0.5)
        except Exception as e:  # noqa: BLE001
            errs.append('%s %s' % (r['name'], str(e)[:120]))
            if (prev.get('regions') or {}).get(r['name']):
                regs[r['name']] = prev['regions'][r['name']]
    if not regs:
        raise RuntimeError('조례를 하나도 받지 못함: %s' % '; '.join(errs[:3]))
    if errs:
        log('조례 일부 실패: %s' % '; '.join(errs[:5]))
    # 동해시 외에는 화면에 필요한 숫자만 남김(용량 절약)
    me = C['me']
    for k, v in regs.items():
        if k != me:
            for x in ('related', 'annex'):
                v.pop(x, None)
            for x in ('bcr_art', 'far_art'):
                if v.get(x):
                    v[x] = {'no': v[x].get('no'), 'title': v[x].get('title')}
    return {'at': now().strftime('%Y-%m-%d'), 'regions': regs, 'errors': errs[:6], 'source': '국가법령정보센터 자치법규'}
