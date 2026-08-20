#!/bin/zsh
# Claude Code + Codex 사용 기록으로 PROFILE.md를 자동 생성/갱신한다.
# 사용법: ./profile.sh
#
# LLM 호출은 gen_report.sh를 경유한다 — 재시도·출력 검증·도구 차단·stdin 처리가
# 거기 한 곳에 있다. 직접 claude -p를 부르면 그 보호가 빠지고, API가 중간에
# 끊길 때 잘린 PROFILE.md가 덮어써져 이후 모든 리포트가 깨진 프로필 위에 올라간다.
set -e
cd "$(dirname "$0")"
[ -f config.sh ] && source ./config.sh

python3 build_profile.py > digest-profile.md
echo "활동 다이제스트 생성 완료 ($(wc -l < digest-profile.md)줄)"

MIN_BYTES=500 ./gen_report.sh PROFILE.md <<EOF
$(cat prompt-profile.md)

맨 위에 '<!-- profile.sh로 자동 생성: $(date +%F). 직접 수정 가능, 재생성 시 덮어씀 -->' 주석을 넣어라.

$(cat digest-profile.md)
EOF

echo "PROFILE.md 갱신 완료"
