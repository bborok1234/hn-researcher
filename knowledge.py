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
ITEM = re.compile(r"^- (\d{4}-\d{2}-\d{2}) · \[(.*?)\]\((\S+?)\)(?: — (.*?))?(?: `#([^`\s]+)`)?$")


def _flat(s):
    """한 줄로 눕힌다. 줄바꿈이 하나라도 남으면 그 항목은 다음 읽기에서 조용히 사라진다."""
    return " ".join(str(s or "").split())


def item_line(date, title, url, why="", hn_id=""):
    """항목 한 줄. 제목의 대괄호는 링크를 깨뜨리므로 지운다."""
    safe = _flat(title).replace("[", "(").replace("]", ")")
    line = f"- {date} · [{safe}]({_flat(url).replace(' ', '%20')})"
    if why:
        line += f" — {_flat(why)}"
    if hn_id:
        line += f" `#{hn_id}`"
    return line


def parse_items(text, section, on_drop=None):
    """페이지 본문에서 한 섹션의 항목을 뽑는다.

    형식이 안 맞는 줄은 버리는데, **버린 줄은 다음 덮어쓰기에서 영구히 사라진다.**
    그래서 조용히 버리지 않고 `on_drop`으로 알린다.
    """
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
        elif line.strip() and line.strip() != "(없음)" and on_drop:
            on_drop(line.rstrip())
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


RESERVED = {"index", "log"}     # OKF §3.1 — 이 이름은 개념 문서가 쓸 수 없다


def page_name(bucket):
    """파일명. `project` 값은 LLM이 채우므로 임의 문자열이라고 보고 다듬는다.

    경로 구분자·제어문자를 막고 길이를 자른다. 예약 이름을 그대로 쓰면
    생성된 `index.md`가 항목 페이지를 덮어써 그 주제가 통째로 사라진다.
    """
    safe = re.sub(r"[\x00-\x1f\x7f/\\:]+", "-", _flat(bucket)).strip(". -")[:80]
    return f"{safe}-주제" if safe.lower() in RESERVED else (safe or "기타")


def bundle_index(names, version="0.2"):
    """번들 루트 index.md. okf_version은 여기에만 쓴다(§12). names는 이미 파일명이다."""
    lines = ["---", f"okf_version: \"{version}\"", "---", "", "# 주제", ""]
    lines += [f"* [{n}](/topics/{n}.md) - {n} 관련 누적 항목" for n in sorted(names)]
    return "\n".join(lines) + "\n"


def source_of(item_id):
    """ID 접두사가 소스다. HN은 숫자, `lob…`은 Lobsters, `gn…`은 GeekNews."""
    i = str(item_id or "")
    return "Lobsters" if i.startswith("lob") else "GeekNews" if i.startswith("gn") else "HN"


