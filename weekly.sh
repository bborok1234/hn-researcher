#!/bin/zsh
# 주 1회 수익 기회 리포트. daily.sh가 월요일에 일간 리포트를 낸 뒤 호출한다.
#
# 새로 긁지 않는다 — 지난 한 주에 이미 수집해 둔 자료만 다시 훑는다.
# 하루 단위로는 안 보이고 한 주를 모아야 보이는 것을 찾는 게 이 리포트의 존재 이유다.
set -e
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")"
mkdir -p logs out
[ -f config.sh ] && source ./config.sh

DATE=$(date +%F)
[ -f "out/report-weekly-$DATE.html" ] && exit 0

WEEK_REPORTS=$(cat $(ls -t out/report-2*.md 2>/dev/null | grep -v weekly | head -7) 2>/dev/null || true)
WEEK_PAGES=$(cat $(ls -t out/pages-2*.md 2>/dev/null | head -7) 2>/dev/null || true)

if [ -z "$WEEK_REPORTS" ]; then
  echo "지난 주 일간 리포트가 없어 건너뜀"
  exit 0
fi

MODEL="${WEEKLY_MODEL:-fable}" ./gen_report.sh "out/report-weekly-$DATE.md" <<EOF
$(cat prompts/weekly.md)

## 발행일
이 리포트의 발행일은 **$DATE**(한국 시간)다.

## 내 프로필
$(cat PROFILE.md)

## 지난 한 주 일간 리포트
$WEEK_REPORTS

## 같은 기간 수집된 게시물 본문
$WEEK_PAGES
EOF

python3 to_html.py "out/report-weekly-$DATE.md" > "out/report-weekly-$DATE.html"
osascript -e "display notification \"주간 수익 기회 리포트\" with title \"hn-researcher $DATE\" sound name \"Glass\"" || true
[ "${OPEN_BROWSER:-1}" = "1" ] && { open "out/report-weekly-$DATE.html" || true; }
echo "주간 리포트 완료: out/report-weekly-$DATE.md"
exit 0
