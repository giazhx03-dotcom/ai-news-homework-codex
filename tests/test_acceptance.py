"""验收使用固定 RSS、真实文件与 SQLite；所有状态均写入隔离目录。"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from assistant_news.collector import collect, instant
from assistant_news.feeds import parse_feed
from assistant_news.rules import classify

UTC = timezone.utc
NOW = datetime(2026, 11, 25, 17, 21, 42, 123456, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
A = {"id": "a", "name": "模拟媒体 A"}
B = {"id": "b", "name": "模拟媒体 B"}


def article(uid, published=NOW, **changes):
    item = dict(uid=uid, title="AI 开发工具", url=f"https://example.org/{uid}",
                summary="这是一条测试用 RSS 简介。", published_at=published.isoformat(),
                date_status="ok", tags=[])
    item.update(changes)
    return item


class CollectionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        work = ROOT / "work"
        work.mkdir(exist_ok=True)
        directory = tempfile.TemporaryDirectory(prefix="audit-", dir=work)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.day = "2026-11-26"

    def collect(self, batches, when=NOW, bounds=None):
        def fetcher(source):
            batch = batches[source["id"]]
            if isinstance(batch, Exception):
                raise batch
            return batch, []
        return collect(self.root, [A, B], fetcher=fetcher, now=when, bounds=bounds)

    def cursors(self):
        with sqlite3.connect(self.root / "state" / "news.sqlite3") as db:
            return dict(db.execute("SELECT source,success_end FROM cursors"))

    def test_first_72_hours_exact_edges_and_singapore_midnight(self):
        low = NOW - timedelta(hours=72)
        tick = timedelta(microseconds=1)
        report = self.collect({"a": [article("start", low), article("end", NOW), article("before", low - tick),
                                     article("after", NOW + tick)], "b": []})
        self.assertEqual(instant(report["range_start"]), low)
        self.assertEqual(instant(report["range_end"]), NOW)
        self.assertEqual(report["day"], self.day)
        self.assertEqual([s["status"] for s in report["sources"]], ["updated", "unchanged"])
        self.assertEqual({a["url"].rsplit("/", 1)[1] for a in report["articles"]}, {"start", "end"})
        self.assertEqual(report["new_count"], 2)

    def test_id_or_normalized_url_survive_reload_and_same_title_can_be_distinct(self):
        self.collect({"a": [article("id1", url="https://EXAMPLE.org:443/story?x=1&utm_source=feed#top")],
                      "b": []})
        report = self.collect({"a": [article("id2", url="https://example.org/story?x=1"),
                                     article("id2", url="https://example.org/moved"),
                                     article("distinct")],
                               "b": [article("other-source-id", url="https://example.org/moved")]})
        self.assertEqual((report["new_count"], report["total_count"]), (1, 2))
        self.assertEqual(report["sources"][1]["status"], "unchanged")
        again = self.collect({"a": [article("id1", title="更正：AI 工具", url="https://example.org/new-link")],
                              "b": []})
        self.assertEqual((again["new_count"], again["total_count"]), (0, 2))
        for filename in ("daily.md", "daily.html", "daily.json"):
            archive = self.root / "outputs" / "history" / self.day / filename
            self.assertEqual(archive.read_bytes(), (self.root / "outputs" / "latest" / filename).read_bytes())
        data = json.loads((self.root / "outputs" / "latest" / "daily.json").read_text())
        self.assertEqual(data, again)

    def test_failure_recovery_uses_source_specific_cursor_beyond_overlap(self):
        first = self.collect({"a": [], "b": []})
        old_cursor = self.cursors()["a"]
        later = NOW + timedelta(hours=25)
        failed = self.collect({"a": OSError("模拟断网"), "b": [article("good", later)]}, later)
        self.assertEqual(self.cursors()["a"], old_cursor)
        self.assertEqual(instant(self.cursors()["b"]), later)
        self.assertEqual([s["status"] for s in failed["sources"]], ["failed", "updated"])
        self.assertIn("模拟断网", failed["sources"][0]["error"])
        recovered = self.collect({"a": [article("missed", NOW + timedelta(hours=1))], "b": []},
                                 later + timedelta(minutes=1))
        self.assertEqual([s["status"] for s in recovered["sources"]], ["updated", "unchanged"])
        self.assertLess(instant(recovered["sources"][0]["range_start"]),
                        instant(recovered["sources"][1]["range_start"]))
        self.assertEqual((recovered["new_count"], recovered["total_count"]), (1, 2))
        previous = self.root / "outputs" / "history" / self.day / "daily.json"
        self.assertEqual(json.loads(previous.read_text()), first)

    def test_first_source_failure_retains_original_start_even_after_72h(self):
        first = self.collect({"a": OSError("模拟首次失败"), "b": []})
        self.assertIsNone(self.cursors()["a"])
        later = NOW + timedelta(days=6)
        recovered = self.collect({"a": [article("old", NOW - timedelta(hours=71))], "b": []}, later)
        self.assertEqual(first["sources"][0]["range_start"], recovered["sources"][0]["range_start"])
        self.assertEqual(recovered["new_count"], 1)

    def test_manual_historical_interval_preserves_cursor_and_accumulated_daily_report(self):
        self.collect({"a": [article("daily")], "b": []})
        checkpoints = self.cursors()
        start = instant("2026-11-17T10:00:00")
        end = instant("2026-11-17T11:00:00+08:00")
        self.assertEqual(start.hour, 2)
        report = self.collect({"a": [article("backfill", start), article("outside", end + timedelta(seconds=1))],
                               "b": []}, NOW + timedelta(minutes=1), bounds=(start, end))
        self.assertEqual(self.cursors(), checkpoints)
        self.assertEqual((report["new_count"], report["total_count"]), (1, 2))

    def test_invalid_and_undated_rss_then_empty_day(self):
        raw = (b"<rss><channel><item><title>AI test</title><link>javascript:nope</link></item>"
               b"<item><title>AI agent &amp; automation</title><link>https://example.org/tool</link>"
               b"<description><![CDATA[<script>unsafe()</script>plain &amp; text]]></description>"
               b"</item></channel></rss>")
        entries, warnings = parse_feed(raw)
        self.assertEqual(len(entries), 1)
        self.assertTrue(warnings)
        first = self.collect({"a": entries, "b": []})
        item = first["articles"][0]
        self.assertIsNone(item["published_at"])
        self.assertEqual((item["date_status"], item["summary"]), ("missing", "plain & text"))
        html = (self.root / "outputs" / "latest" / "daily.html").read_text()
        self.assertIn("AI agent &amp; automation", html)
        self.assertNotIn("unsafe()", html)
        self.assertIn("来源未提供日期", html)
        empty = self.collect({"a": entries, "b": []}, NOW + timedelta(days=1))
        self.assertEqual((empty["new_count"], empty["total_count"]), (0, 0))
        for filename in ("daily.md", "daily.html"):
            content = (self.root / "outputs" / "latest" / filename).read_text()
            self.assertEqual(content.count("本期此分类暂无条目"), 4)
            self.assertIn("成功无更新", content)

    def test_interrupted_export_replayed_even_after_day_change(self):
        with patch("assistant_news.collector.replace_file", side_effect=OSError("模拟写盘失败")):
            with self.assertRaises(OSError):
                self.collect({"a": [article("saved")], "b": []})
        self.collect({"a": [], "b": []}, NOW + timedelta(days=1))
        saved = self.root / "outputs" / "history" / self.day / "daily.json"
        self.assertEqual(json.loads(saved.read_text())["total_count"], 1)

    def test_concurrent_process_cannot_touch_active_run(self):
        self.collect({"a": [], "b": []})
        initial = self.cursors()
        program = ("import sys; from pathlib import Path; from assistant_news.collector import project_lock\n"
                   "with project_lock(Path(sys.argv[1])):\n"
                   " print('locked', flush=True); sys.stdin.readline()\n")
        with subprocess.Popen([sys.executable, "-c", program, str(self.root / "state")],
                              cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as locker:
            try:
                self.assertEqual(locker.stdout.readline().strip(), "locked")
                with self.assertRaisesRegex(RuntimeError, "另一个收集任务"):
                    self.collect({"a": [article("other")], "b": []})
                self.assertEqual(self.cursors(), initial)
            finally:
                locker.communicate(input="release\n", timeout=10)
        self.assertEqual(self.collect({"a": [article("other")], "b": []})["new_count"], 1)


class RuleAcceptanceTests(unittest.TestCase):
    def test_four_categories_and_word_boundaries(self):
        for title, expected in [
            ("OpenAI 发布大模型评测基准", "模型与研究"),
            ("Anthropic launches a Claude coding agent", "产品与工具"),
            ("AI 加速芯片企业完成融资", "行业与政策"),
            ("关于人工智能的几点观察", "待确认"),
            ("A family has paid a fee again", None),
        ]:
            with self.subTest(title=title):
                self.assertEqual(classify({"title": title, "summary": ""}), expected)

    def test_writing_credit_does_not_admit_unrelated_news(self):
        for title, summary in [
            ("港队赢得足球决赛", "本文借助 AI 工具撰写。"),
            ("Champions win city league final", "This article was written with assistance from AI."),
            ("电影获得年度大奖", "本文由 AI 辅助生成。"),
            ("Claude Monet exhibition opens at national museum", ""),
        ]:
            with self.subTest(title=title):
                self.assertIsNone(classify({"title": title, "summary": summary}))

    def test_actual_ai_writing_products_are_retained(self):
        for title in ("AI写作工具上线", "New AI-generated video tool launches"):
            with self.subTest(title=title):
                self.assertEqual(classify({"title": title, "summary": ""}), "产品与工具")
