"""누적 지식 번들. 각 테스트는 실제로 겪은 버그 하나에 대응한다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import knowledge as k  # noqa: E402


def write_day(out, date, cands, urls, report):
    os.makedirs(out, exist_ok=True)
    for name, obj in ((f"candidates-{date}.json", cands), (f"urls-{date}.json", urls)):
        with open(os.path.join(out, name), "w") as f:
            json.dump(obj, f, ensure_ascii=False)
    with open(os.path.join(out, f"report-{date}.md"), "w") as f:
        f.write(report)


def read_file(path):
    with open(path) as f:
        return f.read()


def ingest(out, date):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "knowledge.py"),
                        "--ingest", date, "--dir", out],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return r.stdout


def pending(out, *extra):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "knowledge.py"),
                        "--pending", "--dir", out, *extra],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return r.stdout


class TestItemLine(unittest.TestCase):
    def test_roundtrip(self):
        """줄 형식이 이 파일의 실제 계약이다 — frontmatter가 아니라 이 정규식이다."""
        line = k.item_line("2026-08-20", "제목", "https://x.dev/a", "이유 한 줄", "123")
        got = k.parse_items(f"# {k.PENDING}\n\n{line}\n", k.PENDING)
        self.assertEqual(got, [{"date": "2026-08-20", "title": "제목", "url": "https://x.dev/a",
                                "why": "이유 한 줄", "id": "123"}])

    def test_brackets_in_title_do_not_break_link(self):
        """버그: 제목에 대괄호가 있으면 마크다운 링크가 깨져 다음 인제스트에서 항목이 사라진다."""
        line = k.item_line("2026-08-20", "Show HN: [beta] 도구", "https://x.dev/b", "", "9")
        self.assertEqual(len(k.parse_items(f"# {k.PENDING}\n\n{line}\n", k.PENDING)), 1)

    def test_sections_do_not_bleed(self):
        text = (f"# {k.ADOPTED}\n\n" + k.item_line("2026-08-01", "A", "u1", "", "1")
                + f"\n\n# {k.PENDING}\n\n" + k.item_line("2026-08-02", "B", "u2", "", "2") + "\n")
        self.assertEqual([i["title"] for i in k.parse_items(text, k.ADOPTED)], ["A"])
        self.assertEqual([i["title"] for i in k.parse_items(text, k.PENDING)], ["B"])

    def test_merge_keeps_first_seen_date(self):
        """언제 처음 잡혔는지가 신호다 — 다시 올라올 때 날짜를 덮어쓰면 그게 사라진다."""
        old = [{"date": "2026-08-01", "title": "A", "url": "u", "why": "", "id": "1"}]
        new = [{"date": "2026-08-20", "title": "A", "url": "u", "why": "새 이유", "id": "1"}]
        merged = k.merge(old, new)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["date"], "2026-08-01")


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, name):
        with open(os.path.join(self.out, "knowledge", "topics", f"{name}.md")) as f:
            return f.read()

    def test_adopted_vs_pending_split(self):
        """리포트가 원문 URL로 링크하므로 URL 등장 여부가 그대로 채택 판정이 된다."""
        write_day(self.out, "2026-08-20",
                  [{"id": "1", "title": "쓴 것", "project": "p", "why": "w1"},
                   {"id": "2", "title": "안 쓴 것", "project": "p", "why": "w2"}],
                  {"1": "https://a.dev/x", "2": "https://b.dev/y"},
                  "본문 [쓴 것](https://a.dev/x) 끝")
        ingest(self.out, "2026-08-20")
        text = self.page("p")
        self.assertEqual([i["title"] for i in k.parse_items(text, k.ADOPTED)], ["쓴 것"])
        self.assertEqual([i["title"] for i in k.parse_items(text, k.PENDING)], ["안 쓴 것"])

    def test_revived_moves_out_of_pending(self):
        """재심이 닫히는 지점. 보류였던 것이 채택되면 보류에 남아 있으면 안 된다 —
        남으면 이미 리포트에 쓴 것이 매일 다시 재심 대상으로 올라온다."""
        write_day(self.out, "2026-08-18",
                  [{"id": "7", "title": "묵힌 것", "project": "p", "why": "그때 이유"}],
                  {"7": "https://c.dev/z"}, "아무것도 안 씀")
        ingest(self.out, "2026-08-18")
        self.assertIn("묵힌 것", pending(self.out, "--days", "3650"))

        # 되살아난 항목의 URL은 **오늘 urls 맵에 없다** — 어제 잡힌 것이다.
        # 처음 쓴 테스트는 여기에 {"7": ...}를 넣어 버그를 가렸다(Codex가 잡아냈다).
        write_day(self.out, "2026-08-20",
                  [{"id": "7", "title": "묵힌 것", "project": "p", "why": "오늘은 맞다"}],
                  {}, "본문 [묵힌 것](https://c.dev/z) 끝")
        stdout = ingest(self.out, "2026-08-20")

        text = self.page("p")
        self.assertEqual([i["title"] for i in k.parse_items(text, k.ADOPTED)], ["묵힌 것"])
        self.assertEqual(k.parse_items(text, k.PENDING), [])
        self.assertNotIn("묵힌 것", pending(self.out, "--days", "3650"))
        self.assertIn("되살아남 1", stdout)
        self.assertIn("**되살아남 1건**", open(
            os.path.join(self.out, "knowledge", "log.md")).read())

    def test_revived_under_different_project(self):
        """버그: 재심 때 LLM이 project를 다르게 적으면 원래 페이지의 보류 항목이 영구히
        남아, 이미 리포트에 쓴 항목이 매일 다시 재심 대상으로 올라왔다. 정리는 전역이어야 한다."""
        write_day(self.out, "2026-08-18",
                  [{"id": "7", "title": "묵힌 것", "project": "이전주제", "why": "그때"}],
                  {"7": "https://j.dev/z"}, "")
        ingest(self.out, "2026-08-18")
        write_day(self.out, "2026-08-20",
                  [{"id": "7", "title": "묵힌 것", "project": "새주제", "why": "오늘"}],
                  {}, "본문 [묵힌 것](https://j.dev/z) 끝")
        ingest(self.out, "2026-08-20")
        self.assertEqual(k.parse_items(self.page("이전주제"), k.PENDING), [])
        self.assertNotIn("묵힌 것", pending(self.out, "--days", "3650"))

    def test_reserved_page_name_does_not_clobber_index(self):
        """`project`는 LLM이 채운다. 'index'를 그대로 쓰면 생성된 index.md가
        항목 페이지를 덮어써 그 주제가 통째로 사라진다(OKF §3.1 예약 이름)."""
        write_day(self.out, "2026-08-20",
                  [{"id": "1", "title": "t", "project": "index", "why": "w"}],
                  {"1": "https://k.dev/1"}, "")
        ingest(self.out, "2026-08-20")
        topics = os.path.join(self.out, "knowledge", "topics")
        self.assertEqual(k.parse_items(read_file(os.path.join(topics, "index-주제.md")),
                                       k.PENDING)[0]["title"], "t")
        self.assertNotIn("`#1`", read_file(os.path.join(topics, "index.md")))

    def test_newline_in_fields_survives_roundtrip(self):
        """줄바꿈이 하나라도 남으면 그 항목은 다음 읽기에서 조용히 사라진다."""
        write_day(self.out, "2026-08-20",
                  [{"id": "1", "title": "제목\n둘째줄", "project": "p", "why": "이유\n둘째줄"}],
                  {"1": "https://l.dev/1"}, "")
        ingest(self.out, "2026-08-20")
        got = k.parse_items(self.page("p"), k.PENDING)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["title"], "제목 둘째줄")

    def test_broken_json_does_not_crash(self):
        """망가진 JSON 하나가 아침 리포트를 날리면 안 된다."""
        os.makedirs(self.out, exist_ok=True)
        with open(os.path.join(self.out, "candidates-2026-08-20.json"), "w") as f:
            f.write("{ 깨진 ")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "knowledge.py"),
                            "--ingest", "2026-08-20", "--dir", self.out],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertNotEqual(r.returncode, 0)          # 실패는 알린다
        self.assertNotIn("Traceback", r.stderr)       # 하지만 터지지는 않는다

    def test_pending_window_bounds_prompt_not_bundle(self):
        """창을 제한하는 것은 프롬프트 크기 때문이다. 번들에서는 아무것도 지우지 않는다."""
        write_day(self.out, "2020-01-01",
                  [{"id": "5", "title": "오래된 것", "project": "p", "why": "w"}],
                  {"5": "https://d.dev/old"}, "")
        ingest(self.out, "2020-01-01")
        self.assertNotIn("오래된 것", pending(self.out, "--days", "14"))
        self.assertIn("오래된 것", self.page("p"))          # 번들에는 그대로 있다

    def test_urls_mode_feeds_stage_two(self):
        """선별 목록에는 URL을 넣지 않는다(토큰 레버). 되살아난 항목의 URL을
        2단계가 되찾지 못하면 본문 수집이 조용히 실패한다."""
        write_day(self.out, "2026-08-20",
                  [{"id": "9", "title": "보류", "project": "p", "why": "w"}],
                  {"9": "https://e.dev/u"}, "")
        ingest(self.out, "2026-08-20")
        raw = subprocess.run([sys.executable, os.path.join(ROOT, "knowledge.py"), "--pending",
                              "--dir", self.out, "--urls"],
                             capture_output=True, text=True, cwd=ROOT).stdout
        self.assertEqual(json.loads(raw), {"9": "https://e.dev/u"})

    def test_okf_conformance(self):
        """OKF §11 — 모든 개념 문서에 파싱 가능한 frontmatter와 비어 있지 않은 type이 있어야 한다."""
        write_day(self.out, "2026-08-20",
                  [{"id": "1", "title": "t", "project": "기술", "why": "w"}],
                  {"1": "https://f.dev/v"}, "")
        ingest(self.out, "2026-08-20")
        topics = os.path.join(self.out, "knowledge", "topics")
        pages = [n for n in os.listdir(topics) if n.endswith(".md") and n != "index.md"]
        self.assertTrue(pages)
        for name in pages:
            with open(os.path.join(topics, name)) as f:
                head = f.read().split("---")[1]
            self.assertRegex(head, r"(?m)^type: \S+")
        root = os.path.join(self.out, "knowledge")
        self.assertIn('okf_version: "0.2"', open(os.path.join(root, "index.md")).read())
        self.assertTrue(os.path.exists(os.path.join(root, "log.md")))

    def test_log_records_source_breakdown(self):
        """추가한 소스가 실제로 리포트에 쓰이는지는 며칠 봐야 안다. 그때 이 줄이 없으면
        후보 파일을 다시 파헤쳐야 한다 — ID 접두사가 소스다."""
        write_day(self.out, "2026-08-20",
                  [{"id": "1", "title": "hn", "project": "p", "why": "w"},
                   {"id": "lobabc", "title": "lo", "project": "p", "why": "w"},
                   {"id": "gn99", "title": "gn", "project": "p", "why": "w"}],
                  {"1": "https://m.dev/1", "lobabc": "https://m.dev/2", "gn99": "https://m.dev/3"},
                  "본문 [lo](https://m.dev/2) 끝")
        ingest(self.out, "2026-08-20")
        log = read_file(os.path.join(self.out, "knowledge", "log.md"))
        self.assertIn("Lobsters 1/1", log)      # 채택/후보
        self.assertIn("GeekNews 0/1", log)
        self.assertIn("HN 0/1", log)

    def test_reingest_same_date_is_idempotent(self):
        """버그: 백필로 같은 날을 다시 돌리면 log.md에 같은 날짜 블록이 또 붙었다.
        항목 페이지는 URL 기준 합치기라 멱등인데 로그만 아니었다."""
        write_day(self.out, "2026-08-20",
                  [{"id": "1", "title": "a", "project": "p", "why": "w"}],
                  {"1": "https://h.dev/1"}, "")
        ingest(self.out, "2026-08-20")
        ingest(self.out, "2026-08-20")
        log = open(os.path.join(self.out, "knowledge", "log.md")).read()
        self.assertEqual(log.count("## 2026-08-20"), 1)
        self.assertEqual(len(k.parse_items(self.page("p"), k.PENDING)), 1)

    def test_log_keeps_other_dates(self):
        for date, url in (("2026-08-18", "https://i.dev/1"), ("2026-08-19", "https://i.dev/2")):
            write_day(self.out, date, [{"id": "1", "title": "a", "project": "p", "why": "w"}],
                      {"1": url}, "")
            ingest(self.out, date)
        ingest(self.out, "2026-08-19")
        log = open(os.path.join(self.out, "knowledge", "log.md")).read()
        self.assertEqual(log.count("## 2026-08-18"), 1)
        self.assertEqual(log.count("## 2026-08-19"), 1)

    def test_missing_project_falls_back(self):
        """LLM이 project를 비우거나 빼먹어도 항목을 잃지 않아야 한다."""
        write_day(self.out, "2026-08-20",
                  [{"id": "1", "title": "t", "why": "w"}, {"id": "2", "title": "u", "project": "  "}],
                  {"1": "https://g.dev/1", "2": "https://g.dev/2"}, "")
        ingest(self.out, "2026-08-20")
        self.assertEqual(len(k.parse_items(self.page("기타"), k.PENDING)), 2)


if __name__ == "__main__":
    unittest.main()
