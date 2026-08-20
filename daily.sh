#!/bin/zsh
# launchd가 매일 아침 실행. 마지막 완결된 UTC 하루치 HN → 뉴스레터 발행.
set -e
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")"
mkdir -p logs out
[ -f config.sh ] && source ./config.sh
ENABLE_WEEKLY="${ENABLE_WEEKLY:-1}"; OPEN_BROWSER="${OPEN_BROWSER:-1}"

DATE=$(date +%F)
# 실행 흔적 — 스케줄러가 정말 불렀는지 확인용 (가드보다 먼저 남겨야 의미가 있다)
echo "$(date +'%F %T') invoked (ppid=$PPID)" >> logs/runs.log

# 잠금: mkdir은 원자적이라 동시에 뜬 두 프로세스 중 하나만 통과한다.
# (파일 존재 확인만으로는 막지 못한다 — 리포트가 만들어지기까지 7분 걸려 그 사이가 무방비였다)
LOCK=logs/.lock
# 2시간 넘은 잠금은 죽은 프로세스가 남긴 것으로 보고 회수
# ponytail: 시각 비교로 충분. 진짜 PID 추적이 필요해지면 그때 flock으로 교체.
[ -d "$LOCK" ] && [ -z "$(find "$LOCK" -maxdepth 0 -mmin -120)" ] && rmdir "$LOCK"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date +'%F %T') skipped (다른 실행이 진행 중)" >> logs/runs.log
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# 오늘 치가 이미 있으면 종료
[ -f "out/report-$DATE.html" ] && exit 0

# 프로필·회사맥락 갱신
#  - 월요일: 정기 갱신 (활발→방치 같은 '상태 변화'는 새 프로젝트 감지로는 안 잡힌다)
#  - 그 외: 프로필에 없는 프로젝트를 새로 만졌으면 그날 바로 갱신
NEW=$(python3 build_profile.py --check PROFILE.md 2>/dev/null || true)
if [ "$(date +%u)" = "1" ] || [ -n "$NEW" ]; then
  [ -n "$NEW" ] && echo "새 프로젝트 감지: $(echo $NEW | tr '\n' ' ')" >> "logs/$DATE.log"
  ./profile.sh >> "logs/$DATE.log" 2>&1
fi

./run.sh >> "logs/$DATE.log" 2>&1   # 인자 없음 = 실행 시점 기준 지난 24시간
python3 to_html.py "out/report-$DATE.md" > "out/report-$DATE.html"

# 알림/열기 실패가 리포트 생성을 무효로 만들지는 않는다
HEADLINE=$(grep -m1 '^\*\*' "out/report-$DATE.md" | tr -d '*' | cut -c1-80 || true)
osascript -e "display notification \"${HEADLINE:-리포트 도착}\" with title \"HN 스카우트 $DATE\" sound name \"Glass\"" || true
[ "$OPEN_BROWSER" = "1" ] && { open "out/report-$DATE.html" || true; }

# 월요일: 주간 수익 기회 리포트 (일간이 완성된 뒤 실행 — 중복 제안 방지에 참고한다)
# if로 쓴다 — `[ ... ] && cmd`를 마지막 줄에 두면 월요일이 아닌 날 스크립트가 실패(1)로 끝난다
if [ "$(date +%u)" = "1" ] && [ "$ENABLE_WEEKLY" = "1" ]; then
  ./weekly.sh >> "logs/$DATE.log" 2>&1
fi

exit 0
