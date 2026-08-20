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

# 회사 사업화 트랙 (주 1회, 월요일). 개인 리포트만 원하면 0.
ENABLE_COMPANY=0
COMPANY_NAME="회사명"
# 회사 트랙이 다루는 영역. 리포트의 판단 기준이 된다.
COMPANY_DOMAIN="담당 사업 영역 (예: 헬스케어, 공공, 커머스)"
# 사용 기록에서 회사 업무로 분류할 디렉토리 이름 (개인 프로젝트와 구분).
COMPANY_DIR_HINT="회사업무_디렉토리명"

# 리포트 완성 후 브라우저로 자동으로 열기
OPEN_BROWSER=1
COMPANY_KEYWORDS='health|medical|clinic|hospital|patient|doctor|nurse|disease|diagnos|therap|drug|pharma|FDA|trial|bio|genom|cancer|diabet|mental|insurance|EHR|telemed|wearable|vaccine|nutrition|elder|care|의료|건강|병원|환자'
