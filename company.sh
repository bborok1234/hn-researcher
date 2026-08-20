#!/bin/zsh
# 사용 기록에서 회사 사업 맥락을 뽑아 COMPANY.md 생성. 설정은 config.sh.
set -e
cd "$(dirname "$0")"
[ -f config.sh ] && source ./config.sh

python3 build_profile.py > digest-profile.md

claude -p --model "${DAILY_MODEL:-sonnet}" --safe-mode "아래는 $COMPANY_NAME 구성원의 Claude Code / Codex 사용 기록 다이제스트다.
이 사람이 회사에서 실제로 만들고 있는 것들을 근거로 **회사의 사업 맥락**을 정리하라.
개인 사이드 프로젝트는 제외하고 회사 업무(경로에 \"$COMPANY_DIR_HINT\"가 들어간 프로젝트)만 다룬다.
출력은 markdown 본문만 (인사말 없이).

섹션:
1. **회사 정체성** — 무슨 회사이고 누가 만들었는지, 도메인 전문성의 원천
2. **제품 포트폴리오** — 진행 중/중단된 제품 각각이 무엇을 푸는지, 현재 단계
3. **보유 자산** — 남들이 쉽게 못 갖는 것 (도메인 전문가, 데이터, 채널, 기술 자산, 레퍼런스)
4. **고객·채널** — 실제로 거론된 고객사·파트너·수주처
5. **약점·공백** — 반복적으로 막히는 지점, 아직 없는 역량

각 항목에 근거(프로젝트명, 날짜, 프롬프트 요지)를 들고, 추측은 '추정'이라 표시하라.
맨 위에 '<!-- company.sh로 자동 생성: $(date +%F) -->' 주석을 넣어라.

$(cat digest-profile.md)" > COMPANY.md

echo "COMPANY.md 갱신 완료"
