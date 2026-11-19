"""도내 순위·백분위·강점/개선 판정.

pct = (N - 순위) / (N - 1) × 100  (1위 = 100, 꼴찌 = 0)
강점 = 상위 strong_pct %, 개선 필요 = 하위 weak_pct %. N=18이면 1~5위 강점, 14~18위 개선 필요.
"""
import math


def rank(values, direction, judge):
    """values: {시군: 값}. direction: 1 높을수록 좋음, -1 낮을수록 좋음, 0 판정 제외(순위는 높은 값 순)."""
    items = [(k, v) for k, v in values.items() if v is not None]
    if not items:
        return [], {}
    rev = direction != -1
    items.sort(key=lambda kv: kv[1], reverse=rev)
    n = len(items)
    strong_n = math.ceil(n * judge.get('strong_pct', 25) / 100.0)
    weak_n = math.ceil(n * judge.get('weak_pct', 25) / 100.0)
    out = []
    prev_v, prev_rank = None, 0
    for i, (k, v) in enumerate(items):
        r = prev_rank if v == prev_v else i + 1  # 같은 값은 같은 순위
        prev_v, prev_rank = v, r
        pct = round((n - r) / (n - 1) * 100, 1) if n > 1 else 100.0
        if direction == 0:
            j = 'excluded'
        elif r <= strong_n:
            j = 'strong'
        elif r > n - weak_n:
            j = 'weak'
        else:
            j = 'middle'
        out.append({'name': k, 'value': v, 'rank': r, 'pct': pct, 'judge': j})
    by = {o['name']: o for o in out}
    return out, by
