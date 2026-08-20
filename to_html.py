#!/usr/bin/env python3
"""리포트 markdown → 뉴스레터 HTML. Usage: to_html.py report.md > report.html
ponytail: 리포트가 쓰는 문법만 지원(h1/h2/h3, bold, 링크, 리스트, hr) — 범용 md 파서 아님."""
import html
import re
import sys

CSS = """
body{margin:0;padding:0;background:#f4f1ea;font-family:'Apple SD Gothic Neo',-apple-system,sans-serif;color:#2b2b2b}
.wrap{max-width:680px;margin:0 auto;padding:32px 20px}
.card{background:#fff;border-radius:12px;padding:36px 40px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.5px}
h1+p{color:#8a8378;font-size:14px;margin-top:0}
h2{font-size:19px;margin:36px 0 12px;padding-bottom:8px;border-bottom:2px solid #e8630a;color:#1a1a1a}
h3{font-size:16px;margin:24px 0 8px}
p,li{font-size:15px;line-height:1.75}
a{color:#e8630a;text-decoration:none;word-break:break-all}
a:hover{text-decoration:underline}
strong{color:#111}
hr{border:none;border-top:1px solid #eee;margin:28px 0}
ul{padding-left:22px}
.footer{text-align:center;color:#b0a99c;font-size:12px;margin:24px 0}
"""


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"(?<![\"(>])(https?://[^\s<)]+)", r'<a href="\1">\1</a>', s)
    return s


def convert(md):
    out, in_list = [], False
    for line in md.splitlines():
        line = line.rstrip()
        is_li = line.startswith("- ")
        if in_list and not is_li:
            out.append("</ul>")
            in_list = False
        if not line:
            continue
        if line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line == "---":
            out.append("<hr>")
        elif is_li:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
        else:
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


if __name__ == "__main__":
    md = open(sys.argv[1]).read()
    print(f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HN 스카우트 뉴스레터</title><style>{CSS}</style></head>
<body><div class="wrap"><div class="card">
{convert(md)}
</div><p class="footer">hn-researcher · 매일 아침 자동 발행</p></div></body></html>""")
