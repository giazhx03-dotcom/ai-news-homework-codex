import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from assistant_news.feeds import FeedError, MAX_FEED_BYTES, fetch_feed, in_window, parse_feed


def rss(*items):
    return ("<rss version='2.0'><channel>" + "".join("<item>" + item + "</item>" for item in items)
            + "</channel></rss>").encode()


BASIC = "<title>Hello &amp; world</title><link>https://example.org/news?q=a&amp;b=c</link>"


class FeedTests(unittest.TestCase):
    def test_fields_plain_text_and_offset(self):
        fields = BASIC + """<guid isPermaLink="false">abc</guid>
        <pubDate>Wed, 25 Nov 2026 23:59:07 +0800</pubDate><category>AI</category>
        <description><![CDATA[<p>First &amp; second.</p><script>alert(1)</script><p>Third.</p>]]></description>"""
        items, warnings = parse_feed(rss(fields))
        self.assertEqual(warnings, [])
        self.assertEqual(items, [{
            "uid": "abc", "title": "Hello & world", "url": "https://example.org/news?q=a&b=c",
            "summary": "First & second. Third.", "published_at": "2026-11-25T15:59:07+00:00",
            "date_status": "ok", "tags": ["AI"],
        }])

    def test_skip_invalid_entries_but_keep_valid_ones(self):
        for link in ["javascript:alert(1)", "ftp://example.org/x", "https://example.org:bad/a", "//example.org/x"]:
            with self.subTest(link=link):
                items, warnings = parse_feed(rss("<link>https://example.org</link>",
                                                 "<title>Unsafe</title><link>" + link + "</link>", BASIC))
                self.assertEqual(len(items), 1)
                self.assertIn("2 条", warnings[0])
                self.assertIsNone(items[0]["uid"])

    def test_missing_and_unusable_dates(self):
        entries, warnings = parse_feed(rss(BASIC, BASIC + "<pubDate>n/a</pubDate>",
                                           BASIC + "<pubDate>2026-11-25T17:00:00</pubDate>"))
        self.assertEqual([entry["date_status"] for entry in entries], ["missing", "invalid", "invalid"])
        self.assertTrue(all(entry["published_at"] is None for entry in entries))
        self.assertIn("1 条日期缺失、2 条日期无效", warnings[0])

    def test_dc_iso_date(self):
        item = BASIC + "<dc:date xmlns:dc='http://purl.org/dc/elements/1.1/'>2026-11-25T10:00:00Z</dc:date>"
        self.assertEqual(parse_feed(rss(item))[0][0]["published_at"], "2026-11-25T10:00:00+00:00")

    def test_empty_and_invalid_responses(self):
        self.assertEqual(parse_feed(rss()), ([], []))
        for body in (b"<html/>", b"<rss>", b"<rss/>", rss("<title>No link</title>"),
                     b'<!DOCTYPE rss [<!ENTITY x "unexpected">]><rss><channel/></rss>',
                     b"x" * (MAX_FEED_BYTES + 1)):
            with self.subTest(size=len(body)):
                with self.assertRaises(FeedError):
                    parse_feed(body)

    def test_fetch_propagates_transport_failure(self):
        with patch("assistant_news.feeds.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(URLError):
                fetch_feed({"url": "https://example.org/feed"})

    def test_fetch_rejects_partial_response(self):
        response = MagicMock()
        response.__enter__.return_value.status = 206
        with patch("assistant_news.feeds.urlopen", return_value=response):
            with self.assertRaises(FeedError):
                fetch_feed({"url": "https://example.org/feed"})

    def test_closed_window_at_fractional_precision_across_offsets(self):
        sgt = timezone(timedelta(hours=8))
        end = datetime(2026, 11, 26, 9, tzinfo=sgt)
        start = end - timedelta(hours=72)
        self.assertTrue(in_window("2026-11-23T01:00:00+00:00", start, end))
        self.assertTrue(in_window("2026-11-26T01:00:00+00:00", start, end))
        self.assertFalse(in_window("2026-11-23T00:59:59.999999+00:00", start, end))
        self.assertFalse(in_window("2026-11-26T01:00:00.000001+00:00", start, end))
        self.assertTrue(in_window(None, start, end))
        with self.assertRaises(ValueError):
            in_window(None, end, start)
        with self.assertRaises(ValueError):
            in_window(None, start.replace(tzinfo=None), end)
