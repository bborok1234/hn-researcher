"""프로필 집계 회귀 테스트. 각 테스트는 실제로 겪은 버그 하나에 대응한다."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_profile as bp  # noqa: E402


def write_session(root, day, name, cwd, ts, subagent=False):
    d = os.path.join(root, ".codex", "sessions", "2026", "08", day)
    os.makedirs(d, exist_ok=True)
    meta = {
        "timestamp": ts,
        "type": "session_meta",
        "payload": {"cwd": cwd, **({"source": {"subagent": {"depth": 1}}} if subagent else {})},
    }
    path = os.path.join(d, f"rollout-{name}.jsonl")
    with open(path, "w") as f:
        f.write(json.dumps(meta) + "\n")
        f.write(json.dumps({"payload": {"type": "user_message", "message": "실제 사용자 요청"}}) + "\n")
    return path


class TestCodexNoise(unittest.TestCase):
    def test_boilerplate_filtered(self):
        """버그: 서브에이전트 세션에 Codex 내부 보일러플레이트가 섞여 들어와
        프로필이 사용자 의도가 아닌 시스템 텍스트를 근거로 삼았다."""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.jsonl")
            with open(p, "w") as f:
                f.write(json.dumps({"payload": {"type": "user_message",
                        "message": "The following is the Codex agent history whose request..."}}) + "\n")
                f.write(json.dumps({"payload": {"type": "user_message",
                        "message": "<in-app-browser-context source=\"x\">"}}) + "\n")
                f.write(json.dumps({"payload": {"type": "user_message", "message": "진짜 요청"}}) + "\n")
            self.assertEqual(bp._codex_user_messages(p, limit=5), ["진짜 요청"])


class TestActiveProjects(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(__file__)))
        self.home, self._home, self._now = self.tmp.name, bp.HOME, bp.NOW
        bp.HOME = self.tmp.name
        bp.NOW = time.time()
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        open(os.path.join(self.home, ".claude", "history.jsonl"), "w").close()

    def tearDown(self):
        bp.HOME, bp.NOW = self._home, self._now
        self.tmp.cleanup()

    def _now_iso(self):
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(bp.NOW - 3600))

    def test_temp_codex_dirs_excluded(self):
        """버그: Codex Desktop이 ~/Documents/Codex/<날짜>/ 아래 만드는 임시 폴더가
        프로젝트로 잡혀, 프로필에 실릴 리 없는 이름이 매일 누락으로 감지되며
        프로필 재생성이 무한히 트리거됐다(비용 누출)."""
        for i in range(3):
            write_session(self.home, "20", f"real{i}",
                          os.path.join(self.home, "myworks", "alpha-proj"), self._now_iso())
            write_session(self.home, "20", f"tmp{i}",
                          os.path.join(self.home, "Documents", "Codex", "2026-08-18", "gu"),
                          self._now_iso())
        names = bp.active_projects(days=7, min_activity=3)
        self.assertIn("alpha-proj", names)
        self.assertNotIn("gu", names)

    def test_subagent_sessions_counted(self):
        """버그: 서브에이전트 세션을 빼면 Codex Desktop 주력 프로젝트가 통째로
        누락된다(한 프로젝트가 7일간 187건 중 186건이 서브에이전트였다)."""
        for i in range(4):
            write_session(self.home, "20", f"sub{i}",
                          os.path.join(self.home, "skunkworks", "beta-proj"),
                          self._now_iso(), subagent=True)
        self.assertIn("beta-proj", bp.active_projects(days=7, min_activity=3))

    def test_below_threshold_ignored(self):
        write_session(self.home, "20", "one",
                      os.path.join(self.home, "myworks", "tiny-proj"), self._now_iso())
        self.assertNotIn("tiny-proj", bp.active_projects(days=7, min_activity=3))


if __name__ == "__main__":
    unittest.main()
