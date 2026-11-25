import unittest
from html.parser import HTMLParser

from assistant_news.render import CATEGORIES, render_html, render_markdown


def report_fixture():
    article = dict(
        title='模型 <script>alert("x")</script> & *安全*',
        source='研究 <团队>', source_id='lab', published_at='2026-11-24T16:30:00Z',
        date_status='ok', url='https://example.org/news/(模型)?x=1&y=2',
        category='模型与研究', collected_at='2026-11-25T01:15:33+00:00',
        summary='RSS 简介 <img src=x onerror=boom()> & [诱饵](https://example.biz)。',
    )
    source = dict(
        id='lab', name='研究 <团队>', status='updated', new_count=1, error=None,
        range_start='2026-11-22T01:15:33Z', range_end='2026-11-25T01:15:33Z',
        warnings=['条目缺字段 <em>1</em>'],
    )
    return dict(
        day='2026-11-25', updated_at='2026-11-25T01:15:33Z',
        range_start=source['range_start'], range_end=source['range_end'],
        mode='首次运行', new_count=1, total_count=1, sources=[source], articles=[article],
    )


class HTMLInspection(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.links = []
        self.text = []
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'a':
            self.links.append(dict(attrs)['href'])

    def handle_data(self, data):
        self.text.append(data)


class ReportRenderTests(unittest.TestCase):
    def setUp(self):
        self.report = report_fixture()

    def test_both_formats_show_categories_status_and_local_time(self):
        for render in (render_html, render_markdown):
            text = render(self.report)
            for value in (*CATEGORIES, '成功有更新', '条目缺字段', '2026-11-25 00:30:00',
                          '2026-11-25 09:15:33', 'Asia/Singapore', '本次收集范围',
                          '日报总数', 'RSS', '本期此分类暂无条目'):
                self.assertIn(value, text)
            self.assertEqual(sorted(CATEGORIES, key=text.index), list(CATEGORIES))

    def test_html_contains_only_safe_links_and_text(self):
        markup = render_html(self.report)
        page = HTMLInspection(markup)
        self.assertNotIn('script', page.tags)
        self.assertNotIn('img', page.tags)
        self.assertNotIn('em', page.tags)
        self.assertIn(self.report['articles'][0]['title'], page.text)
        self.assertIn(self.report['articles'][0]['summary'], page.text)
        self.assertIn('https://example.org/news/%28%E6%A8%A1%E5%9E%8B%29?x=1&y=2', page.links)
        self.assertIn('width=device-width', markup)
        self.assertIn("default-src 'none'", markup)

    def test_markdown_handles_rich_text_and_link_parentheses(self):
        text = render_markdown(self.report)
        self.assertIn(r'\*安全\*', text)
        self.assertIn(r'\[诱饵\]\(', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertNotIn('<img', text)
        self.assertIn('](<https://example.org/news/%28', text)
        self.assertIn('?x=1&amp;y=2>)', text)

    def test_unsafe_and_malformed_urls_become_plain_text(self):
        for value in ['javascript:alert(1)', 'file:///etc/passwd', '//evil.test', '',
                      'https://example.test:NaN/path', 'http://[malformed', 'https://a\n.test',
                      'https://good.test\\@evil.test', 'https://user@private.test']:
            with self.subTest(value=value):
                self.report['articles'][0]['url'] = value
                page = HTMLInspection(render_html(self.report))
                self.assertTrue(all(link.startswith('#section-') for link in page.links))
                self.assertIn('原文链接无效', render_markdown(self.report))

    def test_failure_or_no_update_can_still_show_earlier_articles(self):
        for status, label in [('failed', '读取失败'), ('unchanged', '成功无更新')]:
            self.report.update(new_count=0)
            self.report['sources'][0].update(status=status, new_count=0, error='断线 <error>' if status == 'failed' else '')
            for render in (render_html, render_markdown):
                text = render(self.report)
                self.assertIn(label, text)
                self.assertIn('安全', text)
                self.assertIn('同日已收录的条目会保留', text)
                if status == 'failed':
                    self.assertIn('断线 &lt;error&gt;', text)

    def test_missing_fields_are_described_without_inventing_values(self):
        for date_status, label in [('missing', '来源未提供日期'), ('invalid', '来源日期无法解析')]:
            self.report['articles'][0].update(date_status=date_status, published_at=None, summary='')
            for render in (render_markdown, render_html):
                text = render(self.report)
                self.assertIn('RSS 未提供简介', text)
                self.assertIn(label, text)
                self.assertIn('其发布时间是否在收集范围内无法核实', text)

    def test_empty_report_retains_four_sections_and_status(self):
        self.report.update(articles=[], new_count=0, total_count=0)
        self.report['sources'][0].update(status='unchanged', new_count=0)
        for render in (render_html, render_markdown):
            text = render(self.report)
            self.assertEqual(text.count('本期此分类暂无条目'), 4)
            self.assertIn('成功无更新', text)


if __name__ == '__main__':
    unittest.main()
