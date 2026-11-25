# 模块接口与文件归属
Python 3.9+，标准库，进程间通过 SQLite 与 POSIX 文件锁协调。所有接口使用普通 dict/list。
- A 独占 assistant_news/feeds.py、config/sources.json、docs/sources.md、tests/test_feeds.py。sources.json 是数组，每项含 id、name、site、url、language、focus、reason。fetch_feed(source) 返回 (entries, warnings)，读取失败抛异常；entries 每项含 uid（可空）、title、url（绝对 HTTP(S)）、summary（纯文本）、published_at（UTC ISO 带偏移或 None）、date_status（ok/missing/invalid），可选 tags（字符串数组）。in_window(published_at, start, end) 接收 UTC ISO 日期或 None 和两个 aware datetime，边界闭区间，None 返回 True（按首次观察，明确标注范围未核实）。
- B 独占 assistant_news/render.py、tests/test_render.py。render_html(report)、render_markdown(report) 各返回字符串，不碰文件。report 含 day (YYYY-MM-DD)、updated_at、range_start、range_end（带偏移 ISO）、mode（中文）、new_count、total_count、sources、articles。sources 每项含 id/name/status（updated/unchanged/failed）/range_start/range_end/new_count/error/warnings（字符串数组）。articles 每项包含 title/source（名称）/source_id/published_at/date_status/url/category/collected_at/summary。分类依次为 模型与研究、产品与工具、行业与政策、待确认。日期显示 Asia/Singapore。日报按采集日归档。
- 主控负责其他文件（数据库、分类、CLI、调度、输出、文档及版本控制）。跨模块调整需先沟通。
- 独立验收者在主要实现完成后检查，可新增 tests/test_acceptance.py 及 work/ 验证材料，不编辑实现。
