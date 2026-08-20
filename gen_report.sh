#!/bin/zsh
# claude -p 호출 + 재시도 + 검증. 사용법: <프롬프트를 stdin으로> gen_report.sh 출력경로
# API가 중간에 끊기면 잘린 결과가 남으므로, 검증 통과한 것만 최종 경로로 옮긴다.
#
# 환경변수:
#   MODEL      기본 sonnet. 지정하지 않으면 ~/.claude/settings.json의 대화용 기본값
#              (2026-08 기준 claude-fable-5[1m])을 물려받아 배치가 최상위 티어로 돈다.
#   DISALLOW   거부할 도구 목록. 기본은 전부 거부 — 도구를 쓰면 매 턴 컨텍스트가 누적돼
#              비용이 폭증한다(일일 리포트가 이 때문에 회당 5.5M을 썼다).
#              웹 조사가 필요한 주간 리포트만 WebFetch·WebSearch를 빼고 넘긴다.
#              주의 1: --allowedTools ""는 무시되므로(모델이 Bash를 실제로 실행함) 반드시 거부 목록을 쓴다.
#              주의 2: --disallowedTools는 가변 인자라 뒤따르는 인자를 도구 이름으로 먹는다.
#                      반드시 쉼표로 구분하고, 프롬프트를 이 옵션보다 앞에 둔다.
#   MIN_BYTES  기본 1000. 이보다 작으면 실패로 보고 재시도.
OUT="$1"
PROMPT=$(cat)
MODEL="${MODEL:-sonnet}"
DISALLOW="${DISALLOW:-Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,TodoWrite,NotebookEdit}"
MIN_BYTES="${MIN_BYTES:-1000}"

for attempt in 1 2 3; do
  # --safe-mode: 스킬·플러그인·MCP 정의를 시스템 프롬프트에서 뺀다 (턴당 50K→29K 토큰).
  # 배치는 이 프로젝트의 스크립트만 쓰므로 잃는 것이 없다.
  claude -p "$PROMPT" --model "$MODEL" --safe-mode --disallowedTools "$DISALLOW" </dev/null > "$OUT.tmp" || true
  if [ -s "$OUT.tmp" ] && [ "$(wc -c < "$OUT.tmp")" -ge "$MIN_BYTES" ] \
     && ! grep -qi '^API Error' "$OUT.tmp"; then
    mv "$OUT.tmp" "$OUT"
    exit 0
  fi
  echo "생성 실패 (시도 $attempt/3): $(head -c 120 "$OUT.tmp" 2>/dev/null)" >&2
  [ "$attempt" -lt 3 ] && sleep 60
done

rm -f "$OUT.tmp"
echo "3회 모두 실패 — 포기" >&2
exit 1
