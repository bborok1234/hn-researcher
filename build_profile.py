#!/usr/bin/env python3
"""Claude Code + Codex 사용 기록에서 활동 다이제스트를 뽑아 stdout으로 출력.
PROFILE.md 생성용 원료 — profile.sh가 claude -p에 넣는다."""
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import unquote

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


def _agent_counts(days):
    """최근 N일간 에이전트 기록에 나타난 {프로젝트 절대경로: 건수}. 실제 프로젝트가 아닌 경로는 제외."""
    cutoff = NOW - days * 86400
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
    return {p: n for p, n in counts.items() if p not in ("?", HOME) and not p.startswith(skip)}


def active_projects(days=7, min_activity=3):
    """최근 N일간 의미 있게 활동한 프로젝트의 basename 집합.

    에이전트 기록만 본다. git·GitHub·편집기 신호는 다이제스트만 살찌우고 여기엔 넣지 않는다 —
    이 함수의 결과가 --check로 프로필 재생성을 트리거하므로, LLM이 프로필에 안 쓸 만한
    이름(웹에서 커밋만 한 레포 등)이 섞이면 매일 재생성이 걸린다.
    """
    return {
        os.path.basename(p.rstrip("/"))
        for p, n in _agent_counts(days).items()
        if n >= min_activity
    }


