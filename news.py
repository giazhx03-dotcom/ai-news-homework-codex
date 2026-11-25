#!/usr/bin/env python3
"""AI 行业新闻收集助手命令行。"""
import argparse
import json
import sys
from pathlib import Path

from assistant_news.collector import collect, instant

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="区间开始（ISO 8601，未写时区按新加坡时间）")
    parser.add_argument("--end", help="区间结束（含边界）")
    parser.add_argument("--scheduled", action="store_true", help="标记 launchd 调用")
    args = parser.parse_args(argv)
    if bool(args.start) != bool(args.end):
        parser.error("--start 与 --end 需同时指定")
    try:
        bounds = (instant(args.start), instant(args.end)) if args.start else None
        if bounds and bounds[0] > bounds[1]:
            raise ValueError("开始时间晚于结束时间")
        sources = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
        report = collect(ROOT, sources, bounds=bounds, trigger="launchd" if args.scheduled else "命令行")
    except Exception as exc:
        print(f"收集任务异常：{exc}", file=sys.stderr)
        return 1
    print(f'{report["updated_at"]} | 新增 {report["new_count"]} | 当日累计 {report["total_count"]}')
    for source in report["sources"]:
        state = {"failed": "读取失败", "updated": "成功有更新", "unchanged": "成功无更新"}[source["status"]]
        print(f'{source["name"]} | {state} | 新增 {source["new_count"]} | {source["error"]}'.rstrip(" |"))
    return 2 if any(s["status"] == "failed" for s in report["sources"]) else 0


if __name__ == "__main__":
    sys.exit(main())
