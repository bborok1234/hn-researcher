#!/usr/bin/env python3
"""하루치 HN 게시물 전체를 Algolia API로 수집해 markdown 다이제스트 출력.
Usage: python3 fetch_hn.py [YYYY-MM-DD]  (기본: 지금 기준 지난 24시간)"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def fetch_window(start, end):
    stories, seen = [], set()
    # Algolia는 페이지네이션을 1000건에서 자르므로(nbPages=1), 최신순 결과의
    # 가장 오래된 시각으로 end를 좁혀가며 이어받는다.
    while True:
        q = urllib.parse.urlencode({
            "tags": "story",
            "numericFilters": f"created_at_i>={start},created_at_i<{end}",
            "hitsPerPage": 1000,
        })
        with urllib.request.urlopen(f"https://hn.algolia.com/api/v1/search_by_date?{q}") as r:
            hits = json.load(r)["hits"]
        new = [h for h in hits if h["objectID"] not in seen]
        stories += new
        seen.update(h["objectID"] for h in new)
        if len(hits) < 1000:
            return stories
        end = min(h["created_at_i"] for h in hits) + 1  # 같은 초 겹침은 seen으로 dedupe


def to_markdown(stories, label):
    """선별 단계용 목록. URL은 넣지 않는다 — 1,100여 줄에 URL 두 개씩 붙이면
    다이제스트가 21만 토큰까지 부풀고, 선별에는 제목과 ID만 있으면 된다.
    실제 URL은 --urls로 따로 저장해 수집 단계에서 ID로 되찾는다."""
    stories.sort(key=lambda s: s.get("points") or 0, reverse=True)
    lines = [f"# Hacker News — {label}, 총 {len(stories)}건", ""]
    for s in stories:
        lines.append(
            f"- [{s.get('points') or 0}p/{s.get('num_comments') or 0}c] "
            f"#{s['objectID']} {s.get('title') or '(제목 없음)'}"
        )
    return "\n".join(lines)


def url_map(stories):
    return {
        s["objectID"]: s.get("url") or f"https://news.ycombinator.com/item?id={s['objectID']}"
        for s in stories
    }


if __name__ == "__main__":
    urls_path = None
    if "--urls" in sys.argv:
        i = sys.argv.index("--urls")
        urls_path = sys.argv[i + 1]
        del sys.argv[i:i + 2]

    if len(sys.argv) > 1:  # 특정 UTC 하루 (백필용)
        start = int(datetime.strptime(sys.argv[1], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        end = start + 86400
        label = f"{sys.argv[1]} (UTC)"
    else:  # 기본: 지금 기준 지난 24시간 (신선도 최우선)
        end = int(datetime.now(timezone.utc).timestamp())
        start = end - 86400
        fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%m-%d %H:%M")
        label = f"{fmt(start)} ~ {fmt(end)} UTC 24시간"
    stories = fetch_window(start, end)
    assert stories, "수집된 게시물이 없음 — 날짜/창 확인"
    if urls_path:
        json.dump(url_map(stories), open(urls_path, "w"))
    print(to_markdown(stories, label))
