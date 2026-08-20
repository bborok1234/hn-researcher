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
        self.assertEqual(out["o/r"]["푸시"], 2)
        self.assertEqual(out["o/r"]["PR"], 1)
        self.assertGreater(out["o/r"]["last"], 0)

    def test_stops_on_short_page(self):
        """4페이지는 422로 죽는다. 100건 미만이 오면 더 부르지 않는다."""
        calls = self._fake([[self._ev("PushEvent", "o/r")]])
        bp.github_events()
        self.assertEqual(len([c for c in calls if "events" in c]), 1)

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


if __name__ == "__main__":
    unittest.main()
