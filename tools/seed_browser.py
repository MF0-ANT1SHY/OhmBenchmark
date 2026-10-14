#!/usr/bin/env python3
"""Generate ordinary browser SQLite history offline, without modifying app code."""
import argparse
import datetime
import json
import sqlite3
from pathlib import Path


def generate(path, days, per_day):
    if days < 0 or per_day <= 0:
        raise ValueError('days must be nonnegative and rows per day positive')
    if path.exists():
        raise FileExistsError(f"refusing to replace existing fixture: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE date_table (date TEXT PRIMARY KEY)")
        for day in range(days):
            date = datetime.date(2026, 9, 15) - datetime.timedelta(days=day)
            key = date.strftime("%Y_%m_%d")
            db.execute("INSERT INTO date_table VALUES (?)", (key,))
            table = "history_" + key
            db.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, url TEXT NOT NULL, timestamp TEXT NOT NULL)")
            db.executemany(f"INSERT INTO {table} (title,url,timestamp) VALUES (?,?,?)",
                           [(f"Article {day*per_day+i}", f"https://example.com/{day*per_day+i}", key + " 12:00") for i in range(per_day)])
        db.execute("PRAGMA user_version=1")
    return {"days": days, "rows": days*per_day, "file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--days", type=int, default=60, help='0 prepares ordinary empty browser history')
    parser.add_argument("--per-day", type=int, default=100)
    args = parser.parse_args()
    if args.days < 0 or args.per_day <= 0:
        parser.error("days must be nonnegative and rows per day positive")
    print(json.dumps(generate(args.output, args.days, args.per_day)))


if __name__ == "__main__":
    main()
