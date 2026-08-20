#!/bin/zsh
# install.sh가 이 파일을 config.sh로 복사한다. config.sh는 .gitignore 대상.

# 발행 시각 (24시간제). 출근 전에 리포트가 준비돼 있도록 잡는다.
PUBLISH_HOUR=6
PUBLISH_MIN=44

# 모델. 일일은 매일 도니 저렴한 쪽, 주간 심층은 상위 모델.
# 지정하지 않으면 ~/.claude/settings.json의 대화용 기본값을 물려받아
# 배치가 조용히 최상위 티어로 돌면서 사용량이 폭증한다.
DAILY_MODEL=sonnet
WEEKLY_MODEL=fable

# 주간 수익 기회 리포트 (월요일). 끄려면 0.
ENABLE_WEEKLY=1

# 리포트 완성 후 브라우저로 자동으로 열기
OPEN_BROWSER=1
