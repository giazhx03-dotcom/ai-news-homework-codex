"""Render a daily report from its persisted articles and current run metadata."""

import html
import re
from datetime import datetime
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo


CATEGORIES = ("模型与研究", "产品与工具", "行业与政策", "待确认")
SINGAPORE = ZoneInfo("Asia/Singapore")
STATUS = {
    "updated": "成功有更新",
    "unchanged": "成功无更新",
    "failed": "读取失败",
}
DATE_NOTE = "缺少有效发布时间的条目按首次采集日归档，其发布时间是否在收集范围内无法核实。"
SCOPE_NOTE = "分类和简介仅依据 RSS 信息。同日已收录的条目会保留，以下来源状态与新增数对应本次运行。"


def _timestamp(value):
    if not value:
        return "未提供"
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return "时区未提供"
        return instant.astimezone(SINGAPORE).strftime("%Y-%m-%d %H:%M:%S")
    except (AttributeError, TypeError, ValueError, OverflowError):
        return "日期无法解析"


def _published(article):
    if article["date_status"] == "missing":
        return "来源未提供日期"
    if article["date_status"] == "invalid":
        return "来源日期无法解析"
    return _timestamp(article["published_at"])


def _href(value):
    """Allow only absolute web URLs, with no credentials or ambiguous delimiters."""
    if not isinstance(value, str) or not value or re.search(r"[\x00-\x20\x7f\\]", value):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme.lower() not in {"https", "http"} or
                not parts.hostname or parts.username is not None):
            return None
        _ = parts.port  # May reject a malformed or out-of-range port.
    except ValueError:
        return None
    return quote(value, safe=":/?#[]@!$&'*+,;=%~")


def _groups(report):
    groups = {category: [] for category in CATEGORIES}
    for article in report["articles"]:
        category = article["category"]
        groups[category if category in groups else "待确认"].append(article)
    return groups


def _h(value):
    return html.escape(str(value), quote=True)


def _md(value):
    # Keep untrusted feed strings on one line. Escape angle brackets and ampersands
    # before escaping Markdown punctuation so neither raw HTML nor links can form.
    value = html.escape(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~>-])", r"\\\1", value)


def _span(start, end):
    return f"{_timestamp(start)} 至 {_timestamp(end)}"


def _source_html(source):
    status = source["status"]
    tone = {"failed": "error", "unchanged": "quiet", "updated": "fresh"}.get(status, "quiet")
    notes = []
    if source.get("error"):
        notes.append(f'<p class="problem">错误 · {_h(source["error"])}</p>')
    for warning in source.get("warnings", []):
        notes.append(f'<p class="note">提示 · {_h(warning)}</p>')
    return (
        '<li class="source"><div class="source-head">'
        f'<strong>{_h(source["name"])}</strong>'
        f'<span class="status {tone}">{STATUS.get(status, "状态未知")}</span></div>'
        f'<p>本次新增 {_h(source["new_count"])} 篇</p>'
        f'<p class="range">{_h(_span(source["range_start"], source["range_end"]))}</p>'
        + "".join(notes) + '</li>'
    )


def _article_html(article):
    title = _h(article["title"])
    href = _href(article["url"])
    if href:
        title = f'<a href="{_h(href)}" rel="noreferrer">{title}</a>'
    else:
        title += ' <small>（原文链接无效）</small>'
    summary = _h(article.get("summary") or "RSS 未提供简介。")
    return (
        '<article><div class="byline">'
        f'<strong>{_h(article["source"])}</strong>'
        f'<span>发布 · {_h(_published(article))}</span></div>'
        f'<h3 dir="auto">{title}</h3><p class="summary" dir="auto">{summary}</p>'
        f'<p class="collected">采集于 {_h(_timestamp(article["collected_at"]))}</p></article>'
    )


_CSS = """
:root{color-scheme:light;--ink:#182e32;--muted:#4d6262;--line:#d2dfda;--green:#176250;--paper:#f6f8f5}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font:16px/1.65 "Source Sans 3",-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
overflow-wrap:anywhere}main{max-width:1000px;margin:auto;padding:38px 30px 56px}
header{border-top:5px solid var(--green);padding:21px 0 16px}
h1,h2,h3,p{margin:0}h1{font-size:clamp(2rem,5vw,3.2rem);letter-spacing:-.035em;line-height:1.24}
h2{font-size:1.3rem}h3{font-size:1.15rem;line-height:1.45}
.dateline,.run-meta,.byline,.collected,.range,.note,footer{color:var(--muted)}
.dateline{font-weight:650;margin-bottom:6px}.run-meta{margin-top:10px}
.overview{display:grid;grid-template-columns:auto auto 1fr;gap:32px;align-items:center;padding:18px 22px;
background:#e6efe9;border-radius:8px}.metric,.window{display:grid}.metric strong{font-size:1.85rem;
line-height:1.25;font-variant-numeric:tabular-nums}.metric span,.window span{color:var(--muted);font-size:.88rem}
.window{border-left:1px solid #a8c7b9;padding-left:28px}.window b{font-size:.98rem}
.sources{margin:24px 0}.source-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));
gap:10px;list-style:none;padding:0;margin:9px 0 0}.source{background:#fff;border:1px solid var(--line);
border-radius:7px;padding:12px 15px;font-size:.9rem}.source-head,.byline{display:flex;align-items:center;
flex-wrap:wrap;gap:6px 12px}.source-head{justify-content:space-between;margin-bottom:5px;font-size:1rem}
.status{padding:2px 8px;border-radius:5px;font-size:.8rem;font-weight:650}.fresh{background:#dceee1;color:#245d37}
.quiet{background:#edf1f0;color:#455754}.error{background:#fae6db;color:#933a20}.problem{color:#90351e}
.note,.problem{margin-top:4px}.range,.collected{font-size:.8rem}.context{font-size:.9rem;color:var(--muted)}
nav{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}nav a{border:1px solid var(--line);border-radius:5px;
text-decoration:none;padding:4px 11px;background:white;color:var(--green)}
a{color:var(--green);text-decoration-thickness:1px;text-underline-offset:3px}a:hover{text-decoration:underline}
a:focus-visible{outline:3px solid #c27800;outline-offset:3px}
.category{padding-top:16px}.category h2{display:flex;align-items:baseline;gap:10px;
border-bottom:2px solid #a9c3b6;padding:0 0 7px}.count{font-size:.86rem;color:var(--muted);font-weight:500}
article{border-bottom:1px solid var(--line);padding:17px 0}.byline{font-size:.85rem;margin-bottom:3px}
.byline strong{color:var(--ink)}.summary{margin-top:5px}.collected{margin-top:6px}.empty{padding:10px 0;color:var(--muted)}
footer{margin-top:25px;padding-top:12px;border-top:1px solid var(--line);font-size:.85rem}
@media(max-width:590px){main{padding:18px 16px 32px}.overview{grid-template-columns:1fr 1fr;gap:12px}
.window{grid-column:1/-1;border:0;border-top:1px solid #b8cec3;padding:9px 0 0}.sources{margin:17px 0}}
@media print{body{background:white}main{padding:0}nav{display:none}article,.source{break-inside:avoid}}
"""


