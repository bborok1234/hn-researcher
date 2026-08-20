"""git·GitHub·편집기 신호의 결정론적 부분만 검증. 네트워크와 gh 호출 자체는 테스트하지 않는다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_profile as bp  # noqa: E402


class TestGitActivity(unittest.TestCase):
    def test_non_repo_skipped_and_repo_measured(self):
        """대화만 한 레포와 코드가 나간 레포를 가르는 것이 이 신호의 존재 이유다.
        git이 아닌 경로가 섞여도 죽지 않아야 한다 — 에이전트 기록의 cwd는 레포가 아닐 수 있다."""
        with tempfile.TemporaryDirectory() as d:
            repo, plain = os.path.join(d, "repo"), os.path.join(d, "plain")
            os.makedirs(repo)
            os.makedirs(plain)
            env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e",
                   "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e"}
            for args in (("init", "-b", "feat/topic"), ("config", "user.email", "t@e"),
                         ("commit", "--allow-empty", "-m", "x")):
                subprocess.run(("git", "-C", repo) + args, check=True,
                               capture_output=True, env=env)

            out = bp.git_activity([repo, plain, os.path.join(d, "gone")])

            self.assertEqual(list(out), [repo])
            self.assertEqual(out[repo]["commits"], 1)
            self.assertEqual(out[repo]["branch"], "feat/topic")  # 브랜치명이 주제를 말한다

    def test_only_my_commits_counted(self):
        """팀 레포에서 전체 커밋을 세면 남의 활동이 섞인다 — '내 활동만' 선을 넘는다."""
        with tempfile.TemporaryDirectory() as d:
            base = {"GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "me@e"}
            subprocess.run(("git", "-C", d, "init"), check=True, capture_output=True)
            subprocess.run(("git", "-C", d, "config", "user.email", "me@e"),
                           check=True, capture_output=True)
            for email in ("me@e", "other@e", "other@e"):
                subprocess.run(("git", "-C", d, "commit", "--allow-empty", "-m", email), check=True,
                               capture_output=True,
                               env={**os.environ, **base, "GIT_AUTHOR_NAME": "A",
                                    "GIT_AUTHOR_EMAIL": email})
            self.assertEqual(bp.git_activity([d])[d]["commits"], 1)

    def test_empty_user_email_counts_nothing(self):
        """버그: user.email이 비면 `--author=`가 빈 정규식이 되어 모든 저자에 매칭된다.
        팀 레포의 남의 커밋이 전부 내 것으로 집계돼 '내 활동만' 선을 넘었다."""
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(("git", "-C", d, "init"), check=True, capture_output=True)
            for email in ("a@b", "other@x", "other@x"):
                subprocess.run(("git", "-C", d, "-c", f"user.email={email}", "-c", "user.name=A",
                                "commit", "--allow-empty", "-m", email),
                               check=True, capture_output=True)
            self.assertEqual(bp.git_activity([d])[d]["commits"], 0)  # 3이 아니다


class TestFocus(unittest.TestCase):
    """집중도 감쇠. focus()는 순수 함수라 목킹 없이 값만 넣어 검증한다."""

    def setUp(self):
        self._now, bp.NOW = bp.NOW, 1_800_000_000.0

    def tearDown(self):
        bp.NOW = self._now

    def _ago(self, days, n=1):
        return [bp.NOW - days * 86400] * n

    def test_recent_few_beats_old_many(self):
        """이 항목의 존재 이유. 총량으로 재면 '2주 전에 몰아서 한 것'과
        '어제부터 붙어 있는 것'이 같은 값이 나온다 — 그 구분이 목적이다."""
        self.assertGreater(bp.decay(self._ago(0, 5)), bp.decay(self._ago(14, 200)))

    def test_same_count_recent_wins(self):
        self.assertGreater(bp.decay(self._ago(1, 10)), bp.decay(self._ago(7, 10)))

    def test_future_timestamp_not_amplified(self):
        """시계가 틀어져 미래 시각이 들어오면 exp(양수)로 폭발한다 — 1로 막는다."""
        self.assertAlmostEqual(bp.decay([bp.NOW + 86400]), 1.0)

    def test_ranks_by_all_signals(self):
        """에이전트 활동이 적어도 커밋·GitHub·편집기가 붙으면 위로 온다.
        로컬 프롬프트 19건짜리 프로젝트가 GitHub PR로 승격된 실제 사례가 이 모양이다."""
        events = {"/p/quiet": self._ago(0, 3), "/p/chatty": self._ago(10, 300)}
        git = {"/p/quiet": {"ts": self._ago(0, 5)}}
        gh = {"o/quiet": {"ts": self._ago(0, 8)}}
        ranked = bp.focus(events, git, gh, ["/p/quiet"], "/p/quiet")
        self.assertEqual(ranked[0][0], "quiet")
        self.assertIn("편집기 마지막 활성 창", ranked[0][1])

    def test_floor_drops_tail(self):
        """감쇠를 걸면 '2주 전에 한 번 만진 것'이 꼬리로 남는다. 순위에 넣으면 패딩이다."""
        events = {"/p/live": self._ago(0, 100), "/p/stale": self._ago(13, 1)}
        names = [n for n, _ in bp.focus(events, {}, {}, [], "")]
        self.assertEqual(names, ["live"])

    def test_empty_input_is_not_fatal(self):
        self.assertEqual(bp.focus({}, {}, {}, [], ""), [])


class TestGithubEvents(unittest.TestCase):
    def setUp(self):
        self._gh = bp._gh

    def tearDown(self):
        bp._gh = self._gh

    def _fake(self, pages):
        calls = []

        def gh(path):
            calls.append(path)
            if path == "user":
                return {"login": "me"}
            return pages.pop(0) if pages else []

        bp._gh = gh
        return calls

    @staticmethod
    def _ev(type_, repo, when="2026-08-20T01:00:00Z"):
        return {"type": type_, "repo": {"name": repo}, "created_at": when}

    def test_aggregates_and_drops_noise(self):
        """Watch·Fork는 작업 신호가 아니다. 같은 레포의 여러 타입은 한 줄로 합친다."""
        self._fake([[self._ev("PushEvent", "o/r"), self._ev("PushEvent", "o/r"),
                     self._ev("PullRequestEvent", "o/r"), self._ev("WatchEvent", "o/other")]])
        out = bp.github_events()
        self.assertEqual(set(out), {"o/r"})
        self.assertEqual(out["o/r"]["counts"]["푸시"], 2)
        self.assertEqual(out["o/r"]["counts"]["PR"], 1)
        self.assertEqual(len(out["o/r"]["ts"]), 3)

    def test_stops_on_short_page(self):
        """4페이지는 422로 죽는다. 100건 미만이 오면 더 부르지 않는다."""
        calls = self._fake([[self._ev("PushEvent", "o/r")]])
        bp.github_events()
        self.assertEqual(len([c for c in calls if "events" in c]), 1)

    def test_malformed_event_dropped_not_fatal(self):
        """외부 서비스 구조는 믿지 않는다. 이벤트 한 건이 이상해서 프로필 생성
        전체가 죽으면 안 된다 — 그 한 건만 버리고 나머지는 살린다."""
        self._fake([[None, "문자열", {"type": "PushEvent"},
                     {"type": "PushEvent", "repo": {"name": "o/r"}, "created_at": "깨진값"},
                     self._ev("PushEvent", "o/r")]])
        out = bp.github_events()
        self.assertEqual(out["o/r"]["counts"]["푸시"], 1)

    def test_no_gh_returns_empty(self):
        """gh가 없거나 미인증이어도 다이제스트는 나와야 한다."""
        bp._gh = lambda path: None
        self.assertEqual(bp.github_events(), {})


class TestVscodeWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._home, bp.HOME = bp.HOME, self.tmp.name
        self.dir = os.path.join(self.tmp.name, "Library", "Application Support", "Code",
                               "User", "globalStorage")

    def tearDown(self):
        bp.HOME = self._home
        self.tmp.cleanup()

    def test_active_window_separated_and_path_unquoted(self):
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, "storage.json"), "w") as f:
            json.dump({"windowsState": {
                "lastActiveWindow": {"folder": "file:///Users/me/my%20proj"},
                "openedWindows": [{"folder": "file:///Users/me/other"}, {"backupPath": "/x"}],
            }}, f)
        opened, active = bp.vscode_windows()
        self.assertEqual(active, "/Users/me/my proj")     # %20을 안 풀면 이름이 깨진다
        self.assertEqual(opened, ["/Users/me/other"])     # folder 없는 창은 버린다

    def test_missing_file_is_not_fatal(self):
        self.assertEqual(bp.vscode_windows(), ([], ""))

    def test_wrong_shape_is_not_fatal(self):
        """JSON 문법은 맞고 구조만 다른 경우 — 파일 존재·JSON 유효성만 막으면 여기서 터진다."""
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, "storage.json"), "w") as f:
            json.dump({"windowsState": {"openedWindows": {"a": 1}, "lastActiveWindow": 7}}, f)
        self.assertEqual(bp.vscode_windows(), ([], ""))


if __name__ == "__main__":
    unittest.main()
