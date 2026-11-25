# RSS 来源与读取记录

两源均可匿名通过 HTTPS GET 获取 RSS 2.0。以下时间均为 Asia/Singapore（UTC+08:00）。这里的数量是订阅响应中的条目数。最终收录量见相应日期的结构化日报。

| 来源与网站 | RSS 地址 | 语言、内容与选择原因 |
| --- | --- | --- |
| [TechCrunch AI](https://techcrunch.com/category/artificial-intelligence/) | [AI 专栏订阅](https://techcrunch.com/category/artificial-intelligence/feed/) | 英语。科技媒体追踪多家公司的交易、产品、芯片和监管，提供行业报道视角。 |
| [OpenAI News](https://openai.com/news/) | [官方新闻订阅](https://openai.com/news/rss.xml) | 英语。厂商直接发布模型研究、产品、安全和应用案例，补充媒体报道。 |

## 2026 年 11 月 26 日验证

先执行 curl 完整 GET，独立解析收到的 XML；随后用系统 Python 3.9.6 运行项目的 fetch_feed 再次获取，两次的条目数一致。

| 来源 | GET 完成时间 | HTTP、响应类型 | 字节数 | 条目数 | 发布于当时最近 72 小时 |
| --- | --- | --- | ---: | ---: | ---: |
| TechCrunch AI | 02:11:30 | 200，application/rss+xml | 18,770 | 20 | 20 |
| OpenAI News | 02:11:32 | 200，text/xml | 870,107 | 1,430 | 8 |

- TechCrunch 样例的 RSS 发布时间为 11 月 26 日 01:35:58，报道各州总检察长对 Character AI 聊天记录拍卖计划的异议。[RSS 条目原文链接](https://techcrunch.com/2026/11/25/state-ags-fight-character-ais-plan-to-auction-off-users-private-chats/)
- OpenAI 样例的 RSS 发布时间为 11 月 24 日 19:00:00，介绍使用 Codex 和 Astra 分析天文数据的案例。[RSS 条目原文链接](https://openai.com/index/searching-for-distant-planets-with-astra)

原始响应 SHA-256：TechCrunch 为 `0d23ed07d9a09cadc9ec2813421cd40a08f003ac9d79566e1d1d95456a13f57f`，OpenAI 为 `c6c4ef92198fd46c0440ae73da912e5bac79f6a7daca9bd9988e90eb8c929bbd`。RSS 持续更新，后续抓取的哈希及条目数可能变化。验证期间沙箱的 DNS 查询失败，获准联网后两源均读取成功，两项来源无需更换。

## 读取口径

- 仅读取发布方 RSS 中的标题、链接、GUID、时间、分类标签和简介。简介去除 HTML 标记；缺少简介时保留空值。文章原文未抓取。
- 读取带时区的 RSS pubDate 或 Dublin Core date，转换为 UTC 存储、在日报中以新加坡时间展示。起止端点均包含。
- 缺失日期记为 missing；日期损坏或无可判定时区记为 invalid。两者均保留空的发布时间，允许首次观察时进入相关性筛选，标明无法验证其发布时间是否属于收集窗口。去重后不会在每次抓取时重复记为新增。
- 缺少标题或有效绝对 HTTP(S) 原文链接的条目跳过，并按源汇总警告。如果源含条目但全部无效，该源整次读取失败。空的有效 RSS channel 可成功返回零条。网络错误、无效 XML、非 RSS 响应或超过 8 MiB 上限均视为该源读取失败。
- 订阅仅提供发布方当前保留的条目。TechCrunch 本次只提供 20 条，长时间停机后，已经移出订阅的旧文章无法依靠 RSS 补取。两家来源的语言、主题及厂商立场也限制了报道覆盖面。