def log_entry(date, adopted, pending, revived, by_source=None):
    """log.md 한 날. 날짜 제목은 ISO 8601이어야 한다(§9).

    소스별 수를 함께 남긴다. 추가한 소스가 실제로 리포트에 쓰이는지는 며칠 봐야 알고,
    그때 이 줄이 없으면 후보 파일을 다시 파헤쳐야 한다.
    """
    line = f"- 채택 {adopted}건, 보류 {pending}건"
    if revived:
        line += f", **되살아남 {revived}건**"   # 보류가 나중에 채택된 것 — 재심이 값을 한 증거
    if by_source:
        parts = ", ".join(f"{s} {n[0]}/{n[0] + n[1]}" for s, n in sorted(by_source.items()))
        line += f"\n- 소스별 채택/후보 — {parts}"
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
    if not (date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)):
        sys.exit("사용법: knowledge.py --ingest YYYY-MM-DD | --pending [--days N] [--urls]")
    out = opt("--dir", "out")

    def load(path, default):
        """망가진 JSON 하나가 아침 리포트를 날리지 않게 한다 — 철하기는 리포트보다 덜 중요하다."""
        try:
            return json.loads(read(os.path.join(out, path)) or "null") or default
        except json.JSONDecodeError as e:
            print(f"경고: {path} 를 읽지 못함 ({e}) — 건너뜀", file=sys.stderr)
            return default

    cands = load(f"candidates-{date}.json", [])
    # URL 맵 전부를 합친다. HN 외 소스(urls-extra)와 재심 항목(pending-urls)이 따로 오므로
    # 오늘 것만 읽으면 그 항목들의 URL을 못 찾아 조용히 버려진다.
    urls = {}
    for name in (f"urls-{date}.json", f"urls-extra-{date}.json", f"pending-urls-{date}.json"):
        got = load(name, {})
        if isinstance(got, dict):
            urls.update(got)
    report = read(os.path.join(out, f"report-{date}.md"))
    if not isinstance(cands, list) or not cands:
        sys.exit(f"철할 후보가 없다: candidates-{date}.json")

    dropped = []
    def items(text, section):
        return parse_items(text, section, on_drop=dropped.append)

    # 기존 페이지를 먼저 다 읽는다. 이유 둘:
    #  1) 되살아난 항목의 URL은 오늘 urls 맵에 없다(어제 잡힌 것이다). 번들이 그 URL을 안다.
    #  2) 보류 정리는 전역이어야 한다 — 재심 때 LLM이 project를 다르게 적으면
    #     원래 페이지의 보류 항목이 영구히 남아 매일 다시 재심 대상으로 올라온다.
    pages = {}
    known_url = {}
    if os.path.isdir(topics):
        for name in sorted(os.listdir(topics)):
            if not name.endswith(".md") or name == "index.md":
                continue
            text = read(os.path.join(topics, name))
            pages[name[:-3]] = {s: items(text, s) for s in (ADOPTED, PENDING)}
            for s in (ADOPTED, PENDING):
                for it in pages[name[:-3]][s]:
                    if it["id"]:
                        known_url.setdefault(it["id"], it["url"])

    # 채택 판정: 리포트가 원문 URL로 링크하므로 URL 등장 여부가 그대로 판정이 된다.
    fresh, today_adopted = {}, set()
    for c in cands if isinstance(cands, list) else []:
        hn = str((c or {}).get("id") or "")
        # HN 폴백은 숫자 ID에만 유효하다 — lob·gn 접두사는 그 주소가 없다.
        url = (urls.get(hn) or known_url.get(hn)
               or (f"https://news.ycombinator.com/item?id={hn}" if hn.isdigit() else ""))
        if not url:
            dropped.append(f"URL을 찾을 수 없는 후보: #{hn}")
            continue
        bucket = _flat((c or {}).get("project")) or "기타"
        section = ADOPTED if url and url in report else PENDING
        if section == ADOPTED:
            today_adopted.add(url)
        fresh.setdefault(bucket, {ADOPTED: [], PENDING: []})[section].append(
            {"date": date, "title": _flat((c or {}).get("title")) or url, "url": url,
             "why": _flat((c or {}).get("why")), "id": hn})

    os.makedirs(topics, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    projects = set()
    try:
        import build_profile
        projects = build_profile.active_projects(days=14)
    except Exception:      # noqa: BLE001 — 감지가 실패해도 철하는 것은 계속돼야 한다
        pass

    # 채택된 URL은 어느 페이지에서도 보류로 남지 않는다.
    for bucket, new in fresh.items():
        page = pages.setdefault(page_name(bucket), {ADOPTED: [], PENDING: []})
        page[ADOPTED] = merge(page[ADOPTED], new[ADOPTED])
        page[PENDING] = merge(page[PENDING], new[PENDING])
    taken = today_adopted | {i["url"] for p in pages.values() for i in p[ADOPTED]}
    revived = sum(1 for p in pages.values() for i in p[PENDING] if i["url"] in today_adopted)
    for name, page in pages.items():
        page[PENDING] = [i for i in page[PENDING] if i["url"] not in taken]

    def write(path, text):
        """원자적 쓰기. 정본이 여기 하나뿐이라 중간에 끊기면 그 주제가 통째로 사라진다."""
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)

    for name, page in pages.items():
        kind = "Project" if name in projects else "Topic"
        write(os.path.join(topics, f"{name}.md"),
              render_page(kind, name, page[ADOPTED], page[PENDING], now))

    names = sorted(pages)
    write(os.path.join(root, "index.md"), bundle_index(names))
    write(os.path.join(topics, "index.md"), "# 주제\n\n" + "\n".join(
        f"* [{n}]({n}.md) - {n} 관련 누적 항목" for n in names) + "\n")
    if dropped:
        print(f"경고: 형식이 안 맞는 줄 {len(dropped)}개를 버렸다 — 첫 줄: {dropped[0][:80]}",
              file=sys.stderr)

    # log.md는 최신이 위다(§9). 앞에 붙인다.
    n_ad = sum(len(v[ADOPTED]) for v in fresh.values())
    n_pd = sum(len(v[PENDING]) for v in fresh.values())
    by_source = {}
    for v in fresh.values():
        for section, idx in ((ADOPTED, 0), (PENDING, 1)):
            for it in v[section]:
                by_source.setdefault(source_of(it["id"]), [0, 0])[idx] += 1
    log_path = os.path.join(root, "log.md")
    prev = read(log_path)
    head = "# 인제스트 기록\n\n"
    body = log_drop(prev[len(head):] if prev.startswith(head) else prev, date)
    with open(log_path, "w") as f:
        f.write(head + log_entry(date, n_ad, n_pd, revived, by_source) + ("\n" + body.lstrip("\n")
                                                               if body.strip() else ""))
    print(f"철함: 채택 {n_ad} / 보류 {n_pd} / 되살아남 {revived} → {root}")
