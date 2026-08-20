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

mkdir -p out
# 덮어쓰기 전에 사본을 남긴다. 손으로 고친 부분이 재생성에서 살아남게 하는 것은 아직 못 하지만,
# 최소한 무엇이 어떻게 바뀌었는지는 diff로 볼 수 있어야 한다.
# ponytail: 날짜당 하나(-n). 같은 날 두 번 돌리면 그날 첫 사본이 유지된다.
# `[ 조건 ] && cp`로 쓰지 않는다 — set -e 아래에서 조건이 거짓일 때의 종료 코드를 신경 써야 한다.
cp -n PROFILE.md "out/PROFILE-$(date +%F).md" 2>/dev/null || true

python3 build_profile.py > out/digest-profile.md
echo "활동 다이제스트 생성 완료 ($(wc -l < out/digest-profile.md)줄)"

MIN_BYTES=500 ./gen_report.sh PROFILE.md <<EOF
$(cat prompt-profile.md)

맨 위에 '<!-- profile.sh로 자동 생성: $(date +%F). 직접 수정 가능, 재생성 시 덮어씀 -->' 주석을 넣어라.

$(cat out/digest-profile.md)
EOF

echo "PROFILE.md 갱신 완료"
