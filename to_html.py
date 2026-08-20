#!/usr/bin/env python3
"""리포트 markdown → 뉴스레터 HTML. Usage: to_html.py report-YYYY-MM-DD.md > out.html

ponytail: 리포트가 실제로 쓰는 문법만 지원(h1/h2/h3, bold, inline code, 링크, 리스트, hr).
범용 markdown 파서가 아니다.

디자인 노트 — 이 리포트의 정체는 '필터'다(1,100여 건 → 7건). 그래서 상단에 추적 중인
프로젝트 전체를 칩으로 깔고 오늘 건진 것만 켠다. 커버리지가 한눈에 보이는 게 핵심이고,
'오늘 매칭 없음' 목록은 본문에서 빼서 이 칩의 꺼진 상태로 표현한다.
"""
import glob
import html
import json
import os
import re
import sys

CSS = """
:root{
  --ink:#0d1220; --surface:#151d31; --line:#242f4d;
  --paper:#e8ecf6; --muted:#8b95ad; --dim:#5c6580; --signal:#ffb45c; --signal-soft:rgba(255,180,92,.13);
  --kr:'Apple SD Gothic Neo','Pretendard',system-ui,sans-serif;
  --slab:'Superclarendon','Iowan Old Style','Charter',Georgia,serif;
  --mono:'SF Mono',Menlo,Monaco,monospace;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ink); color:var(--paper); font-family:var(--kr);
  font-size:16.5px; line-height:1.85; -webkit-font-smoothing:antialiased;
}
/* 발행 시각이 새벽이라, 페이지 위쪽에 아주 옅은 동틀 무렵의 빛만 남긴다 */
body::before{
  content:''; position:fixed; inset:0 0 auto 0; height:340px; pointer-events:none;
  background:radial-gradient(120% 100% at 50% 0%, rgba(255,180,92,.10), transparent 70%);
}
.wrap{position:relative; max-width:730px; margin:0 auto; padding:56px 24px 96px}

/* ── 머리말 ───────────────────────────────────────── */
.masthead{border-bottom:1px solid var(--line); padding-bottom:22px; margin-bottom:26px}
h1{
  font-size:30px; line-height:1.3; letter-spacing:-.4px; font-weight:800;
  margin:0 0 10px;
}
.funnel{
  font-family:var(--slab); font-size:14px; color:var(--muted); margin:0;
  font-variant-numeric:tabular-nums;
}
.funnel b{color:var(--signal); font-weight:600}

/* ── signature: 프로젝트 로스터 ───────────────────── */
.roster{margin:0 0 40px}
.roster-label{
  font-size:11.5px; letter-spacing:.02em; color:var(--dim); margin:0 0 11px;
}
.chips{display:flex; flex-wrap:wrap; gap:6px; list-style:none; padding:0; margin:0}
.chips li{margin:0; padding:6px 9px}
.chips li::before{content:none}
.chip{
  font-family:var(--mono); font-size:11.5px; line-height:1; padding:6px 9px;
  border:1px solid transparent; border-radius:3px; color:var(--dim);
  animation:rise .5s both; animation-delay:calc(var(--i) * 35ms);
}
.chip.on{color:var(--signal); border-color:rgba(255,180,92,.42); background:var(--signal-soft)}
@keyframes rise{from{opacity:0; transform:translateY(5px)} to{opacity:1; transform:none}}
@media (prefers-reduced-motion:reduce){.chip{animation:none}}

/* ── 헤드라인 ─────────────────────────────────────── */
.leads{margin:0 0 44px; padding:0; list-style:none; counter-reset:lead}
.leads li{
  display:grid; grid-template-columns:30px 1fr; gap:4px; align-items:baseline;
  padding:15px 0; border-top:1px solid var(--line); margin:0;
}
.leads li::marker{content:none}
.leads-body{display:block; line-height:1.7}
.leads li::before{
  counter-increment:lead; content:counter(lead);
  font-family:var(--slab); font-size:19px; color:var(--signal); line-height:1.5;
}
.leads strong{font-weight:700}

/* ── 본문 ─────────────────────────────────────────── */
h2{
  font-size:12.5px; letter-spacing:.06em; font-weight:700; color:var(--signal);
  margin:54px 0 20px; padding-bottom:9px; border-bottom:1px solid var(--line);
}
h3{
  font-family:var(--mono); font-size:14px; font-weight:600; color:var(--paper);
  margin:32px 0 10px; padding-left:11px; border-left:2px solid var(--signal);
}
/* 경고 섹션만 붉은 계열 — 나머지와 시급성이 다르다 */
h2.warn{color:#ff8a6b; border-bottom-color:rgba(255,138,107,.35)}
h2.warn + ul li::before{background:#ff8a6b}
p{margin:0 0 15px}
ul{padding-left:0; list-style:none; margin:0 0 15px}
ul li{position:relative; padding-left:17px; margin-bottom:13px}
ul li::before{
  content:''; position:absolute; left:0; top:.72em; width:5px; height:1px;
  background:var(--signal); opacity:.75;
}
/* 프로젝트 이름으로 시작하는 항목은 그 이름이 그 줄의 주인이다 */
ul li > strong:first-child{
  display:inline-block; font-family:var(--mono); font-size:12.5px; font-weight:600;
  color:var(--signal); letter-spacing:-.1px;
}
strong{color:#fff; font-weight:700}
a{color:var(--paper); text-decoration:none; border-bottom:1px solid rgba(255,180,92,.45)}
a:hover{color:var(--signal); border-bottom-color:var(--signal)}
a:focus-visible{outline:2px solid var(--signal); outline-offset:3px; border-radius:2px}
a.src{
  font-family:var(--mono); font-size:11px; color:var(--dim); border-bottom:0;
  white-space:nowrap; padding-left:2px;
}
a.src:hover{color:var(--signal)}
code{
  font-family:var(--mono); font-size:.86em; background:var(--surface);
  padding:1.5px 5px; border-radius:3px; color:#cfd7ea;
}
hr{border:0; border-top:1px solid var(--line); margin:34px 0}
.foot{
  margin-top:64px; padding-top:20px; border-top:1px solid var(--line);
  font-family:var(--mono); font-size:11px; color:var(--dim); letter-spacing:.04em;
}
@media (max-width:560px){
  body{font-size:16px}
  .wrap{padding:36px 18px 72px}
  h1{font-size:24px}
}
"""

