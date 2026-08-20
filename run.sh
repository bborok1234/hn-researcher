#!/bin/zsh
# 사용법: ./run.sh              → 지금 기준 지난 24시간 (파일명은 오늘 로컬 날짜)
#        ./run.sh YYYY-MM-DD   → 특정 UTC 하루 백필
#
# 3단계로 나눠 돈다. 예전에는 한 세션에서 선별·페치·작문을 다 했는데, claude -p는
# 매 턴 대화 전체를 다시 보내므로 읽어들인 웹페이지가 계속 누적돼 회당 5.5M 토큰을 썼다.
#   1 선별  : 목록 전체를 한 번만 읽고 후보를 고른다 (도구 없음, 1턴)
#   2 수집  : 파이썬이 원문·댓글을 받아 텍스트로 정리한다 (LLM 미사용, 0 토큰)
#   3 작문  : 정리된 본문만 받아 리포트를 쓴다 (도구 없음, 1턴)
set -e
cd "$(dirname "$0")"
[ -f config.sh ] && source ./config.sh
export MODEL="${DAILY_MODEL:-sonnet}"
DATE=${1:-$(date +%F)}
mkdir -p out   # 산출물은 전부 out/ 아래. 사이드카 파일명 규약은 그대로다

python3 fetch_hn.py $1 --urls "out/urls-$DATE.json" > "out/digest-$DATE.md"
echo "1/3 수집 완료: out/digest-$DATE.md ($(grep -c '^- ' out/digest-$DATE.md)건)"

PROJECTS=$(python3 build_profile.py --list)
print -r -- "$PROJECTS" > "out/projects-$DATE.txt"   # 화면의 로스터 칩이 이 목록과 대조한다

MIN_BYTES=200 ./gen_report.sh "out/candidates-$DATE.json" <<EOF
$(cat prompt-select.md)

## 활동 중인 프로젝트 목록 (최근 14일 — 전부 검토 대상)
$PROJECTS

## 내 프로필
$(cat PROFILE.md)

## 오늘의 HN 게시물 전체 목록
$(cat out/digest-$DATE.md)
EOF

# 모델이 코드펜스를 두르는 경우가 있어 JSON 배열만 잘라낸다
python3 - "out/candidates-$DATE.json" <<'PY'
import json, re, sys
p = sys.argv[1]
raw = open(p).read()
m = re.search(r"\[.*\]", raw, re.S)
assert m, f"후보 JSON을 찾지 못함: {raw[:200]}"
json.dump(json.loads(m.group()), open(p, "w"), ensure_ascii=False)
PY
echo "2/3 선별 완료: $(python3 -c "import json;print(len(json.load(open('out/candidates-$DATE.json'))))")건"

python3 fetch_pages.py "out/candidates-$DATE.json" "out/urls-$DATE.json" > "out/pages-$DATE.md"
echo "   본문 수집 완료: $(wc -c < out/pages-$DATE.md) bytes"

./gen_report.sh "out/report-$DATE.md" <<EOF
$(cat prompt-write.md)

## 발행일
이 리포트의 발행일은 **$DATE**(한국 시간)다. 제목에 반드시 이 날짜를 쓴다.

## 활동 중인 프로젝트 목록 (최근 14일)
$PROJECTS

## 내 프로필
$(cat PROFILE.md)

## 오늘 수집한 게시물 본문
$(cat out/pages-$DATE.md)
EOF

echo "3/3 리포트 완료: out/report-$DATE.md"
