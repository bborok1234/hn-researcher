#!/bin/zsh
# 스케줄만 해제한다. 생성된 리포트·프로필은 그대로 둔다(지우려면 직접).
cd "$(dirname "$0")"
LABEL="com.$(id -un).hn-researcher"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "스케줄 해제됨" || echo "등록된 스케줄이 없습니다"
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "리포트와 PROFILE.md는 남아 있습니다: $PWD"
