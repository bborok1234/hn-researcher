#!/usr/bin/env python3
"""HN 밖의 소스. 셋에서 멈춘다 — 소스를 늘리는 것 자체가 목표가 아니다.

두 모드가 있고, 나뉘는 이유는 **관련성 필터가 필요한지**다.

  --digest   Lobsters + GeekNews → 다이제스트 줄 + ID→URL 맵.
             HN과 같은 처리를 받는다(선별 → 수집 → 작문).

  --releases GitHub Releases Atom → 릴리스 노트 본문 그대로.
             **선별을 건너뛴다.** 내가 의존하는 레포 목록을 내가 정하니 관련성이 100%고,
             "지난 24시간" 날짜 컷이면 끝난다. 릴리스 노트가 곧 본문이라 수집 단계도 필요 없다.
             리포트의 `경고` 섹션을 먹여줄 주 재료다.

다이제스트 줄 형식은 `fetch_hn.py`와 같다(`- [Np/Mc] #ID 제목`). 뒤 단계는 소스를 구분하지 않는다.
ID에 접두사를 붙여 HN 숫자 ID와 겹치지 않게 한다 — `lob<id>`, `gn<id>`.

한 소스가 죽어도 나머지는 나온다. 소스 추가가 아침 리포트를 잃는 이유가 되면 안 된다.

Usage:
  sources.py [YYYY-MM-DD] --digest [--urls PATH]
  sources.py [YYYY-MM-DD] --releases "owner/repo owner/repo"
"""
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

TIMEOUT = 20
UA = "hn-researcher/1.0 (+local personal digest)"
ATOM = "{http://www.w3.org/2005/Atom}"
MAX_RELEASE_CHARS = 1500      # 릴리스 노트는 길다. 앞부분에 breaking change가 온다


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read(3_000_000)


def _ts(text):
    """ISO 8601 또는 RFC 2822 → epoch. 3.9의 fromisoformat은 'Z'를 못 읽는다."""
    text = (text or "").strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return parsedate_to_datetime(text).timestamp()


def lobsters(raw, start, end):
    """`hottest.json` — 무키·무인증. 한 번에 25건(`?page=2`는 무시된다).

    `tags[]`가 있어 HN보다 필터가 쉽지만, 태그로 걸러내지 않고 제목 옆에 붙여 넘긴다 —
    무엇을 버릴지는 프롬프트가 정한다.
    """
    out = []
    for s in json.loads(raw):
        if not isinstance(s, dict) or not start <= _ts(s.get("created_at")) < end:
            continue
        sid = str(s.get("short_id") or "").strip()
        if not sid:
            continue
        tags = " ".join(f"[{t}]" for t in (s.get("tags") or [])[:4])
        out.append({
            "id": f"lob{sid}",
            "title": f"{s.get('title') or '(제목 없음)'} {tags}".strip(),
            "points": s.get("score") or 0,
            "comments": s.get("comment_count") or 0,
            # 자체 게시물은 외부 URL이 없다 — HN의 url_map과 같은 방식으로 토론 페이지를 쓴다
            "url": s.get("url") or s.get("comments_url") or "",
        })
    return out


