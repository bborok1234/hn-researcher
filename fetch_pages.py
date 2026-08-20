#!/usr/bin/env python3
"""2단계(수집): 선별된 후보의 원문/HN댓글을 받아 텍스트로 정리해 stdout에 출력.
LLM 없이 순수 코드로 처리한다 — 예전에는 모델이 WebFetch를 20번 부르며 페이지 전문을
컨텍스트에 쌓았고, 그 누적분이 리포트 1회 비용의 57%였다.

Usage: python3 fetch_pages.py candidates.json urls.json
  urls.json — fetch_hn.py --urls가 만든 {게시물ID: URL} 맵.
  선별 단계 목록에는 URL을 넣지 않으므로(토큰 절약) 여기서 ID로 되찾는다.
"""
import concurrent.futures as cf
import html
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

MAX_CHARS = 8000          # 항목당 본문 상한
MAX_COMMENTS = 40
TIMEOUT = 20
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}
BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip_depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth and data.strip():
            self.parts.append(data)

    def text(self):
        t = re.sub(r"[ \t]+", " ", "".join(self.parts))
        return re.sub(r"\n\s*\n\s*\n+", "\n\n", t).strip()


def html_to_text(raw):
    p = TextExtractor()
    p.feed(raw)
    return p.text()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype and "json" not in ctype:
            raise ValueError(f"본문이 아닌 콘텐츠({ctype.split(';')[0]})")
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read(3_000_000).decode(charset, errors="replace")


def hn_comments(item_id):
    """Algolia items API로 댓글 트리를 받아 평탄화."""
    raw = get(f"https://hn.algolia.com/api/v1/items/{item_id}")
    out = []

    def walk(node):
        if len(out) >= MAX_COMMENTS:
            return
        t = node.get("text")
        if t:
            out.append(f"- {html_to_text(html.unescape(t))}")
        for c in node.get("children") or []:
            walk(c)

    walk(json.loads(raw))
    return "\n".join(out)


def collect(c):
    """후보 하나를 수집. (candidate, 본문 or None, 실패사유 or None)"""
    try:
        # HN 외 소스(lob·gn 접두사)는 Algolia에 없다. 숫자 ID만 댓글 경로로 보낸다 —
        # 안 막으면 Lobsters/GeekNews의 comments 후보가 전부 404로 죽는다.
        if c.get("source") == "comments" and str(c.get("id") or "").isdigit():
            body = hn_comments(c["id"])
        else:
            body = html_to_text(get(c["url"]))
        if len(body) < 200:
            return c, None, "본문이 거의 비어 있음(JS 렌더링 추정)"
        return c, body[:MAX_CHARS], None
    except urllib.error.HTTPError as e:
        return c, None, f"HTTP {e.code}"
    except Exception as e:  # 네트워크·인코딩·형식 등 — 실패는 버리고 사유만 남긴다
        return c, None, f"{type(e).__name__}: {e}"[:120]


if __name__ == "__main__":
    cands = json.load(open(sys.argv[1]))
    # URL 맵은 여러 개를 받아 합친다. 오늘 것 + 지난 보류 항목(재심으로 되살아난 것)의 맵이
    # 따로 오기 때문이다 — 선별 목록에는 URL을 넣지 않으므로(토큰 레버) 여기서 되찾아야 한다.
    urls = {}
    for p in sys.argv[2:]:
        with open(p) as f:
            urls.update(json.load(f))
    for c in cands:
        if not c.get("url"):
            c["url"] = urls.get(str(c.get("id")), "")
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(collect, cands))

    ok = [(c, b) for c, b, _ in results if b]
    bad = [(c, e) for c, _, e in results if e]

    print(f"# 수집 결과 — 성공 {len(ok)}건 / 실패 {len(bad)}건\n")
    for c, body in ok:
        hn = f"https://news.ycombinator.com/item?id={c['id']}" if c.get("id") else ""
        kind = "HN 댓글" if c.get("source") == "comments" else "원문"
        # 한글 약 500자/분, 영문 약 1,200자/분으로 잡아 섞인 글을 대충 700자/분으로 근사
        mins = max(1, round(len(body) / 700))
        print(f"## {c['title']}")
        print(f"- 관련 프로젝트: {c.get('project', '?')} / 선별 이유: {c.get('why', '')}")
        print(f"- {kind} | 읽기 {mins}분 | URL: {c.get('url', '')} | HN: {hn}\n")
        print(body)
        print("\n---\n")

    if bad:
        print("## 수집 실패 (리포트의 '버린 것'에 사유와 함께 적을 것)\n")
        for c, err in bad:
            print(f"- {c['title']} — {err} ({c.get('url', '')})")
