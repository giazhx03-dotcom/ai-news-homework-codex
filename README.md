# AI 行业新闻收集助手

用 Python 标准库读取 TechCrunch AI 和 OpenAI News，每日按新加坡采集日生成中文日报。打开[最新 HTML 日报](outputs/latest/daily.html)可浏览分类并点击原文。在 GitHub 仓库页面可以直接阅读[最新 Markdown 日报](outputs/latest/daily.md)。

## 启动

在项目根目录运行。需要 Python 3.9+、系统 IANA 时区数据和可访问两项 RSS 的网络。已验证 macOS 用户环境。

```sh
/usr/bin/python3 -m venv .venv
.venv/bin/python news.py
```

已有本项目虚拟环境时直接执行第二行。指定时间区间的示例（包含两个端点，未写时区时按新加坡时间解释）：

```sh
.venv/bin/python news.py --start 2026-11-23T09:00:00+08:00 --end 2026-11-26T09:00:00+08:00
.venv/bin/python -m unittest discover -v
```

## 数据与阅读方式

| 位置 | 内容 |
| --- | --- |
| `outputs/latest/daily.html`、`daily.md`、`daily.json` | 最近一次收集完成后的三种日报 |
| `outputs/history/YYYY-MM-DD/` | 每个新加坡采集日三份累计快照 |
| `outputs/logs/runs.jsonl` | 实际每轮开始/结束、触发入口、逐来源范围、状态、数量及错误 |
| `outputs/logs/launchd.stdout.log`、`launchd.stderr.log` | 后台启动项输出和解释器错误 |
| `state/news.sqlite3` | 文章、身份别名、各来源成功位置以及每次运行的完整快照 |
| `config/sources.json` | 两项公开来源及选择依据 |

“本次新增”是该轮新入库篇数。“日报总数”是当天首次入库的全部篇数。今天补入一篇昨天发布的文章，归入今天的日报。重复运行、空窗口或单源失败都保留当日已有条目。HTML 和 Markdown 的日期统一为新加坡时间；JSON 的发布时间使用带偏移的 UTC，采集时间和窗口给出新加坡偏移，可无损换算。缺失或无法解析发布时间时保持空值并区分原因，按首次观察收录。

首次无参运行的上限为真实启动时刻，下限为该时刻减 72 小时。以后每源从上次成功位置回退 6 小时，最早回到首次窗口的起点。源失败保留成功位置，首次失败也保留最初的起点。显式起止时间只回补该窗口，不推进日常任务的游标。长时间停机后只能补取仍出现在 RSS 里的条目。

先按“来源 + 条目 ID”查重，再按全局规范化 URL 查重。URL 统一主机名和默认端口，移除片段及常见跟踪参数，保留有语义的查询参数。发现新 ID 或新链接时补记别名。标题相同、标识不同的报道可以同时收录。最先收录的来源获得新增归属。两家媒体写同一事件但链接不同，可以各自保留。

每轮使用独占文件锁。各来源独立回滚，文章、游标和运行快照在同一数据库事务内提交。报告逐文件原子替换；若写文件中断，下次调用先从数据库重发未完成的快照。锁冲突或程序异常返回 1；任一来源失败返回 2，并尽量产出完整状态日报；两源成功返回 0。

## 每天 09:00 自动收集

本项目使用 macOS 用户级 launchd。日历触发使用系统本地时间。安装脚本核验 `/etc/localtime` 指向 Asia/Singapore；更改系统时区后应重新核对。公开仓库提供可移植的 `scheduling/daily.plist.in` 配置模板。运行时生成带本机绝对路径的 plist，仅保存在本机。唯一服务名由项目绝对路径的 SHA-256 前 12 位生成。plist 明确指定虚拟环境解释器、脚本、工作目录和日志。命令均在本项目根目录执行：

```sh
.venv/bin/python scheduling/manage.py generate
.venv/bin/python scheduling/manage.py install
.venv/bin/python scheduling/manage.py status
.venv/bin/python scheduling/manage.py trigger
.venv/bin/python scheduling/manage.py disable
.venv/bin/python scheduling/manage.py uninstall
```

`generate` 仅生成配置。`install` 在当前用户的 `~/Library/LaunchAgents/` 下注册指向项目 plist 的专属链接，并 enable/bootstrap；可重复执行。`trigger` 手动 kickstart。用 `status` 查看 runs、last exit code 和 09:00 日历条件，再核对 JSONL 中 trigger 为 launchd 的记录。停用后可用 install 恢复。uninstall 移除本项目注册项，历史数据仍可手动阅读。更换项目路径前先在原路径卸载；编辑了已加载的配置后先 disable，再 install。

用户登录图形会话时任务才会加载。机器醒着且已登录时可按时触发。睡眠期间错过的日历触发一般在唤醒后合并执行一次；关机或未登录期间没有准点运行保证。遇到 `Operation not permitted` 时，查看 stderr 中被拒绝的路径。在“系统设置 → 隐私与安全性 → 文件与文件夹”核对后台解释器对“文稿”的访问权；交互式终端的权限与后台进程可能不同。授权后重新 trigger，并以退出码和运行日志验证。真实安装与触发记录见[交付验证](outputs/verification.md)。

## 项目记录

- [RSS 来源、样例与实测记录](docs/sources.md)
- [相关性与分类规则](docs/rules.md)
- [协作接口与文件归属](docs/interfaces.md)
- [实际进度、验证和交付限制](outputs/verification.md)
- Git 版本记录可用 `git log --oneline --decorate` 查看。运行库、虚拟环境、缓存、工作草稿及运行日志均排除于 Git；仓库保留真实示例日报。