SLUG = re.compile(r"^[a-z][a-z0-9._-]{2,29}$")
# 리포트는 섹션 제목을 '## 제목'으로도, 볼드 한 줄('**제목**')로도 쓴다 — 실행마다 흔들린다.
SECTION = re.compile(r"^\s*(?:##+\s+(.+?)|\*\*([^*]+)\*\*)\s*$")


def slugs(text):
    """'`a` / b — 설명' 같은 덩어리에서 프로젝트 이름만 건져낸다."""
    out = []
    for part in re.split(r"[/,]", text):
        part = re.split(r"\s+[—:(]", part.strip())[0]
        part = part.strip(" `*").rstrip(".")
        if SLUG.match(part):
            out.append(part)
    return out


def tokenize(md):
    """(kind, text) 목록으로 정규화. kind: h1 h2 h3 li p hr
    섹션 제목 표기가 두 가지라 여기서 한 번만 흡수하고, 이후 로직은 이 결과만 본다."""
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("# "):
            yield "h1", line[2:]
            continue
        if line == "---":
            yield "hr", ""
            continue
        if line.startswith("### "):
            yield "h3", line[4:]
            continue
        m = SECTION.match(line)
        if m:
            t = (m.group(1) or m.group(2)).strip()
            # 섹션 제목은 한국어 구절이고, 프로젝트 이름은 소문자 슬러그다.
            # 둘 다 '볼드 한 줄'로 오므로 이 구분이 필요하다.
            yield ("h3" if slugs(t) and not re.search(r"[가-힣]", t) else "h2"), t
            continue
        if line.startswith(("- ", "* ")):
            yield "li", line[2:]
            continue
        yield "p", line


def source_link(url):
    """맨 URL은 도메인만 보여준다 — 리포트가 URL을 괄호로 붙이는데, 원문 그대로 두면
    한 줄을 다 잡아먹고 줄바꿈되며 읽는 흐름을 끊는다."""
    host = re.sub(r"^www\.", "", url.split("//", 1)[-1].split("/")[0])
    return f'<a class="src" href="{url}">{html.escape(host)} ↗</a>'


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    # 괄호로 감싼 출처는 괄호까지 걷어낸다
    s = re.sub(r"\(\s*(https?://[^)\s]+)\s*\)", lambda m: source_link(m.group(1)), s)
    s = re.sub(r'(?<![">(=])(https?://[^\s<)\]]+)', lambda m: source_link(m.group(1)), s)
    return s


