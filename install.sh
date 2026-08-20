#!/bin/zsh
# hn-researcher 설치. 몇 번을 실행해도 같은 결과가 되도록(idempotent) 작성.
# 하는 일: 의존성 확인 → config.sh 생성 → 첫 프로필 생성 → launchd 등록 → 첫 리포트 발행
set -e
cd "$(dirname "$0")"
DIR="$PWD"
LABEL="com.$(id -un).hn-researcher"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

say() { print -P "%F{cyan}▸%f $1"; }
die() { print -P "%F{red}✗%f $1"; exit 1; }

# ── 1. 의존성 ────────────────────────────────────────────────
say "의존성 확인"
[ "$(uname)" = "Darwin" ] || die "macOS 전용입니다 (launchd·osascript 사용). 리눅스는 cron으로 바꿔야 합니다."
command -v python3 >/dev/null || die "python3가 없습니다. Xcode Command Line Tools를 설치하세요: xcode-select --install"
command -v claude  >/dev/null || die "claude CLI가 없습니다. https://claude.com/claude-code 에서 설치 후 다시 실행하세요."
claude -p "Reply with exactly: OK" --model sonnet --safe-mode --disallowedTools "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,TodoWrite,NotebookEdit" </dev/null >/dev/null 2>&1 \
  || die "claude CLI 인증이 안 돼 있습니다. 터미널에서 'claude' 실행 후 로그인하고 다시 시도하세요."

# 사용 기록이 없으면 개인화가 불가능하다 — 이 도구의 전제
[ -f "$HOME/.claude/history.jsonl" ] || [ -d "$HOME/.codex/sessions" ] \
  || die "Claude Code나 Codex 사용 기록이 없습니다. 며칠 사용한 뒤 설치하세요 — 그 기록이 개인화의 재료입니다."

# ── 2. 설정 ──────────────────────────────────────────────────
if [ -f config.sh ]; then
  say "config.sh 이미 있음 — 유지합니다"
else
  cp config.example.sh config.sh
  say "config.sh 생성 — 발행 시각·회사 트랙을 바꾸려면 이 파일을 편집하세요"
fi
source ./config.sh

# ── 3. 프로필 (사용 기록 → 나에 대한 이해) ──────────────────────
if [ -f PROFILE.md ]; then
  say "PROFILE.md 이미 있음 — 유지합니다 (다시 만들려면: ./profile.sh)"
else
  say "사용 기록에서 프로필 생성 중 (1~2분)"
  ./profile.sh
fi

# ── 4. 스케줄 등록 ────────────────────────────────────────────
say "매일 $(printf '%02d:%02d' $PUBLISH_HOUR $PUBLISH_MIN) 발행으로 launchd 등록"
mkdir -p "$HOME/Library/LaunchAgents" logs
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/zsh</string><string>$DIR/daily.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$PUBLISH_HOUR</integer><key>Minute</key><integer>$PUBLISH_MIN</integer></dict>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.err</string>
  <key>StandardOutPath</key><string>$DIR/logs/launchd.out</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || die "launchd 등록 실패"

# cron은 쓰지 않는다 — GUI 세션 밖이라 로그인 키체인에 접근하지 못해
# claude CLI가 'OAuth session expired'로 반드시 실패한다.

# ── 5. 첫 리포트 ──────────────────────────────────────────────
say "첫 리포트 생성 중 (2분쯤 걸립니다)"
./daily.sh

cat <<DONE

  설치 완료.

  매일 $(printf '%02d:%02d' $PUBLISH_HOUR $PUBLISH_MIN)에 리포트가 만들어지고 브라우저로 열립니다.
  오늘 리포트: $DIR/out/report-$(date +%F).html

  자주 쓰는 명령
    ./daily.sh        지금 바로 발행 (오늘 치가 있으면 건너뜀)
    ./profile.sh      프로필 다시 생성 — 추천이 안 맞으면 PROFILE.md를 직접 고쳐도 됩니다
    ./uninstall.sh    스케줄 해제

  주의: 시스템 설정 → 일반 → 로그인 항목 및 확장 프로그램에서
  'zsh' 항목이 켜져 있어야 예약 실행이 됩니다. 꺼져 있으면 아침에 조용히 안 돕니다.
DONE
