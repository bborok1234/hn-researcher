#!/usr/bin/env python3
"""누적 지식 — 긁어왔지만 안 쓰인 후보를 버리지 않고 주제별로 철한다.

지금까지 하루가 끝나면 후보 25건 중 리포트에 오른 12건 말고는 전부 사라졌다.
LLM이 이미 "이 항목은 프로젝트 X에 이런 이유로 관련 있다"고 판정한 것을 버리는 것이다.

정본은 마크다운, 형식은 OKF v0.2(Google Cloud). **쓰기만 준수한다** —
frontmatter를 OKF로 내보내되 우리가 읽는 것은 본문의 줄 형식뿐이다.
macOS 기본 파이썬(3.9.6)에 yaml이 없어서, 우리가 YAML을 파싱해야 하는 순간
의존성이 늘거나 손으로 쓴 파서를 안고 가야 한다. 내보내기는 문자열 조립이라 공짜다.

**LLM 인제스트 패스는 없다.** llm-wiki 패턴의 절반(LLM이 위키를 재편성)은
`ROADMAP.md`의 `선을 넘는 것`에 이미 있고, 하루 2턴을 3턴으로 만든다.
종합은 리포트 작문 턴에서 이미 일어나므로 여기서는 철하기만 한다 — 0토큰.

사용법:
  knowledge.py --ingest YYYY-MM-DD [--dir out]   그날 후보·리포트를 번들에 반영
  knowledge.py --pending [--days 14] [--dir out] 재심 대상(보류 항목)을 stdout으로
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

ADOPTED, PENDING = "채택", "보류"
# 항목 한 줄의 형식이 이 파일의 실제 계약이다. frontmatter가 아니라 이 정규식이다.
ITEM = re.compile(r"^- (\d{4}-\d{2}-\d{2}) · \[(.*?)\]\((\S+?)\)(?: — (.*?))?(?: `#(\d+)`)?$")


def item_line(date, title, url, why="", hn_id=""):
    """항목 한 줄. 제목의 대괄호는 링크를 깨뜨리므로 지운다."""
    safe = title.replace("[", "(").replace("]", ")").strip()
    line = f"- {date} · [{safe}]({url})"
    if why:
        line += f" — {why.replace(chr(10), ' ').strip()}"
    if hn_id:
        line += f" `#{hn_id}`"
    return line


def parse_items(text, section):
    """페이지 본문에서 한 섹션의 항목을 뽑는다. 형식이 안 맞는 줄은 버린다."""
    body = text.split(f"# {section}", 1)
    if len(body) < 2:
        return []
    out = []
    for line in body[1].splitlines():
        if line.startswith("# "):        # 다음 섹션에서 멈춘다
            break
        m = ITEM.match(line.rstrip())
        if m:
            out.append({"date": m.group(1), "title": m.group(2), "url": m.group(3),
                        "why": m.group(4) or "", "id": m.group(5) or ""})
    return out


def merge(old, new):
    """URL 기준 합치기. 먼저 본 날짜를 유지한다 — 언제 처음 잡혔는지가 신호다."""
    by_url = {}
    for it in old + new:
        prev = by_url.get(it["url"])
        by_url[it["url"]] = {**it, "date": min(prev["date"], it["date"])} if prev else it
    return sorted(by_url.values(), key=lambda x: (x["date"], x["title"]))


def render_page(kind, title, adopted, pending, now):
    """OKF 개념 문서. 필수 필드는 `type` 하나다(§4.1)."""
    lines = [
        "---",
        f"type: {kind}",
        f"title: {title}",
        f"description: {title} 관련해 수집한 항목의 누적 기록.",
        f"timestamp: {now}",
        "---",
        "",
        f"# {ADOPTED}",
        "",
    ]
    lines += [item_line(**{k: i[k] for k in ("date", "title", "url", "why")}, hn_id=i["id"])
              for i in adopted] or ["(없음)"]
    lines += ["", f"# {PENDING}", ""]
    lines += [item_line(**{k: i[k] for k in ("date", "title", "url", "why")}, hn_id=i["id"])
              for i in pending] or ["(없음)"]
    return "\n".join(lines) + "\n"


def page_name(bucket):
    """파일명. 경로 구분자만 막고 나머지는 그대로 둔다 — 한국어 주제도 파일명이 된다."""
    return re.sub(r"[/\\:]+", "-", bucket.strip()) or "기타"


def bundle_index(names, version="0.2"):
    """번들 루트 index.md. okf_version은 여기에만 쓴다(§12)."""
    lines = ["---", f"okf_version: \"{version}\"", "---", "", "# 주제", ""]
    lines += [f"* [{n}](/topics/{page_name(n)}.md) - {n} 관련 누적 항목" for n in sorted(names)]
    return "\n".join(lines) + "\n"


def log_entry(date, adopted, pending, revived):
    """log.md 한 날. 날짜 제목은 ISO 8601이어야 한다(§9)."""
    line = f"- 채택 {adopted}건, 보류 {pending}건"
    if revived:
        line += f", **되살아남 {revived}건**"   # 보류가 나중에 채택된 것 — 재심이 값을 한 증거
    return f"## {date}\n\n{line}\n"


def log_drop(body, date):
    """같은 날짜 블록을 지운다. 항목 페이지는 URL 기준 합치기라 멱등인데 로그는 아니어서,
    백필로 같은 날을 다시 돌리면 기록이 중복됐다."""
    out, skip = [], False
    for line in body.splitlines(keepends=True):
        if line.startswith("## "):
            skip = line[3:].strip() == date
        if not skip:
            out.append(line)
    return "".join(out)


if __name__ == "__main__":
    args = sys.argv[1:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    root = os.path.join(opt("--dir", "out"), "knowledge")
    topics = os.path.join(root, "topics")

    def read(path):
        try:
            with open(path) as f:
                return f.read()
        except OSError:
            return ""

    if "--pending" in args:
        # 재심 대상. 창을 제한하는 것은 프롬프트 크기 때문이고, 번들에서는 아무것도 지우지 않는다.
        days = int(opt("--days", 14))
        cutoff = (datetime.now(timezone.utc).timestamp() - days * 86400)
        floor = datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y-%m-%d")
        rows = []
        for name in sorted(os.listdir(topics) if os.path.isdir(topics) else []):
            if name == "index.md" or not name.endswith(".md"):
                continue
            bucket = name[:-3]
            for it in parse_items(read(os.path.join(topics, name)), PENDING):
                if it["date"] >= floor:
                    rows.append((it["date"], bucket, it))
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
        if "--urls" in args:
            # 선별 목록에는 URL을 넣지 않는다(216KB → 85KB 레버). 되살아난 항목의 URL은
            # 2단계가 되찾아야 하므로 ID→URL 맵을 따로 내보낸다.
            json.dump({it["id"]: it["url"] for _, _, it in rows if it["id"]},
                      sys.stdout, ensure_ascii=False)
            sys.exit(0)
        for date, bucket, it in rows:
            why = f" — {it['why']}" if it["why"] else ""
            print(f"- [{bucket}] {date} #{it['id'] or '?'} {it['title']}{why}")
        sys.exit(0)

    date = opt("--ingest")
    assert date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date), "사용법: --ingest YYYY-MM-DD"
    out = opt("--dir", "out")
    cands = json.loads(read(os.path.join(out, f"candidates-{date}.json")) or "[]")
    urls = json.loads(read(os.path.join(out, f"urls-{date}.json")) or "{}")
    report = read(os.path.join(out, f"report-{date}.md"))
    assert cands, f"후보가 없다: candidates-{date}.json"

    # 채택 판정: 리포트가 원문 URL로 링크하므로 URL 등장 여부가 그대로 판정이 된다.
    fresh = {}
    for c in cands:
        hn = str(c.get("id") or "")
        url = urls.get(hn) or f"https://news.ycombinator.com/item?id={hn}"
        bucket = (c.get("project") or "기타").strip() or "기타"
        section = ADOPTED if url and url in report else PENDING
        fresh.setdefault(bucket, {ADOPTED: [], PENDING: []})[section].append(
            {"date": date, "title": c.get("title") or url, "url": url,
             "why": c.get("why") or "", "id": hn})

    os.makedirs(topics, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    projects = set()
    try:
        import build_profile
        projects = build_profile.active_projects(days=14)
    except Exception:      # noqa: BLE001 — 감지가 실패해도 철하는 것은 계속돼야 한다
        pass

    revived = 0
    for bucket, new in fresh.items():
        path = os.path.join(topics, f"{page_name(bucket)}.md")
        old = read(path)
        adopted = merge(parse_items(old, ADOPTED), new[ADOPTED])
        # 전에 보류였다가 이번에 채택된 것은 보류에서 빼야 한다 — 그게 재심이 닫히는 지점이다.
        taken = {i["url"] for i in adopted}
        was_pending = {i["url"] for i in parse_items(old, PENDING)}
        revived += len(was_pending & {i["url"] for i in new[ADOPTED]})
        pending = [i for i in merge(parse_items(old, PENDING), new[PENDING]) if i["url"] not in taken]
        kind = "Project" if bucket in projects else "Topic"
        with open(path, "w") as f:
            f.write(render_page(kind, bucket, adopted, pending, now))

    names = [n[:-3] for n in os.listdir(topics) if n.endswith(".md") and n != "index.md"]
    with open(os.path.join(root, "index.md"), "w") as f:
        f.write(bundle_index(names))
    with open(os.path.join(topics, "index.md"), "w") as f:
        f.write("# 주제\n\n" + "\n".join(
            f"* [{n}]({page_name(n)}.md) - {n} 관련 누적 항목" for n in sorted(names)) + "\n")

    # log.md는 최신이 위다(§9). 앞에 붙인다.
    n_ad = sum(len(v[ADOPTED]) for v in fresh.values())
    n_pd = sum(len(v[PENDING]) for v in fresh.values())
    log_path = os.path.join(root, "log.md")
    prev = read(log_path)
    head = "# 인제스트 기록\n\n"
    body = log_drop(prev[len(head):] if prev.startswith(head) else prev, date)
    with open(log_path, "w") as f:
        f.write(head + log_entry(date, n_ad, n_pd, revived) + ("\n" + body.lstrip("\n")
                                                               if body.strip() else ""))
    print(f"철함: 채택 {n_ad} / 보류 {n_pd} / 되살아남 {revived} → {root}")
