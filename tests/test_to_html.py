"""렌더러 회귀 테스트. 각 테스트는 실제로 겪은 버그 하나에 대응한다."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import to_html  # noqa: E402


class TestTokenize(unittest.TestCase):
    def test_bold_line_slug_is_project_korean_is_section(self):
        """버그: 리포트가 섹션 제목을 '**볼드**' 한 줄로도 쓰는데, 프로젝트 이름도
        같은 형태라 소문자 슬러그 이름이 섹션으로 잡혀 로스터가 비었다."""
        kinds = dict((t, k) for k, t in to_html.tokenize("**적용**\n**alpha-proj**"))
        self.assertEqual(kinds["적용"], "h2")
        self.assertEqual(kinds["alpha-proj"], "h3")

    def test_hash_heading_still_works(self):
        """'## 제목' 형식도 계속 지원해야 한다 — 실행마다 형식이 흔들린다."""
        self.assertEqual(list(to_html.tokenize("## 적용")), [("h2", "적용")])


class TestSlugs(unittest.TestCase):
    def test_splits_and_strips(self):
        self.assertEqual(to_html.slugs("`alpha-proj` / beta-proj — 설명"),
                         ["alpha-proj", "beta-proj"])

    def test_rejects_korean_and_too_short(self):
        self.assertEqual(to_html.slugs("한국어 구절"), [])
        self.assertEqual(to_html.slugs("ab"), [])


class TestInline(unittest.TestCase):
    def test_bare_url_becomes_domain_link(self):
        """버그: 맨 URL이 한 줄을 다 잡아먹으며 줄바꿈돼 읽는 흐름을 끊었다."""
        out = to_html.inline("설명 (https://www.empirical.health/blog/x/)")
        self.assertIn(">empirical.health ↗<", out)
        self.assertIn('href="https://www.empirical.health/blog/x/"', out)
        self.assertNotIn("(<a", out)  # 감싼 괄호까지 걷어냈는지

    def test_markdown_link_preserved(self):
        out = to_html.inline("[원문](https://example.com/a)")
        self.assertIn('<a href="https://example.com/a">원문</a>', out)

    def test_inline_code(self):
        self.assertIn("<code>daily.sh</code>", to_html.inline("`daily.sh` 실행"))


class TestLeads(unittest.TestCase):
    def test_body_wrapped_in_span(self):
        """버그: .leads li가 grid라서 <strong>·텍스트·<a>가 각각 그리드 아이템이 되어
        한 단어씩 줄바꿈됐다. 본문을 span 하나로 감싸야 2칸으로 고정된다."""
        items = to_html.leads("**오늘의 헤드라인**\n- **제목** — 설명")
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].startswith('<li><span class="leads-body">'))


class TestRoster(unittest.TestCase):
    def _report(self, d, body):
        p = os.path.join(d, "report-2026-08-20.md")
        open(p, "w").write(body)
        return p

    def test_active_from_body_idle_from_line(self):
        """버그: 섹션이 시급성별로 바뀌며 프로젝트명이 본문에 묻혀 칩이 하나도 안 켜졌다.
        추적 목록과 대조하는 방식으로 고쳤다."""
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "projects-2026-08-20.txt"), "w").write(
                "- alpha-proj\n- beta-proj\n- gamma-proj\n"
            )
            p = self._report(d, "**적용**\n- alpha-proj 에 적용\n오늘 매칭 없음: beta-proj\n")
            active, idle = to_html.roster(open(p).read(), p)
            self.assertEqual(active, ["alpha-proj"])
            self.assertIn("beta-proj", idle)
            self.assertNotIn("gamma-proj", active)  # 언급 없으면 켜지지 않는다

    def test_project_names_are_newline_stripped(self):
        """버그: projects 파일을 줄 단위로 읽을 때 개행을 안 떼서 대조가 실패했다."""
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "projects-2026-08-20.txt"), "w").write("- alpha-proj\n")
            p = self._report(d, "**적용**\n- alpha-proj 관련\n")
            active, _ = to_html.roster(open(p).read(), p)
            self.assertEqual(active, ["alpha-proj"])

    def test_missing_sidecar_degrades(self):
        """사이드카 파일이 없으면 조용히 비워야 한다 — 렌더는 계속돼야 한다."""
        with tempfile.TemporaryDirectory() as d:
            p = self._report(d, "**적용**\n- 뭔가\n오늘 매칭 없음: beta-proj\n")
            active, idle = to_html.roster(open(p).read(), p)
            self.assertEqual(active, [])
            self.assertEqual(idle, ["beta-proj"])


class TestConvert(unittest.TestCase):
    def test_warn_section_marked(self):
        """경고는 시급성이 달라 시각적으로 분리해야 한다."""
        self.assertIn('<h2 class="warn">경고</h2>', to_html.convert("**경고**\n- 깨졌다"))
        self.assertIn("<h2>적용</h2>", to_html.convert("**적용**\n- 하자"))

    def test_headline_section_and_matching_line_excluded(self):
        """헤드라인은 순위 목록으로, '매칭 없음'은 칩으로 따로 렌더하므로 본문에서 빠진다."""
        md = "**오늘의 헤드라인**\n- 큰 발견\n**적용**\n- 하자\n오늘 매칭 없음: beta\n"
        out = to_html.convert(md)
        self.assertNotIn("큰 발견", out)
        self.assertNotIn("매칭 없음", out)
        self.assertIn("하자", out)


if __name__ == "__main__":
    unittest.main()
