#!/bin/zsh
# 회사 사업화 심층 리포트 (주 1회). daily.sh가 월요일에 호출한다.
set -e
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")"
mkdir -p logs
[ -f config.sh ] && source ./config.sh
WEEKLY_MODEL="${WEEKLY_MODEL:-fable}"

DATE=$(date +%F)
[ -f "report-company-$DATE.html" ] && exit 0

[ -f COMPANY.md ] || ./company.sh

# 주간 digest에서 도메인 관련 줄만 추린다.
# ponytail: 1주치 전량(1MB+)을 넣으면 컨텍스트 낭비 — 키워드 1차 필터 후 LLM이 판단.
KEYWORDS="${COMPANY_KEYWORDS:?config.sh에 COMPANY_KEYWORDS가 필요합니다}"

FILTERED=$(cat $(ls -t digest-2*.md | head -7) 2>/dev/null | grep -iE "$KEYWORDS" | sort -u || true)
RECENT_REPORTS=$(cat $(ls -t report-2*.md 2>/dev/null | head -7) 2>/dev/null || true)

echo "도메인 관련 게시물 $(echo "$FILTERED" | grep -c '^-' || echo 0)건 추출"

# 주 1회 심층 분석이라 상위 모델 유지 (규제·사업성 판단이 들어간다). 일일은 sonnet.
MODEL="$WEEKLY_MODEL" DISALLOW="Bash,Read,Write,Edit,Glob,Grep,Task,TodoWrite,NotebookEdit" ./gen_report.sh "report-company-$DATE.md" <<EOF
$(sed -e "s|{{COMPANY_NAME}}|$COMPANY_NAME|g" -e "s|{{COMPANY_DOMAIN}}|$COMPANY_DOMAIN|g" prompt-company.md)

## 회사 맥락
$(cat COMPANY.md)

## 최근 1주 HN 헬스케어·의료 관련 게시물
$FILTERED

## 같은 기간 개인용 리포트 (중복 제안 방지 및 맥락 참고)
$RECENT_REPORTS
EOF

python3 to_html.py "report-company-$DATE.md" > "report-company-$DATE.html"
osascript -e "display notification \"$COMPANY_NAME 사업화 리포트 도착\" with title \"주간 심층 리포트 $DATE\" sound name \"Glass\"" || true
open "report-company-$DATE.html" || true
echo "회사 리포트 완료: report-company-$DATE.md"
