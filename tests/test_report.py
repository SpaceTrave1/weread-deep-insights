"""Offline tests: all books and notes are invented, networking is forbidden."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_deep_report as report
from scripts import collection


TEMPLATE = Path(__file__).resolve().parents[1] / "assets/report-template.html"


def synthetic_data():
    books = [
        {"bookId": "synthetic-1", "book": {"title": "合成科学甲", "author": "虚构作者甲"},
         "noteCount": 2, "reviewCount": 1, "bookmarkCount": 1, "sort": 20},
        {"bookId": "synthetic-2", "book": {"title": "合成文学乙", "author": "虚构作者乙"},
         "noteCount": 1, "reviewCount": 1, "sort": 10},
    ]
    notes = [
        {"bookId": b["bookId"], "title": b["book"]["title"], "author": b["book"]["author"],
         "totalNotes": report.notebook_total(b), "reviewCount": b["reviewCount"],
         "underlineCount": b["noteCount"],
         "underlines": [{"text": "科学研究需要比较数据。"}] * b["noteCount"],
         "reviews": [{"content": "我的合成例句：比较模型的原因和结果。"}]}
        for b in books
    ]
    return {
        "generatedAt": "2026-01-01T00:00:00+08:00",
        "stats": {"overall": {"totalReadTime": 7200, "readDays": 3,
                  "readStat": [{"stat": "读过", "counts": "10本"}, {"stat": "读完", "counts": "4本"}],
                  "preferCategory": [{"categoryTitle": "合成科学", "readingTime": 3600, "readingCount": 5},
                                     {"categoryTitle": "合成文学", "readingTime": 3600, "readingCount": 5}]},
                  "weekly": {}, "monthly": {}, "annual": [{"year": 2026, "data": {"totalReadTime": 7200, "readDays": 3}}]},
        "shelf": {"raw": {}, "books": [{"bookId": b["bookId"], **b["book"]} for b in books],
                  "albums": [], "progress": [], "bookInfo": []},
        "notebooks": {"books": books, "bookNotes": notes},
        "limits": {"maxNoteBooks": None, "skipProgress": True, "skipBookInfo": True},
    }


def complete_data():
    data = synthetic_data()
    data["collectionStatus"] = {"overall": "success", "weekly": "empty", "monthly": "empty", "shelf": "success", "notebooks": "success"}
    for row in data["stats"]["annual"]:
        row["fetchStatus"] = "success"
    for row in data["notebooks"]["bookNotes"]:
        row["fetchStatus"] = {"underlines": "success", "reviews": "success"}
    return data


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def fetch(self, endpoint, **params):
        self.calls.append((endpoint, params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.offline_guards = []
        for guard in (patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden in tests")),
                      patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Network forbidden in tests")),
                      patch.object(collection, "load_env", side_effect=AssertionError(".env forbidden in tests"))):
            self.offline_guards.append(guard.start())
            self.addCleanup(guard.stop)

    def tearDown(self):
        for guard in self.offline_guards:
            guard.assert_not_called()  # detects calls even if collection catches their errors


class BaselineTests(OfflineTest):
    def test_official_notebook_count(self):
        self.assertEqual(report.notebook_total(synthetic_data()["notebooks"]["books"][0]), 4)

    def test_units_and_stat_counts(self):
        self.assertEqual(report.seconds_text(3660), "1 小时 1 分钟")
        self.assertEqual(report.stat_counts([{"stat": "读过", "counts": "1,234 本"}]), {"读过": 1234})

    def test_content_prioritizes_personal_reviews(self):
        items = report.content_items(synthetic_data())
        evidence = report.pick_evidence(items, ["比较"], set(), 1)
        self.assertEqual(len(items), 5)
        self.assertEqual(evidence[0]["kind"], "想法")

    def test_notebook_cursor_pagination(self):
        client = FakeClient([{"books": [{"bookId": "fake-a", "sort": 20}], "hasMore": 1},
                             {"books": [{"bookId": "fake-b", "sort": 10}], "hasMore": 0}])
        self.assertEqual(len(report.collect_notebooks(client)), 2)
        self.assertEqual(client.calls[1][1], {"count": 100, "lastSort": 20})

    def test_review_cursor_pagination(self):
        client = FakeClient([{"reviews": [{"review": {"content": "合成甲"}}], "hasMore": 1, "synckey": 1},
                             {"reviews": [{"review": {"content": "合成乙"}}]}])
        self.assertEqual(len(report.collect_reviews(client, "fake")), 2)
        self.assertEqual(client.calls[1][1]["synckey"], 1)

    def test_analysis_is_deterministic_and_does_not_mutate(self):
        data = synthetic_data()
        before = copy.deepcopy(data)
        result = report.analyze(data, "合成报告")
        self.assertEqual(result, report.analyze(data, "合成报告"))
        self.assertEqual(data, before)
        self.assertEqual(result["basis"]["exportedUnderlines"], 3)
        self.assertEqual(result["basis"]["exportedReviews"], 2)
        self.assertEqual(result["annual"][0]["hours"], 2.0)

    def test_recommendations_exclude_seen_titles(self):
        data = synthetic_data()
        data["shelf"]["books"].append({"title": "复杂"})
        titles = [b["title"] for b in report.analyze(data, "合成")["recommendedBooks"]]
        self.assertNotIn("复杂", titles)

    def test_renderers_preserve_sections_and_escape_html(self):
        result = report.analyze(synthetic_data(), "<合成&报告>")
        md = report.render_markdown(result)
        rendered = report.render_html(result, TEMPLATE)
        self.assertIn("## 数据基础", md)
        self.assertIn("&lt;合成&amp;报告&gt;", rendered)
        self.assertNotIn("{{BODY}}", rendered)
        self.assertIn('id="basis"', rendered)

    def test_cli_defaults_and_options(self):
        args = report.parse_args([])
        self.assertEqual(args.format, "both")
        args = report.parse_args(["--max-note-books", "1", "--skip-progress", "--skip-book-info", "--timeout", "7", "--retries", "1"])
        self.assertEqual((args.max_note_books, args.timeout, args.retries), (1, 7, 1))

    def test_cli_writes_both_outputs_offline(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-", dir=Path(__file__).resolve().parent) as destination:
            with patch.object(report, "collect_data", return_value=synthetic_data()):
                self.assertEqual(report.main(["--output-dir", destination]), 0)
            self.assertTrue((Path(destination) / "weread_deep_report.md").exists())
            self.assertTrue((Path(destination) / "weread_deep_report.html").exists())


class CollectionRegressionTests(OfflineTest):
    def test_page_limits_are_incomplete_and_retain_rows(self):
        for func, args, pages, expected in (
            (report.collect_reviews, ("fake",), [{"reviews": [{"review": {"content": f"合成{i}"}}], "hasMore": 1, "synckey": i + 1} for i in range(100)], 100),
            (report.collect_notebooks, (), [{"books": [{"bookId": f"fake-{i}", "sort": i}], "hasMore": 1} for i in range(300)], 300),
        ):
            with self.subTest(func=func.__name__):
                client = FakeClient(pages)
                with self.assertRaises(report.PartialFetchError) as error:
                    func(client, *args)
                self.assertEqual(len(error.exception.rows), expected)
                self.assertEqual(len(client.calls), expected)

    def test_upgrade_payload_shapes_always_stop(self):
        for payload in ({}, "synthetic upgrade", {"message": "synthetic upgrade"}):
            with self.subTest(payload=payload), patch.object(collection, "post_json", return_value={"upgrade_info": payload}) as post:
                with self.assertRaises(report.UpgradeRequired):
                    report.WeReadClient("synthetic-token").fetch("/fake")
                self.assertEqual(post.call_count, 1)

    def test_retry_success_and_exhaustion_use_only_mock_transport(self):
        with patch.object(collection, "post_json", side_effect=[TimeoutError("fake"), {"value": 1}]) as post, patch.object(collection.time, "sleep"):
            self.assertEqual(report.WeReadClient("synthetic-token", retries=2).fetch("/fake"), {"value": 1})
            self.assertEqual(post.call_count, 2)
        with patch.object(collection, "post_json", return_value={"errcode": 1, "errmsg": "fake"}) as post, patch.object(collection.time, "sleep"):
            with self.assertRaises(RuntimeError):
                report.WeReadClient("synthetic-token", retries=2).fetch("/fake")
            self.assertEqual(post.call_count, 2)

    def test_metadata_empty_and_failure_counts(self):
        rows = synthetic_data()["shelf"]["books"]
        data = complete_data()
        data["shelf"]["progress"] = report.collect_progress(FakeClient([{}, RuntimeError("fake")]), rows)
        data["shelf"]["bookInfo"] = report.collect_book_info(FakeClient([{}, {"title": "合成"}]), rows)
        data["limits"].update(skipProgress=False, skipBookInfo=False)
        result = report.analyze(data, "合成")
        self.assertEqual(result["basis"]["progressRows"], 0)
        self.assertEqual(result["basis"]["bookInfoRows"], 1)
        self.assertEqual(result["coverage"]["groups"]["进度"]["empty"], 1)
        self.assertEqual(result["coverage"]["groups"]["进度"]["failed"], 1)

    def test_zero_sample_does_not_request_notes(self):
        client = FakeClient([])
        self.assertEqual(report.collect_book_notes(client, synthetic_data()["notebooks"]["books"], 0), [])
        self.assertEqual(client.calls, [])

    def test_repeated_page_ids_do_not_inflate_records(self):
        book = {"bookId": "fake", "sort": 10}
        client = FakeClient([{"books": [book], "hasMore": 1}, {"books": [book]}])
        self.assertEqual(len(report.collect_notebooks(client)), 1)
        row = {"review": {"reviewId": "fake-review", "content": "合成"}}
        client = FakeClient([{"reviews": [row], "hasMore": 1, "synckey": 1}, {"reviews": [row]}])
        self.assertEqual(len(report.collect_reviews(client, "fake")), 1)

    def test_cursor_cycles_are_detected_before_page_limit(self):
        client = FakeClient([{"hasMore": 1, "synckey": key} for key in (1, 2, 1)])
        with self.assertRaises(report.PartialFetchError):
            report.collect_reviews(client, "fake")
        self.assertEqual(len(client.calls), 3)

    def test_missing_id_is_unrequested(self):
        data = complete_data()
        data["notebooks"]["books"].append({"book": {"title": "合成无ID"}})
        result = report.analyze(data, "合成")
        self.assertEqual(result["coverage"]["groups"]["划线"]["not_requested"], 1)
        self.assertFalse(result["coverage"]["notesComplete"])

    def test_stale_or_malformed_text_is_not_valid_content(self):
        data = synthetic_data()
        row = data["notebooks"]["bookNotes"][0]
        row["fetchStatus"] = {"reviews": "not_requested"}
        row["underlines"] = [{"text": {"error": "fake"}}, {"text": 123}, {"text": " "}]
        result = report.analyze(data, "合成")
        self.assertEqual((result["basis"]["exportedUnderlines"], result["basis"]["exportedReviews"]), (1, 1))

    def test_legacy_failure_placeholders_are_not_counted(self):
        data = synthetic_data()
        data["notebooks"]["bookNotes"][0]["underlines"] += [{"text": "[合成失败]", "error": True}, {"text": "   "}]
        data["notebooks"]["bookNotes"][0]["reviews"] += [{"content": "[合成失败]", "error": True}, {}]
        data["shelf"]["progress"] = [{"bookId": "synthetic-1", "error": "SyntheticError"}]
        data["shelf"]["bookInfo"] = [{"bookId": "synthetic-1", "error": "SyntheticError"}]
        result = report.analyze(data, "合成")
        self.assertEqual((result["basis"]["exportedUnderlines"], result["basis"]["exportedReviews"]), (3, 2))
        self.assertEqual((result["basis"]["progressRows"], result["basis"]["bookInfoRows"]), (0, 0))
        self.assertEqual(result["coverage"]["groups"]["划线"]["failed"], 1)

    def test_failure_and_empty_are_distinct_metadata(self):
        client = FakeClient([RuntimeError("synthetic-secret-must-not-leak"), {"reviews": []}])
        notes = report.collect_book_notes(client, synthetic_data()["notebooks"]["books"], 1)
        self.assertEqual(notes[0]["fetchStatus"], {"underlines": "failed", "reviews": "empty"})
        self.assertEqual(notes[0]["underlines"], [])
        self.assertNotIn("synthetic-secret", str(notes))

    def test_partial_review_page_preserves_valid_rows_and_failure(self):
        client = FakeClient([{}, {"reviews": [{"review": {"content": "合成已取得"}}], "hasMore": 1, "synckey": 10}, RuntimeError("fake")])
        notes = report.collect_book_notes(client, synthetic_data()["notebooks"]["books"], 1)
        self.assertEqual(len(notes[0]["reviews"]), 1)
        self.assertEqual(notes[0]["fetchStatus"]["reviews"], "failed")

    def test_stalled_cursors_are_incomplete(self):
        for func, args, pages in (
            (report.collect_notebooks, (), [{"books": [{"sort": 1}], "hasMore": 1}, {"books": [{"sort": 1}], "hasMore": 1}]),
            (report.collect_reviews, ("fake",), [{"hasMore": 1, "synckey": 0}]),
        ):
            with self.subTest(func=func.__name__):
                with self.assertRaises(report.PartialFetchError):
                    func(FakeClient(pages), *args)

    def test_sampling_skipping_and_unknown_coverage_visible_in_both_outputs(self):
        data = synthetic_data()
        data["limits"]["maxNoteBooks"] = 1
        data["notebooks"]["bookNotes"] = data["notebooks"]["bookNotes"][:1]
        result = report.analyze(data, "合成")
        self.assertEqual(result["coverage"]["groups"]["点评"]["not_requested"], 1)
        self.assertEqual(result["coverage"]["groups"]["进度"]["not_requested"], 2)
        for rendered in (report.render_markdown(result), report.render_html(result, TEMPLATE)):
            self.assertNotIn("基于全量", rendered)
            self.assertIn("数据覆盖情况", rendered)
            self.assertIn("定向抽样", rendered)
            self.assertIn("未知", rendered)

    def test_gateway_upgrade_stops_even_optional_collection(self):
        with patch.object(collection, "post_json", return_value={"upgrade_info": {"message": "synthetic upgrade"}}) as post:
            with self.assertRaises(report.UpgradeRequired):
                report.WeReadClient("synthetic-token").fetch("/fake")
            self.assertEqual(post.call_count, 1)
        with self.assertRaises(report.UpgradeRequired):
            report.collect_book_notes(FakeClient([report.UpgradeRequired("fake")]), synthetic_data()["notebooks"]["books"], 1)

    def test_collect_data_partial_stats_and_directory_failure(self):
        client = FakeClient([RuntimeError("fake"), {}, {}, {}, {},
                             {"books": [synthetic_data()["notebooks"]["books"][0]], "hasMore": 1},
                             RuntimeError("fake"), {}, {"reviews": []}])
        with patch.object(collection, "load_env"), patch.dict("os.environ", {"WEREAD_API_KEY": "synthetic-token"}), patch.object(collection, "WeReadClient", return_value=client):
            data = report.collect_data(report.parse_args(["--skip-progress", "--skip-book-info"]))
        result = report.analyze(data, "合成")
        self.assertEqual(data["collectionStatus"]["overall"], "failed")
        self.assertEqual(len(data["notebooks"]["books"]), 1)
        self.assertIn("未发现书籍的数量未知", result["coverage"]["scope"])
        self.assertEqual(result["basis"]["totalReadTime"], "未获取")


class EvidenceRegressionTests(OfflineTest):
    def test_theme_concentration_requires_matching_text_across_books(self):
        data = complete_data()
        data["stats"]["overall"]["preferCategory"] = []
        for index, (book, row) in enumerate(zip(data["notebooks"]["books"], data["notebooks"]["bookNotes"])):
            row["underlines"] = [{"text": "科学研究探索" if index == 0 else "合成无匹配片段"} for _ in range(5)]
            row["reviews"] = []
            book.update(noteCount=5, reviewCount=0)
        result = report.analyze(data, "合成单书主题")
        self.assertTrue(result["coverage"]["notesComplete"])
        self.assertFalse(result["evidenceConditions"]["themeSufficient"])
        self.assertIsNone(result["informationCocoon"]["score"])

    def test_invalid_stat_text_is_unknown_not_zero(self):
        self.assertEqual(report.stat_counts([{"stat": "读完", "counts": "未获取"}]), {})
        data = complete_data()
        data["stats"]["overall"]["readStat"][1]["counts"] = "未获取"
        result = report.analyze(data, "合成")
        self.assertIsNone(next(row["score"] for row in result["dimensionScores"] if row["name"] == "收尾纪律"))

    def test_same_title_distinct_ids_still_count_as_two_books(self):
        data = complete_data()
        for row in data["notebooks"]["bookNotes"]:
            row["title"] = "合成同名书"
            row["reviews"] = [{"content": f"合成{i}：原因结果数据比较"} for i in range(3)]
        result = report.analyze(data, "合成")
        self.assertTrue(result["evidenceConditions"]["personalSufficient"])
        self.assertNotEqual(result["profileSummary"]["label"], "画像证据不足")

    def test_empty_data_never_implies_personality_or_scores(self):
        data = synthetic_data()
        data["stats"] = {"overall": {}, "annual": []}
        data["shelf"] = {"raw": {}, "books": [], "albums": [], "progress": [], "bookInfo": []}
        data["notebooks"] = {"books": [], "bookNotes": []}
        result = report.analyze(data, "合成空数据")
        self.assertEqual(result["profileSummary"]["label"], "画像证据不足")
        self.assertIsNone(result["informationCocoon"]["score"])
        self.assertTrue(all(row["score"] is None for row in result["dimensionScores"]))
        self.assertEqual(result["recommendedBooks"], [])
        for rendered in (report.render_markdown(result), report.render_html(result, TEMPLATE)):
            self.assertIn("暂不评分", rendered)
            self.assertNotIn("None/100", rendered)
            self.assertNotIn("自我修正倾向", rendered)

    def test_underlines_only_do_not_prove_personal_style_or_values(self):
        data = complete_data()
        for row in data["notebooks"]["bookNotes"]:
            row["reviews"] = []
            row["underlines"] = [{"text": "责任主动行动科学研究创新探索" * 30}]
        result = report.analyze(data, "合成划线")
        self.assertEqual(result["profileSummary"]["label"], "画像证据不足")
        self.assertEqual(result["values"], [])
        self.assertTrue(all(not row["personalSufficient"] for row in result["styles"]))
        self.assertIsNone(next(row["score"] for row in result["dimensionScores"] if row["name"] == "行动落地"))

    def test_personal_profile_requires_multiple_reviews_and_books(self):
        data = complete_data()
        for notebook, row in zip(data["notebooks"]["books"], data["notebooks"]["bookNotes"]):
            row["reviews"] = [{"content": f"合成例句{i}：数据模型的原因与结果，科学研究探索"} for i in range(3)]
            notebook["reviewCount"] = 3
        result = report.analyze(data, "合成足量点评")
        self.assertTrue(result["evidenceConditions"]["personalSufficient"])
        self.assertNotEqual(result["profileSummary"]["label"], "画像证据不足")
        data["notebooks"]["bookNotes"] = data["notebooks"]["bookNotes"][:1]
        data["notebooks"]["bookNotes"][0]["reviews"] *= 30
        result = report.analyze(data, "合成单书")
        self.assertEqual(result["profileSummary"]["label"], "画像证据不足")

    def test_scores_are_observed_ratios_without_fixed_baselines(self):
        result = report.analyze(complete_data(), "合成")
        scores = {row["name"]: row["score"] for row in result["dimensionScores"]}
        self.assertEqual(scores, {"问题意识": None, "现实敏感度": None, "表达密度": 40,
                                  "收尾纪律": 40, "知识均衡": 50, "行动落地": None})
        self.assertEqual(result["informationCocoon"]["score"], 50)

    def test_partial_notes_disable_account_ratio_and_theme_concentration(self):
        data = complete_data()
        data["stats"]["overall"]["preferCategory"] = []
        data["notebooks"]["bookNotes"][0]["fetchStatus"]["reviews"] = "failed"
        result = report.analyze(data, "合成不完整")
        self.assertFalse(result["coverage"]["notesComplete"])
        self.assertFalse(result["evidenceConditions"]["themeSufficient"])
        self.assertIsNone(result["informationCocoon"]["score"])
        self.assertIsNone(next(row["score"] for row in result["dimensionScores"] if row["name"] == "表达密度"))

    def test_missing_and_inconsistent_official_counts_do_not_score(self):
        for stats in ({}, {"readStat": [{"stat": "读过", "counts": "1"}, {"stat": "读完", "counts": "1"}]},
                      {"readStat": [{"stat": "读过", "counts": "10"}, {"stat": "读完", "counts": "11"}]}):
            with self.subTest(stats=stats):
                data = complete_data()
                data["stats"]["overall"] = stats
                result = report.analyze(data, "合成")
                self.assertIsNone(next(row["score"] for row in result["dimensionScores"] if row["name"] == "收尾纪律"))


class CompatibilityTests(OfflineTest):
    def test_direct_and_module_cli_help_are_offline(self):
        root = TEMPLATE.parents[1]
        for command in ([sys.executable, str(root / "scripts/generate_deep_report.py"), "--help"],
                        [sys.executable, "-m", "scripts.generate_deep_report", "--help"]):
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--retries", result.stdout)
            self.assertIn("--skip-book-info", result.stdout)

    def test_single_format_cli_outputs(self):
        for format_name, suffix in (("html", "html"), ("markdown", "md")):
            with tempfile.TemporaryDirectory(prefix="synthetic-", dir=Path(__file__).resolve().parent) as destination:
                with patch.object(report, "collect_data", return_value=complete_data()):
                    self.assertEqual(report.main(["--format", format_name, "--output-dir", destination]), 0)
                self.assertEqual([p.name for p in Path(destination).iterdir()], [f"weread_deep_report.{suffix}"])

    def test_synthetic_analysis_snapshot(self):
        expected = json.loads((Path(__file__).parent / "snapshots/analysis.json").read_text(encoding="utf-8"))
        actual = json.loads(json.dumps(report.analyze(complete_data(), "合成回归报告"), ensure_ascii=False))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
