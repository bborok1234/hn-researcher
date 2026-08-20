#!/usr/bin/env python3
"""Claude Code + Codex 사용 기록에서 활동 다이제스트를 뽑아 stdout으로 출력.
PROFILE.md 생성용 원료 — profile.sh가 claude -p에 넣는다."""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
NOW = time.time()
RECENT_DAYS = 30
MAX_PROMPTS_PER_PROJECT = 15
TRUNC = 200

SKIP_DISPLAY = {"exit", "quit", "q", "clear", "/exit", "/clear", "/model", "/config"}


def d(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def claude_code():
    projects = defaultdict(lambda: {"count": 0, "first": None, "last": None, "recent": []})
    path = os.path.join(HOME, ".claude", "history.jsonl")
    with open(path) as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = (e.get("display") or "").strip()
            if not text or text in SKIP_DISPLAY:
                continue
            ts = e["timestamp"] / 1000
            p = projects[e.get("project") or "?"]
            p["count"] += 1
            p["first"] = min(p["first"] or ts, ts)
            p["last"] = max(p["last"] or ts, ts)
            if NOW - ts < RECENT_DAYS * 86400:
                p["recent"].append(text.replace("\n", " ")[:TRUNC])

    lines = ["## Claude Code 프로젝트별 활동 (전체 기간)", ""]
    for proj, p in sorted(projects.items(), key=lambda x: -x[1]["last"]):
        days_ago = int((NOW - p["last"]) / 86400)
        lines.append(f"### {proj}")
        lines.append(f"- 프롬프트 {p['count']}건, {d(p['first'])} ~ {d(p['last'])} (마지막 활동 {days_ago}일 전)")
        for t in p["recent"][-MAX_PROMPTS_PER_PROJECT:]:
            lines.append(f"  - {t}")
        lines.append("")
    return "\n".join(lines)


def _codex_session_meta(path):
    """rollout 파일 첫 줄의 session_meta에서 (cwd, ts, is_subagent) 추출."""
    with open(path) as f:
        first = f.readline()
    e = json.loads(first)
    p = e.get("payload") or {}
    ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
    src = p.get("source")
    is_sub = isinstance(src, dict) and "subagent" in src
    return p.get("cwd") or "?", ts, is_sub


# 서브에이전트 세션에 섞여 들어오는 Codex 내부 보일러플레이트 — 사용자 의도가 아니다
CODEX_NOISE = (
    "The following is the Codex agent history",
    "# Files mentioned by the user:",
    "You are assessing",
    "<in-app-browser-context",
)


def _codex_user_messages(path, limit=3, max_lines=500):
    msgs = []
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= max_lines or len(msgs) >= limit:
                break
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = e.get("payload") or {}
            if p.get("type") == "user_message":
                t = str(p.get("message") or "").strip().replace("\n", " ")
                if t and not t.startswith(CODEX_NOISE):
                    msgs.append(t[:TRUNC])
    return msgs


def codex():
    root = os.path.join(HOME, ".codex", "sessions")
    if not os.path.isdir(root):
        return ""
    projects = defaultdict(lambda: {"count": 0, "sub": 0, "first": None, "last": None, "recent": []})
    for dirpath, _, files in os.walk(root):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(dirpath, name)
            try:
                cwd, ts, is_sub = _codex_session_meta(path)
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                continue
            p = projects[cwd]
            p["count"] += 1
            p["sub"] += is_sub
            p["first"] = min(p["first"] or ts, ts)
            p["last"] = max(p["last"] or ts, ts)
            # 서브에이전트 세션도 반드시 포함한다. Codex Desktop에서 굴리는 프로젝트는
            # 세션의 99%가 서브에이전트라, 이걸 빼면 최다 활동 프로젝트의 내용이 통째로 비어
            # 프로필에서 과소평가된다(fountain-pen: 7일간 187세션 중 186이 서브에이전트).
            # 다만 서브에이전트 메시지는 사용자가 아닌 상위 에이전트가 쓴 지시문이므로 1건만 샘플링.
            if NOW - ts < RECENT_DAYS * 86400:
                p["recent"] += _codex_user_messages(path, limit=1 if is_sub else 3)

    lines = ["## Codex 프로젝트별 활동 (전체 기간, 세션 단위)", ""]
    for proj, p in sorted(projects.items(), key=lambda x: -x[1]["last"]):
        days_ago = int((NOW - p["last"]) / 86400)
        lines.append(f"### {proj}")
        lines.append(
            f"- 세션 {p['count']}건(서브에이전트 {p['sub']} 포함), "
            f"{d(p['first'])} ~ {d(p['last'])} (마지막 활동 {days_ago}일 전)"
        )
        # 서브에이전트는 부모의 첫 메시지를 그대로 물려받아 같은 문장이 수십 번 반복된다 — 중복 제거
        seen_msg, uniq = set(), []
        for t in p["recent"]:
            if t not in seen_msg:
                seen_msg.add(t)
                uniq.append(t)
        for t in uniq[-MAX_PROMPTS_PER_PROJECT:]:
            lines.append(f"  - {t}")
        lines.append("")
    return "\n".join(lines)


def active_projects(days=7, min_activity=3):
    """최근 N일간 의미 있게 활동한 프로젝트의 basename 집합."""
    names, cutoff = set(), NOW - days * 86400
    hist = os.path.join(HOME, ".claude", "history.jsonl")
    counts = defaultdict(int)
    with open(hist) as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e["timestamp"] / 1000 >= cutoff and (e.get("display") or "").strip() not in SKIP_DISPLAY:
                counts[e.get("project") or "?"] += 1

    root = os.path.join(HOME, ".codex", "sessions")
    for dirpath, _, files in os.walk(root):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            try:
                cwd, ts, _ = _codex_session_meta(os.path.join(dirpath, name))
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                continue
            if ts >= cutoff:
                counts[cwd] += 1

    # 실제 프로젝트가 아닌 경로는 제외한다. 특히 ~/Documents/Codex/<날짜>/ 는 Codex Desktop이
    # 만드는 임시 작업 폴더라, 걸러내지 않으면 프로필에 실릴 리 없는 이름이 매일 누락으로 잡혀
    # 재생성이 무한히 트리거된다.
    skip = (
        os.path.join(HOME, "Documents", "Codex"),
        os.path.join(HOME, "Library"),
        "/private/tmp",
        "/tmp",
        "/var/folders",
    )
    for proj, n in counts.items():
        if n >= min_activity and proj not in ("?", HOME) and not proj.startswith(skip):
            names.add(os.path.basename(proj.rstrip("/")))
    return names


if __name__ == "__main__":
    # --check FILE...  : 최근 활동 프로젝트 중 해당 문서들에 언급되지 않은 것을 출력.
    # 하나라도 빠졌으면 exit 1 → 호출자가 프로필 재생성을 트리거한다.
    # --list : 최근 활동 프로젝트 목록. 리포트 프롬프트에 커버리지 체크리스트로 주입한다.
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        print("\n".join(f"- {n}" for n in sorted(active_projects(days=14))))
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        docs = " ".join(open(p).read() for p in sys.argv[2:] if os.path.exists(p))
        missing = sorted(n for n in active_projects() if n not in docs)
        print("\n".join(missing))
        sys.exit(1 if missing else 0)

    print(f"# 코딩 에이전트 사용 기록 다이제스트 (생성: {d(NOW)})\n")
    print(claude_code())
    print(codex())
