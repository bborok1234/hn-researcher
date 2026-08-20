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

# 작은 소스를 먼저 쓴다. HN 1,100여 줄 뒤에 59줄을 붙였더니 선별이 단 한 건도
# 집어가지 않았다 — 큐레이션된 소스가 목록 끝에서 묻힌다. 쿼터를 주는 대신 순서로 푼다.
# 실패해도 넘어간다 — 소스 추가가 아침 리포트를 잃는 이유가 되면 안 된다.
python3 sources.py $1 --digest --urls "out/urls-extra-$DATE.json" > "out/digest-$DATE.md" \
  || echo "추가 소스 실패 — HN만으로 계속" >&2
[ -f "out/urls-extra-$DATE.json" ] || echo '{}' > "out/urls-extra-$DATE.json"
python3 fetch_hn.py $1 --urls "out/urls-$DATE.json" >> "out/digest-$DATE.md"
echo "1/3 수집 완료: out/digest-$DATE.md ($(grep -c '^- ' out/digest-$DATE.md)건)"

# 릴리스는 선별을 건너뛴다 — 내가 의존하는 레포 목록을 내가 정하니 관련성이 100%고,
# 릴리스 노트가 곧 본문이라 수집 단계도 필요 없다. 3단계 프롬프트로 직접 간다.
python3 sources.py $1 --releases "${RELEASE_REPOS:-}" > "out/releases-$DATE.md" 2>/dev/null || true

PROJECTS=$(python3 build_profile.py --list)
print -r -- "$PROJECTS" > "out/projects-$DATE.txt"   # 화면의 로스터 칩이 이 목록과 대조한다

# 재심 대상: 전에 후보였지만 리포트에 못 오른 항목. 오늘 것과 동등하게 경쟁만 하고
# 별도 지면을 갖지 않는다 — 미독 백로그를 만들지 않는 것이 이 설계의 선이다.
PENDING=$(python3 knowledge.py --pending --days 14 2>/dev/null || true)
python3 knowledge.py --pending --days 14 --urls > "out/pending-urls-$DATE.json" 2>/dev/null || echo '{}' > "out/pending-urls-$DATE.json"

MIN_BYTES=200 ./gen_report.sh "out/candidates-$DATE.json" <<EOF
$(cat prompt-select.md)

## 활동 중인 프로젝트 목록 (최근 14일 — 전부 검토 대상)
$PROJECTS

## 내 프로필
$(cat PROFILE.md)

## 지난 후보 중 아직 리포트에 오르지 않은 것 (재심 대상)
$PENDING

## 오늘의 게시물 전체 목록 — Lobsters · GeekNews · Hacker News
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

python3 fetch_pages.py "out/candidates-$DATE.json" "out/urls-$DATE.json" \
  "out/urls-extra-$DATE.json" "out/pending-urls-$DATE.json" > "out/pages-$DATE.md"
echo "   본문 수집 완료: $(wc -c < out/pages-$DATE.md) bytes"

./gen_report.sh "out/report-$DATE.md" <<EOF
$(cat prompt-write.md)

## 발행일
이 리포트의 발행일은 **$DATE**(한국 시간)다. 제목에 반드시 이 날짜를 쓴다.

## 활동 중인 프로젝트 목록 (최근 14일)
$PROJECTS

## 내 프로필
$(cat PROFILE.md)

## 지난 24시간 릴리스 (선별을 거치지 않은 것 — '경고' 섹션의 주 재료)
$(cat out/releases-$DATE.md)

## 오늘 수집한 게시물 본문
$(cat out/pages-$DATE.md)
EOF

echo "3/3 리포트 완료: out/report-$DATE.md"

# 오늘 후보 전부를 주제별로 철한다. 채택/보류를 가르고, 보류가 나중에 채택되면 되살아남으로 센다.
# LLM을 쓰지 않는다 — 0토큰. 종합은 위 작문 턴에서 이미 끝났고 여기서는 철하기만 한다.
#
# 실패해도 넘어간다. 리포트는 이미 완성됐고, 여기서 죽으면 set -e에 걸려
# daily.sh가 to_html도 못 부르고 끝난다 — 철하기 하나 때문에 아침 리포트를 잃는 셈이다.
python3 knowledge.py --ingest "$DATE" || echo "누적 철하기 실패 — 리포트는 정상" >&2