def geeknews(raw, start, end):
    """`news.hada.io/rss/news` — 한국어 제목이라 정보 밀도가 높다.

    **경로가 `/rss/`지만 실제로 주는 것은 Atom이다**(50 entry). RSS 2.0으로 읽으면
    `item`이 하나도 없어 조용히 0건이 된다.

    HN에서 놓친 것을 한국어 맥락으로 재확인하는 용도다. 점수·댓글 수가 피드에 없어 0으로 둔다 —
    이 소스에서는 인기도가 신호가 아니라는 뜻이고, 선별은 제목으로만 판단한다.
    """
    out = []
    for e in ET.fromstring(raw).iter(f"{ATOM}entry"):
        link = e.find(f"{ATOM}link")
        url = (link.get("href") if link is not None else "") or (e.findtext(f"{ATOM}id") or "")
        try:
            ts = _ts(e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated"))
        except (TypeError, ValueError):
            continue
        if not url or not start <= ts < end:
            continue
        m = re.search(r"id=(\d+)", url)
        out.append({
            # hash()는 PYTHONHASHSEED 때문에 실행마다 달라진다 — 같은 글이 매일 새 ID를
            # 받아 영원히 '처음 본 것'이 된다. 안정적인 다이제스트를 쓴다.
            "id": f"gn{m.group(1) if m else hashlib.sha1(url.encode()).hexdigest()[:8]}",
            "title": (e.findtext(f"{ATOM}title") or "(제목 없음)").strip(),
            "points": 0,
            "comments": 0,
            "url": url,
        })
    return out


def releases(raw, repo, start, end):
    """`/{owner}/{repo}/releases.atom` — 선별을 건너뛰는 유일한 소스."""
    out = []
    for e in ET.fromstring(raw).iter(f"{ATOM}entry"):
        try:
            ts = _ts(e.findtext(f"{ATOM}updated"))
        except (TypeError, ValueError):
            continue
        if not start <= ts < end:
            continue
        link = e.find(f"{ATOM}link")
        body = re.sub(r"<[^>]+>", " ", e.findtext(f"{ATOM}content") or "")
        out.append({
            "repo": repo,
            "tag": (e.findtext(f"{ATOM}title") or "").strip(),
            "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"),
            "url": (link.get("href") if link is not None else "") or "",
            "body": " ".join(body.split())[:MAX_RELEASE_CHARS],
        })
    return out


def digest_lines(items, label):
    """`fetch_hn.py`와 같은 줄 형식. 뒤 단계는 소스를 구분하지 않는다."""
    items.sort(key=lambda s: s["points"], reverse=True)
    lines = ["", f"# {label} — 총 {len(items)}건", ""]
    lines += [f"- [{i['points']}p/{i['comments']}c] #{i['id']} {i['title']}" for i in items]
    return "\n".join(lines)


def releases_markdown(rels):
    if not rels:
        return ""
    rels.sort(key=lambda r: (r["repo"], r["tag"]))
    lines = [f"# 지난 24시간 릴리스 — {len(rels)}건", ""]
    for r in rels:
        lines.append(f"## {r['repo']} {r['tag']} ({r['date']})")
        lines.append(f"- {r['url']}")
        lines.append(r["body"] or "(본문 없음)")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    args = sys.argv[1:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    day = next((a for a in args if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a)), None)
    if day:
        start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        end = start + 86400
    else:
        end = datetime.now(timezone.utc).timestamp()
        start = end - 86400

    def pull(label, fn, url):
        """한 소스가 죽어도 나머지는 나온다."""
        try:
            return fn(_get(url))
        except (urllib.error.URLError, OSError, ET.ParseError, ValueError) as e:
            print(f"경고: {label} 실패 ({type(e).__name__}: {e}) — 건너뜀", file=sys.stderr)
            return []

    if "--releases" in args:
        repos = [r for r in re.split(r"[\s,]+", opt("--releases", "") or "") if "/" in r]
        rels = []
        for repo in repos:
            rels += pull(f"releases {repo}",
                         lambda raw, repo=repo: releases(raw, repo, start, end),
                         f"https://github.com/{repo}/releases.atom")
        print(releases_markdown(rels), end="")
        sys.exit(0)

    lob = pull("Lobsters", lambda raw: lobsters(raw, start, end), "https://lobste.rs/hottest.json")
    gn = pull("GeekNews", lambda raw: geeknews(raw, start, end), "https://news.hada.io/rss/news")

    urls_path = opt("--urls")
    if urls_path:
        with open(urls_path, "w") as f:
            json.dump({i["id"]: i["url"] for i in lob + gn if i["url"]}, f, ensure_ascii=False)
    for label, items in (("Lobsters", lob), ("GeekNews", gn)):
        if items:
            print(digest_lines(items, label))
