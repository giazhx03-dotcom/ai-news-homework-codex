"""Collect independent source windows and publish recoverable daily snapshots."""
import fcntl
import json
import os
import tempfile
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import feeds, render
from .rules import classify
from .store import canonical_url, connect, remember

SG = ZoneInfo("Asia/Singapore")
UTC = timezone.utc
INITIAL_WINDOW = timedelta(hours=72)
OVERLAP = timedelta(hours=6)


def instant(value):
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SG)
    return moment.astimezone(UTC)


def stamp(moment):
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def local(moment):
    return moment.astimezone(SG).isoformat(timespec="microseconds")


def as_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


@contextmanager
def project_lock(state):
    state.mkdir(parents=True, exist_ok=True)
    with (state / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("另一个收集任务正在运行，已跳过本次调用") from None
        yield


def replace_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temp:
        temp_path = Path(temp.name)
        try:
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def publish(db, outputs):
    # Replay committed reports after an interrupted export, including reports from an earlier day.
    for run in db.execute("SELECT id,day,payload FROM runs WHERE exported=0 ORDER BY id").fetchall():
        report = json.loads(run["payload"])
        files = {"daily.html": render.render_html(report), "daily.md": render.render_markdown(report),
                 "daily.json": run["payload"]}
        for folder in (outputs / "history" / run["day"], outputs / "latest"):
            for name, content in files.items():
                replace_file(folder / name, content)
        with db:
            db.execute("UPDATE runs SET exported=1 WHERE id=?", (run["id"],))


def read_one(db, source, fetcher, start, end, observed, day, manual):
    sid = source["id"]
    info = dict(id=sid, name=source["name"], range_start=local(start), range_end=local(end),
                status="unchanged", new_count=0, error="", warnings=[], entries_read=0,
                in_window_count=0, relevant_count=0, duplicate_count=0)
    db.execute("SAVEPOINT one_source")
    try:
        entries, warnings = fetcher(source)
        info.update(warnings=list(warnings), entries_read=len(entries))
        for entry in entries:
            if not feeds.in_window(entry["published_at"], start, end):
                continue
            info["in_window_count"] += 1
            category = classify(entry)
            if not category:
                continue
            try:
                canonical_url(entry["url"])
            except (ValueError, UnicodeError):
                info["warnings"].append("跳过无效原文链接")
                continue
            info["relevant_count"] += 1
            if remember(db, entry, source, category, day, observed):
                info["new_count"] += 1
            else:
                info["duplicate_count"] += 1
        if not manual:
            db.execute("UPDATE cursors SET success_end=? WHERE source=?", (stamp(end), sid))
        if info["new_count"]:
            info["status"] = "updated"
    except Exception as exc:
        db.execute("ROLLBACK TO one_source")
        info.update(status="failed", error=f"{type(exc).__name__} · {exc}", new_count=0)
    finally:
        db.execute("RELEASE one_source")
    return info


def collect(root, sources, fetcher=feeds.fetch_feed, bounds=None, now=None, trigger="命令行"):
    state = root / "state"
    outputs = root / "outputs"
    with project_lock(state), closing(connect(state / "news.sqlite3")) as db:
        publish(db, outputs)
        moment = now or datetime.now(UTC)
        day = moment.astimezone(SG).date().isoformat()
        observed = local(moment)
        statuses = []
        has_cursor = False
        with db:
            # Start a real transaction before savepoints.
            db.execute("BEGIN")
            for source in sources:
                if bounds:
                    start, end = bounds
                else:
                    end = moment
                    db.execute("INSERT OR IGNORE INTO cursors(source,initial_start) VALUES(?,?)",
                               (source["id"], stamp(end - INITIAL_WINDOW)))
                    cursor = db.execute("SELECT * FROM cursors WHERE source=?", (source["id"],)).fetchone()
                    start = instant(cursor["initial_start"])
                    if cursor["success_end"]:
                        has_cursor = True
                        start = max(start, instant(cursor["success_end"]) - OVERLAP)
                        if instant(cursor["success_end"]) > end:
                            raise ValueError("系统时间早于上次成功时间，请核对系统时钟")
                statuses.append(read_one(db, source, fetcher, start, end, observed, day, bool(bounds)))
            articles = [dict(row) for row in db.execute(
                "SELECT title,source,source_id,published_at,date_status,url,category,collected_at,summary "
                "FROM articles WHERE day=? ORDER BY published_at IS NULL,published_at DESC,id", (day,))]
            report = dict(day=day, updated_at=local(now or datetime.now(UTC)), started_at=observed, trigger=trigger,
                          range_start=min(s["range_start"] for s in statuses),
                          range_end=max(s["range_end"] for s in statuses),
                          mode="指定时间范围" if bounds else ("按来源增量" if has_cursor else "首次窗口（72 小时起）"),
                          new_count=sum(s["new_count"] for s in statuses), total_count=len(articles),
                          sources=statuses, articles=articles)
            db.execute("INSERT INTO runs(day,payload) VALUES(?,?)", (day, as_json(report)))
        # Log completion of ingestion even if publishing later needs to be retried.
        log = outputs / "logs" / "runs.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({k: v for k, v in report.items() if k != "articles"}, ensure_ascii=False) + "\n")
        publish(db, outputs)
        return report
