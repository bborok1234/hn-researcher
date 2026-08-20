"""HN 밖 소스. 네트워크는 테스트하지 않는다 — 파싱과 창 필터만."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources as s  # noqa: E402

DAY = 1_800_000_000.0          # 창: [DAY, DAY+86400)
IN = "2027-01-15T12:00:00Z"    # 아래 두 상수는 DAY 창 안/밖의 실제 시각
OUT = "2027-02-20T12:00:00Z"


def _epoch(iso):
    return s._ts(iso)


class TestLobsters(unittest.TestCase):
    def raw(self, **over):
        item = {"short_id": "abc123", "title": "제목", "score": 42, "comment_count": 7,
                "tags": ["rust", "web"], "url": "https://x.dev/a",
                "comments_url": "https://lobste.rs/s/abc123", "created_at": IN}
        item.update(over)
        return json.dumps([item])

    def setUp(self):
        self.start = _epoch(IN) - 3600
        self.end = self.start + 86400

    def test_tags_go_into_title(self):
        """태그로 걸러내지 않고 제목 옆에 붙여 넘긴다 — 무엇을 버릴지는 프롬프트가 정한다."""
        got = s.lobsters(self.raw(), self.start, self.end)
        self.assertEqual(got[0]["id"], "lobabc123")
        self.assertIn("[rust]", got[0]["title"])
        self.assertEqual((got[0]["points"], got[0]["comments"]), (42, 7))

    def test_self_post_uses_discussion_url(self):
        """외부 URL이 없는 자체 게시물 — HN의 url_map과 같은 방식으로 토론 페이지를 쓴다."""
        got = s.lobsters(self.raw(url=""), self.start, self.end)
        self.assertEqual(got[0]["url"], "https://lobste.rs/s/abc123")

    def test_outside_window_dropped(self):
        """hottest.json은 시간 필터가 없다. 창 밖 항목이 섞여 들어온다."""
        self.assertEqual(s.lobsters(self.raw(created_at=OUT), self.start, self.end), [])


class TestGeekNews(unittest.TestCase):
    ATOM = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns='http://www.w3.org/2005/Atom'>
      <entry>
        <title>한국어 제목</title>
        <link rel='alternate' href='https://news.hada.io/topic?id=32690' />
        <id>https://news.hada.io/topic?id=32690</id>
        <published>%s</published>
      </entry>
    </feed>"""

    def test_atom_not_rss(self):
        """버그: 경로가 /rss/라 RSS 2.0으로 읽었더니 `item`이 없어 조용히 0건이 됐다.
        실제로 주는 것은 Atom이다."""
        start = _epoch(IN) - 3600
        got = s.geeknews(self.ATOM % IN, start, start + 86400)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["id"], "gn32690")
        self.assertEqual(got[0]["title"], "한국어 제목")

    def test_zero_score_is_absence_not_unpopularity(self):
        """피드에 점수가 없다. 0으로 두고 프롬프트에 '이 소스엔 그 신호가 없다'고 알린다."""
        start = _epoch(IN) - 3600
        got = s.geeknews(self.ATOM % IN, start, start + 86400)
        self.assertEqual((got[0]["points"], got[0]["comments"]), (0, 0))

    def test_outside_window_dropped(self):
        start = _epoch(IN) - 3600
        self.assertEqual(s.geeknews(self.ATOM % OUT, start, start + 86400), [])


class TestReleases(unittest.TestCase):
    ATOM = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns='http://www.w3.org/2005/Atom'>
      <entry>
        <title>v2.1.0</title>
        <link rel='alternate' href='https://github.com/o/r/releases/tag/v2.1.0' />
        <updated>%s</updated>
        <content type='html'>&lt;p&gt;Breaking:  removed   flag&lt;/p&gt;</content>
      </entry>
    </feed>"""

    def test_html_stripped_and_whitespace_collapsed(self):
        start = _epoch(IN) - 3600
        got = s.releases(self.ATOM % IN, "o/r", start, start + 86400)
        self.assertEqual(got[0]["tag"], "v2.1.0")
        self.assertEqual(got[0]["body"], "Breaking: removed flag")
        self.assertEqual(got[0]["repo"], "o/r")

    def test_outside_window_dropped(self):
        """이 소스는 LLM 선별을 건너뛰므로 날짜 컷이 유일한 필터다 — 새면 오래된 릴리스가 리포트에 오른다."""
        start = _epoch(IN) - 3600
        self.assertEqual(s.releases(self.ATOM % OUT, "o/r", start, start + 86400), [])

    def test_empty_markdown_when_nothing(self):
        """조용한 날은 조용해야 한다. 빈 섹션 제목조차 넘기지 않는다."""
        self.assertEqual(s.releases_markdown([]), "")


class TestDigestFormat(unittest.TestCase):
    def test_line_matches_fetch_hn(self):
        """뒤 단계는 소스를 구분하지 않는다 — 줄 형식이 어긋나면 조용히 빠진다."""
        line = s.digest_lines(
            [{"id": "lobx", "title": "t", "points": 3, "comments": 1}], "Lobsters")
        self.assertIn("- [3p/1c] #lobx t", line)

    def test_ids_are_prefixed(self):
        """HN 숫자 ID와 겹치면 urls 맵이 서로를 덮어쓴다."""
        for fn_id in ("lobabc", "gn123"):
            self.assertFalse(fn_id.isdigit())


if __name__ == "__main__":
    unittest.main()