def render_html(report):
    day = _h(report["day"])
    groups = _groups(report)
    nav = []
    sections = []
    for i, (category, articles) in enumerate(groups.items(), 1):
        nav.append(f'<a href="#section-{i}">{category} · {len(articles)}</a>')
        content = "".join(_article_html(article) for article in articles)
        if not content:
            content = '<p class="empty">本期此分类暂无条目。</p>'
        sections.append(
            f'<section id="section-{i}" class="category"><h2>{category}'
            f'<span class="count">{len(articles)} 篇</span></h2>{content}</section>'
        )
    sources = "".join(_source_html(source) for source in report["sources"])
    date_note = DATE_NOTE if any(a["date_status"] != "ok" for a in report["articles"]) else ""
    return f"""<!doctype html>
<html lang="zh-Hans"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{day} · AI 行业新闻日报</title><style>{_CSS}</style></head>
<body><main><header><p class="dateline">采集日 · {day}</p><h1>AI 行业新闻日报</h1>
<p class="run-meta">更新时间 {_h(_timestamp(report["updated_at"]))} · Asia/Singapore（新加坡时间）</p></header>
<section class="overview" aria-label="采集概况">
<div class="metric"><strong>{_h(report["new_count"])}</strong><span>本次新增（篇）</span></div>
<div class="metric"><strong>{_h(report["total_count"])}</strong><span>日报总数（篇）</span></div>
<div class="window"><span>本次收集范围 · {_h(report["mode"])}</span>
<b>{_h(_span(report["range_start"], report["range_end"]))}</b></div></section>
<section class="sources"><h2>来源状态</h2><ul class="source-list">{sources}</ul></section>
<p class="context">{SCOPE_NOTE}</p>
<nav aria-label="分类导航">{"".join(nav)}</nav>{"".join(sections)}
<footer>时间统一显示为 Asia/Singapore（UTC+08:00）。{date_note}</footer>
</main></body></html>
"""


def render_markdown(report):
    groups = _groups(report)
    lines = [
        f'# AI 行业新闻日报 · {_md(report["day"])}', "",
        f'- 采集日：{_md(report["day"])}',
        f'- 更新时间：{_timestamp(report["updated_at"])}（Asia/Singapore）',
        f'- 本次收集范围：{_span(report["range_start"], report["range_end"])}（{_md(report["mode"])}）',
        f'- 本次新增：{report["new_count"]} 篇',
        f'- 日报总数：{report["total_count"]} 篇', "", SCOPE_NOTE, "",
        '## 来源状态', "",
    ]
    for source in report["sources"]:
        lines.append(f'- **{_md(source["name"])}** · {STATUS.get(source["status"], "状态未知")} · '
                     f'本次新增 {source["new_count"]} 篇 · {_span(source["range_start"], source["range_end"])}')
        if source.get("error"):
            lines.append(f'  - 错误：{_md(source["error"])}')
        lines.extend(f'  - 提示：{_md(w)}' for w in source.get("warnings", []))
    for category, articles in groups.items():
        lines.extend(["", f'## {category}（{len(articles)} 篇）', ""])
        if not articles:
            lines.append("本期此分类暂无条目。")
        for article in articles:
            title = _md(article["title"])
            href = _href(article["url"])
            if href:
                heading = f'[{title}](<{html.escape(href, quote=False)}>)'
            else:
                heading = f'{title}（原文链接无效）'
            lines.extend([
                f'### {heading}', '',
                f'- 来源：{_md(article["source"])}',
                f'- 发布时间：{_published(article)}',
                f'- 收集时间：{_timestamp(article["collected_at"])}', '',
                _md(article.get("summary") or "RSS 未提供简介。"), '',
            ])
    lines.extend(["", "时间统一显示为 Asia/Singapore（UTC+08:00）。"])
    if any(a["date_status"] != "ok" for a in report["articles"]):
        lines.extend(["", DATE_NOTE])
    return "\n".join(lines).rstrip() + "\n"
