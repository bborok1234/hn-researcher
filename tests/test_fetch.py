"""수집 단계 회귀 테스트. 네트워크는 타지 않는다 — 순수 변환만 검증한다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_hn  # noqa: E402
import fetch_pages  # noqa: E402

STORIES = [
    {"objectID": "1", "title": "첫 글", "points": 10, "num_comments": 2, "url": "https://a.test/x"},
    {"objectID": "2", "title": "둘째", "points": 50, "num_comments": 9, "url": None},
]


class TestDigest(unittest.TestCase):
    def test_no_urls_in_digest(self):
        """URL은 토큰 밀도가 높아 1,100줄에 두 개씩 붙이면 다이제스트가 21만 토큰까지
        부푼다. 선별에는 제목과 ID만 있으면 된다."""
        md = fetch_hn.to_markdown(list(STORIES), "테스트")
        self.assertNotIn("http", md)
        self.assertIn("#1", md)
        self.assertIn("#2", md)

    def test_sorted_by_points(self):
        lines = [l for l in fetch_hn.to_markdown(list(STORIES), "t").splitlines() if l.startswith("- ")]
        self.assertIn("#2", lines[0])  # 50점이 먼저

    def test_url_map_covers_all_and_falls_back_to_hn(self):
        """다이제스트에서 URL을 뺐으니 수집 단계가 ID로 되찾을 수 있어야 한다."""
        m = fetch_hn.url_map(STORIES)
        self.assertEqual(m["1"], "https://a.test/x")
        self.assertIn("news.ycombinator.com/item?id=2", m["2"])  # url 없으면 HN으로


class TestHtmlToText(unittest.TestCase):
    def test_strips_script_and_style(self):
        html = "<html><head><style>.a{color:red}</style></head><body><p>본문</p>" \
               "<script>alert('x')</script></body></html>"
        out = fetch_pages.html_to_text(html)
        self.assertIn("본문", out)
        self.assertNotIn("alert", out)
        self.assertNotIn("color:red", out)

    def test_block_tags_become_newlines(self):
        out = fetch_pages.html_to_text("<p>가</p><p>나</p>")
        self.assertIn("가", out)
        self.assertIn("나", out)
        self.assertNotIn("가나", out)  # 붙어버리면 안 된다


if __name__ == "__main__":
    unittest.main()
