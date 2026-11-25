"""读取配置中的公开 RSS 2.0 订阅，输出接口文档约定的纯文本字段。"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MAX_FEED_BYTES = 8 * 1024 * 1024


class FeedError(ValueError):
    """源返回了不能作为成功抓取处理的内容。"""


class _RSSBuilder(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise FeedError("不支持包含 DTD 的订阅")


class _PlainText(HTMLParser):
    breaks = {"br", "p", "div", "li", "h1", "h2", "h3", "blockquote"}
    hidden = {"script", "style", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.hidden:
            self.hidden_depth += 1
        elif tag in self.breaks:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.hidden and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag in self.breaks:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)


def _plain_text(element):
    if element is None:
        return ""
    parser = _PlainText()
    # RSS descriptions are often CDATA/escaped HTML, occasionally real XML children.
    parser.feed(element.text or "")
    for child in element:
        parser.feed(ET.tostring(child, encoding="unicode", method="html"))
    parser.close()
    return " ".join("".join(parser.parts).split())


def _is_article_url(value):
    if not value or any(char.isspace() or ord(char) < 32 or char == "\\" for char in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Reject malformed port numbers.
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.username is None
    except ValueError:
        return False


def _parse_date(raw):
    if not raw:
        return None, "missing"
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
        except (ValueError, OverflowError):
            return None, "invalid"
    if parsed.tzinfo is None:
        return None, "invalid"
    try:
        return parsed.astimezone(timezone.utc).isoformat(), "ok"
    except (ValueError, OverflowError):
        return None, "invalid"


def parse_feed(payload):
    """验证 RSS 信封，返回条目和异常摘要。空的有效 channel 可以成功读取。"""
    if len(payload) > MAX_FEED_BYTES:
        raise FeedError("RSS 超过大小上限 8 MiB")
    try:
        root = ET.fromstring(payload, parser=ET.XMLParser(target=_RSSBuilder()))
    except ET.ParseError as error:
        raise FeedError(f"RSS XML 无效：{error}") from error
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FeedError("订阅缺少 RSS channel，或响应不是 RSS")

    entries, warnings = [], []
    skipped = missing = invalid = 0
    for item in channel.findall("item"):
        title = _plain_text(item.find("title"))
        url = (item.findtext("link") or "").strip()
        if not title or not _is_article_url(url):
            skipped += 1
            continue
        date = (item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()
        published_at, status = _parse_date(date)
        missing += status == "missing"
        invalid += status == "invalid"
        entries.append({
            "uid": (item.findtext("guid") or "").strip() or None,
            "title": title,
            "url": url,
            "summary": _plain_text(item.find("description")),
            "published_at": published_at,
            "date_status": status,
            "tags": [value for value in map(_plain_text, item.findall("category")) if value],
        })
    if skipped:
        warnings.append(f"整个订阅中有 {skipped} 条缺少标题或有效 HTTP(S) 链接，已跳过")
    if missing or invalid:
        warnings.append(f"整个订阅中有 {missing} 条日期缺失、{invalid} 条日期无效；按首次观察处理，发布时间范围未核实")
    if skipped and not entries:
        raise FeedError(warnings[0])
    return entries, warnings


def fetch_feed(source):
    request = Request(source["url"], headers={
        "User-Agent": "AIIndustryNewsCollector/1.0 (public RSS reader)",
        "Accept": "application/rss+xml, application/xml, text/xml",
    })
    with urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise FeedError(f"RSS 请求返回 HTTP {response.status}")
        payload = response.read(MAX_FEED_BYTES + 1)
    return parse_feed(payload)


def in_window(published_at, start, end):
    """两个端点均包含；无法确定发布时间的记录交由持久层按首次观察去重。"""
    if start.utcoffset() is None or end.utcoffset() is None or start > end:
        raise ValueError("收集范围必须使用含时区且顺序正确的时间")
    if published_at is None:
        return True
    published = datetime.fromisoformat(published_at)
    if published.utcoffset() is None:
        raise ValueError("条目发布时间必须包含时区")
    return start <= published <= end
