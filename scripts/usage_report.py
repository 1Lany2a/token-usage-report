#!/usr/bin/env python3
"""Estimate token usage and cost for one agent session from per-request records.

The core is agent-agnostic: the installing agent writes a small adapter that
reads ITS OWN session logs and emits one JSON object per line:

    {"input": 123456, "cached": 98765, "output": 4321,
     "started_at": "2026-08-14T10:00:00+08:00", "model": "deepseek-v4-flash",
     "turn_start": true}

- input      : total input tokens of one request (cache-hit + miss)
- cached     : cache-hit input tokens
- output     : output tokens (include reasoning tokens if billed as output)
- started_at : ISO timestamp or null (drives peak/off-peak pricing)
- model      : model id or null (default: deepseek-v4-flash)
- turn_start : true on the first request of a new user turn (segment boundary)

Prints the most recent turn and the whole session:

    本段会话：输入 123456 / 缓存命中 98765 / 输出 4321 / 命中率 80.0% / 费用 ¥0.12
    整个会话：输入 987654 / 缓存命中 876543 / 输出 43210 / 命中率 88.8% / 费用 ¥0.50

Usage:
    python usage_report.py records.jsonl
    python usage_report.py --whole records.jsonl
    cat records.jsonl | python usage_report.py

Cost uses DeepSeek official pricing (CNY per 1M tokens), effective 2026-08-17
00:00 Beijing: peak 09:00-12:00 & 14:00-18:00 Beijing = 2x off-peak; before
that, flat legacy rates. Update the PRICES_* tables if the official rates
change (platform.deepseek.com). Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

# Windows consoles default to GBK and cannot print the half-width '¥' (U+00A5).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_MODEL = "deepseek-v4-flash"
# model -> (cached_input_cny_per_m, miss_input_cny_per_m, output_cny_per_m)
PRICES_LEGACY = {  # flat rates before 2026-08-17 00:00 Beijing
    "deepseek-v4-flash": (0.02, 1.0, 2.0),
    "deepseek-v4-pro": (0.025, 3.0, 6.0),
}
PRICES_PEAK = {  # daily 09:00-12:00 & 14:00-18:00 Beijing
    "deepseek-v4-flash": (0.10, 3.0, 9.0),
    "deepseek-v4-pro": (0.30, 9.0, 27.0),
}
PRICES_OFFPEAK = {  # all other times, half of peak
    "deepseek-v4-flash": (0.05, 1.5, 4.5),
    "deepseek-v4-pro": (0.15, 4.5, 13.5),
}
NEW_PRICING_FROM = dt.datetime(2026, 8, 17, 0, 0)  # Beijing time


def parse_iso(s: str) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def pricing_for(started_at: dt.datetime | None, model: str):
    """Price table and billing period for a window start time."""
    model = (model or "").lower()
    if model not in PRICES_LEGACY:
        model = DEFAULT_MODEL
    now = started_at or dt.datetime.now()
    if now.tzinfo is None:
        now = now.astimezone()
    if now < NEW_PRICING_FROM.astimezone(now.tzinfo):
        return PRICES_LEGACY[model], "legacy"
    peak = (9 <= now.hour < 12) or (14 <= now.hour < 18)
    return (PRICES_PEAK if peak else PRICES_OFFPEAK)[model], "peak" if peak else "off-peak"


def read_records(source) -> list[dict]:
    """Parse JSONL records, keeping those with input tokens."""
    rows = []
    for line in source:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("input") is None:
            continue
        rows.append(rec)
    return rows


def totals(rows: list[dict]) -> dict:
    t = {"input": 0, "cached": 0, "output": 0, "model": None, "started_at": None}
    for r in rows:
        t["input"] += int(r.get("input") or 0)
        t["cached"] += int(r.get("cached") or 0)
        t["output"] += int(r.get("output") or 0)
        if t["model"] is None and r.get("model"):
            t["model"] = r["model"]
        if t["started_at"] is None and r.get("started_at"):
            t["started_at"] = parse_iso(r["started_at"])
    return t


def fmt(t: dict, show_meta: bool = False) -> str:
    inp, cached, out = t["input"], t["cached"], t["output"]
    hit = (cached / inp * 100) if inp else 0.0
    price, period = pricing_for(t["started_at"], t["model"])
    cost = (cached * price[0] + (inp - cached) * price[1] + out * price[2]) / 1_000_000
    line = (f"输入 {inp} / 缓存命中 {cached} / 输出 {out} / "
            f"命中率 {hit:.1f}% / 费用 ¥{cost:.2f}")
    if show_meta:
        line += f" / 模型 {t['model'] or DEFAULT_MODEL} / {period}"
    return line


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Estimate token usage and cost from per-request records")
    ap.add_argument("records", nargs="?", help="JSONL records file (default: stdin)")
    ap.add_argument("--whole", action="store_true",
                    help="print only the whole session, not the segment")
    args = ap.parse_args()

    f = open(args.records, encoding="utf-8") if args.records else sys.stdin
    rows = read_records(f)
    if f is not sys.stdin:
        f.close()
    if not rows:
        print("No usage data found")
        return 1

    full = totals(rows)
    if args.whole:
        print(f"整个会话：{fmt(full, show_meta=True)}")
        return 0

    last_turn = max((i for i, r in enumerate(rows) if r.get("turn_start")), default=0)
    seg = totals(rows[last_turn:])
    print(f"本段会话：{fmt(seg)}")
    print(f"整个会话：{fmt(full)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