def _git(path, *args):
    """git 한 방. 실패는 빈 문자열 — 레포가 아니거나 손상돼도 다이제스트는 계속 나와야 한다."""
    try:
        r = subprocess.run(("git", "-C", path) + args, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def git_activity(paths):
    """디스크 git 스캔 — {경로: {last, commits, branch}}.

    에이전트 기록에 나온 경로만 훑는다(홈 전체를 걷지 않는다). 대화만 한 레포와
    코드가 실제로 나간 레포를 가르는 것이 목적이고, 브랜치명은 주제를 직접 말해준다.
    커밋 수는 `--author`로 내 것만 센다 — 팀 레포에서 전체를 세면 남의 활동이 섞인다.
    """
    out = {}
    for p in paths:
        if not os.path.exists(os.path.join(p, ".git")):
            continue
        ts = _git(p, "log", "-1", "--format=%at")
        if not ts.isdigit():
            continue
        # user.email이 비어 있으면 커밋 수를 세지 않는다. `--author=`는 빈 정규식이라
        # 모든 저자에 매칭돼 팀 레포의 남의 커밋이 전부 내 것으로 집계된다.
        me = _git(p, "config", "user.email")
        n = _git(p, "rev-list", "--count", "--since=2.weeks", f"--author={me}", "HEAD") if me else ""
        out[p] = {
            "last": int(ts),
            "commits": int(n) if n.isdigit() else 0,
            "branch": _git(p, "rev-parse", "--abbrev-ref", "HEAD"),
        }
    return out


# 이벤트 타입 → 다이제스트 표기. 목록에 없는 타입은 버린다(Watch·Fork 등은 작업 신호가 아니다).
GH_EVENTS = {
    "PushEvent": "푸시",
    "PullRequestEvent": "PR",
    "PullRequestReviewEvent": "리뷰",
    "PullRequestReviewCommentEvent": "리뷰코멘트",
    "IssueCommentEvent": "코멘트",
    "IssuesEvent": "이슈",
    "CreateEvent": "생성",
}


def _gh(path):
    """gh api 호출. gh가 없거나 미인증이면 None — 파이프라인은 이 신호 없이도 돌아야 한다."""
    try:
        r = subprocess.run(("gh", "api", path), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def github_events(pages=3):
    """내가 일으킨 GitHub 이벤트를 레포별로 집계 — {레포: {"last": ts, 표기: 건수}}.

    로컬 기록에 없는 것을 준다: 내가 올린 PR·리뷰·코멘트. private·조직 레포도 보인다.
    `/user/repos?sort=pushed`는 쓰지 않는다 — 남이 푸시한 팀 레포가 최신으로 올라와
    '내 활동만' 선을 넘는다. 이벤트는 actor가 나인 것만 온다.
    페이지는 3까지다 — 100건×3=300건이 상한이고 4페이지는 422로 죽는다.
    """
    me = _gh("user")
    if not isinstance(me, dict) or not me.get("login"):
        return {}
    repos = defaultdict(lambda: defaultdict(int))
    for page in range(1, pages + 1):
        batch = _gh(f"/users/{me['login']}/events?per_page=100&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        for e in batch:
            # 외부 서비스가 주는 구조는 믿지 않는다. 이벤트 하나가 이상해서
            # 프로필 생성 전체가 죽으면 안 된다 — 그 한 건만 버린다.
            try:
                label = GH_EVENTS.get(e["type"])
                repo = (e["repo"]["name"] or "").strip()
                ts = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).timestamp()
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
            if not label or not repo:
                continue
            r = repos[repo]
            r[label] += 1
            r["last"] = max(r["last"], ts)
        if len(batch) < 100:
            break
    return repos


def vscode_windows():
    """열려 있는 VS Code 창 → (경로 목록, 마지막 활성 경로).

    '지금 이 순간' 신호로 가장 순수하다. 열림/닫힘뿐이고 순위는 없지만,
    lastActiveWindow 하나는 최근성을 준다.
    """
    p = os.path.join(HOME, "Library", "Application Support", "Code", "User",
                     "globalStorage", "storage.json")

    def folder(w):
        f = ((w or {}).get("folder") or "")
        return unquote(f[len("file://"):]) if f.startswith("file://") else ""

    # 파싱까지 try 안에 둔다. 파일이 없거나 JSON이 깨진 경우만이 아니라,
    # 문법은 맞고 구조가 다른 경우(windowsState가 리스트 등)에도 죽지 않아야 한다.
    try:
        with open(p) as f:
            ws = json.load(f).get("windowsState") or {}
        opened = [f for f in (folder(w) for w in ws.get("openedWindows") or []) if f]
        return opened, folder(ws.get("lastActiveWindow"))
    except (OSError, AttributeError, KeyError, TypeError, ValueError):
        return [], ""


def signals(days=14):
    """git·GitHub·편집기 신호를 다이제스트 섹션으로. 에이전트 기록이 못 보는 것을 채운다."""
    lines = []

    git = git_activity(sorted(_agent_counts(days)))
    lines += ["## 코드가 실제로 나간 곳 (디스크 git)", ""]
    if git:
        for p, g in sorted(git.items(), key=lambda x: -x[1]["last"]):
            lines.append(
                f"- **{os.path.basename(p.rstrip('/'))}** — 내 커밋 2주간 {g['commits']}건, "
                f"브랜치 `{g['branch']}`, 마지막 커밋 {d(g['last'])}"
            )
        lines.append("")
        lines.append("커밋 0건은 대화만 하고 코드는 안 나간 레포다.")
    else:
        lines.append("(git 레포로 잡힌 경로 없음)")
    lines.append("")

    lines += ["## GitHub에서 내가 한 일 (최근 이벤트 300건까지)", ""]
    gh = github_events()
    if gh:
        for repo, counts in sorted(gh.items(), key=lambda x: -x[1]["last"]):
            kinds = " · ".join(
                f"{k} {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]) if k != "last"
            )
            lines.append(f"- **{repo}** — {kinds}, 마지막 {d(counts['last'])}")
    else:
        lines.append("(gh CLI 미설치·미인증이거나 이벤트 없음)")
    lines.append("")

    opened, active = vscode_windows()
    lines += ["## 지금 VS Code에 열려 있는 것", ""]
    if active or opened:
        if active:
            lines.append(f"- **{os.path.basename(active.rstrip('/'))}** (마지막 활성 창)")
        for p in opened:
            if p != active:
                lines.append(f"- {os.path.basename(p.rstrip('/'))}")
        lines.append("")
        lines.append("열림/닫힘뿐이고 순위는 없다. 열려 있다는 것 자체가 '지금'의 신호다.")
    else:
        lines.append("(열린 창 정보 없음)")
    return "\n".join(lines) + "\n"


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
    print(signals())