def roster(md, report_path):
    """(활동한 프로젝트, 오늘 빈 프로젝트).

    섹션이 프로젝트별이 아니라 '결정 종류'별로 나뉘므로, 프로젝트 이름은 항목 본문 안에
    묻혀 있다. 그래서 run.sh가 남긴 projects-<날짜>.txt(추적 중인 전체 목록)와 대조한다.
    목록 파일이 없으면 '매칭 없음' 줄만으로 최소 동작."""
    idle = []
    for m in re.finditer(r"오늘 매칭 없음\s*[::]\s*(.+)", md):
        idle += slugs(m.group(1))

    d = os.path.dirname(os.path.abspath(report_path))
    date = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(report_path))
    known = []
    if date:
        try:
            with open(os.path.join(d, f"projects-{date.group(1)}.txt")) as fh:
                known = [l.strip().lstrip("- ").strip() for l in fh]
            known = [k for k in known if SLUG.match(k)]
        except OSError:
            known = []

    body = md
    active = [k for k in known if k not in idle and re.search(re.escape(k), body)]
    seen = set()
    active = [p for p in active if not (p in seen or seen.add(p))]
    idle = [p for p in idle if not (p in seen or seen.add(p))]
    return active, idle


def funnel(report_path):
    """다이제스트·후보·수집 파일이 옆에 있으면 걸러진 규모를 읽어온다. 없으면 생략."""
    d = os.path.dirname(os.path.abspath(report_path))
    date = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(report_path))
    if not date:
        return None
    date = date.group(1)
    nums = {}
    try:
        with open(os.path.join(d, f"digest-{date}.md")) as f:
            nums["total"] = sum(1 for line in f if line.startswith("- "))
    except OSError:
        return None
    try:
        nums["picked"] = len(json.load(open(os.path.join(d, f"candidates-{date}.json"))))
    except (OSError, ValueError):
        nums["picked"] = None
    try:
        head = open(os.path.join(d, f"pages-{date}.md")).readline()
        nums["read"] = int(re.search(r"성공\s*(\d+)", head).group(1))
    except (OSError, AttributeError, ValueError):
        nums["read"] = None
    return nums


def convert(md):
    """본문 → HTML. 제목·헤드라인 목록·'매칭 없음' 줄은 위에서 따로 쓰므로 제외한다."""
    out, in_list, in_leads = [], False, False
    for kind, text in tokenize(md):
        if kind == "h2":
            in_leads = "헤드라인" in text
        if in_leads or kind == "h1" or "오늘 매칭 없음" in text:
            continue
        if in_list and kind != "li":
            out.append("</ul>")
            in_list = False
        if kind == "li":
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(text)}</li>")
        elif kind == "hr":
            out.append("<hr>")
        elif kind == "h2":
            cls = ' class="warn"' if text.strip() in ("경고", "경고!") else ""
            out.append(f"<h2{cls}>{inline(text)}</h2>")
        elif kind == "h3":
            out.append(f"<h3>{inline(text)}</h3>")
        else:
            out.append(f"<p>{inline(text)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def leads(md):
    """'오늘의 헤드라인' 항목만 추려 순위 목록으로."""
    items, on = [], False
    for kind, text in tokenize(md):
        if kind in ("h1", "h2", "h3"):
            on = kind == "h2" and "헤드라인" in text
            continue
        if on and text.strip():
            items.append(f'<li><span class="leads-body">{inline(text.strip())}</span></li>')
    return items[:3]


if __name__ == "__main__":
    path = sys.argv[1]
    md = open(path).read()
    title = next((l[2:].strip() for l in md.splitlines() if l.startswith("# ")), "HN 리포트")

    f = funnel(path)
    bits = []
    if f:
        bits.append(f"<b>{f['total']:,}</b>건 읽고")
        if f.get("picked"):
            bits.append(f"<b>{f['picked']}</b>건 추려")
        if f.get("read"):
            bits.append(f"<b>{f['read']}</b>건 원문 확인")
    active, idle = roster(md, path)
    if active:
        bits.append(f"<b>{len(active)}</b>개 프로젝트에 배달")

    chips = "".join(
        f'<li class="chip{" on" if p in active else ""}" style="--i:{i}">{html.escape(p)}</li>'
        for i, p in enumerate(active + idle)
    )
    lead_items = leads(md)

    print(f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<header class="masthead">
  <h1>{html.escape(title)}</h1>
  {f'<p class="funnel">{" · ".join(bits)}</p>' if bits else ""}
</header>
{f'''<section class="roster">
  <p class="roster-label">추적 중인 프로젝트 — 켜진 것이 오늘 건진 것</p>
  <ul class="chips">{chips}</ul>
</section>''' if chips else ""}
{f'<ol class="leads">{"".join(lead_items)}</ol>' if lead_items else ""}
{convert(md)}
<p class="foot">hn-researcher · 매일 아침 자동 발행</p>
</div></body></html>""")
