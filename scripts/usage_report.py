#!/usr/bin/env python3
"""Report token usage and estimated cost for local agent sessions.

Reads rollout files written by local CLI agents and prints the usage of the
most recent conversation segment together with the whole session:

    本段会话：输入 123456 / 缓存命中 98765 / 输出 4321 / 命中率 80.0% / 费用 ¥0.12
    整个会话：输入 987654 / 缓存命中 876543 / 输出 43210 / 命中率 88.8% / 费用 ¥0.50

Usage:
    python usage_report.py --latest            # most recent segment/session (default)
    python usage_report.py --whole             # whole latest session
    python usage_report.py --all               # per-session summary
    python usage_report.py --agent zcode|codex|claude|opencode

Supported agents and data sources:
    ZCode    ~/.zcode/cli/rollout/model-io-*.jsonl
             usage: response.usage {inputTokens, cacheReadTokens, outputTokens}
             "segment" = records since the latest request containing a user message
    Codex    ~/.codex/sessions/**/rollout-*.jsonl
             usage: payload.info.total_token_usage {input_tokens, cached_input_tokens, output_tokens}
    Claude   ~/.claude/projects/**/*.jsonl
             usage: message.usage {input_tokens, cache_read_input_tokens, output_tokens}
             "segment" = records since the latest "type":"user" record
    OpenCode <data>/opencode/opencode.db  (SQLite; %LOCALAPPDATA% on Windows,
             $XDG_DATA_HOME or ~/.local/share otherwise)
             usage: message.data.tokens {input, output, cache:{read, write}}

Cost uses DeepSeek official peak/off-peak pricing (CNY per 1M tokens), effective
2026-08-17 00:00 Beijing: peak 09:00-12:00 & 14:00-18:00 Beijing = 2x off-peak.
Update the PRICES_* tables if the official rates change (platform.deepseek.com).
Note: OpenCode is multi-provider; the estimate assumes DeepSeek pricing.
Requires Python 3.9+, standard library only (sqlite3 included).
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

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


def _opencode_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "opencode"


AGENTS = {
    "zcode": Path.home() / ".zcode" / "cli" / "rollout",
    "codex": Path.home() / ".codex" / "sessions",
    "claude": Path.home() / ".claude" / "projects",
    "opencode": _opencode_dir(),
}


def parse_iso(s: str) -> dt.datetime | None:
    """Parse an ISO timestamp, honoring timezone info if present."""
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_time(v) -> dt.datetime | None:
    """Parse a timestamp that may be ISO text or epoch milliseconds."""
    if isinstance(v, (int, float)):
        if v > 10**12:  # milliseconds
            v = v / 1000
        try:
            return dt.datetime.fromtimestamp(v).astimezone()
        except (OSError, OverflowError, ValueError):
            return None
    return parse_iso(v)


def pricing_for(started_at: dt.datetime | None, model: str):
    """Pick the price table and billing period for a session start time."""
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


# --- per-agent record parsing ----------------------------------------------


def has_user_message(agent: str, rec: dict) -> bool:
    """True if this record marks the start of a new user turn (segment boundary).

    Check the *last* message, not any message: request.messages always carries
    the full conversation history, so "contains a user message" would match
    every record and shrink the segment to the last record of the file.
    """
    if agent == "zcode":
        msgs = (rec.get("request") or {}).get("messages") or []
        return bool(msgs) and (msgs[-1] or {}).get("role") == "user"
    if agent == "claude":
        return rec.get("type") == "user"
    return False  # codex / opencode: segment not detectable here


def usage_of(agent: str, rec: dict) -> dict | None:
    """Extract {input, cached, output, model, started_at} from one record."""
    if agent == "zcode":
        usage = (rec.get("response") or {}).get("usage") or {}
        if not usage:
            return None
        m = rec.get("model")
        return {
            "input": int(usage.get("inputTokens") or 0),
            "cached": int(usage.get("cacheReadTokens") or 0),
            "output": int(usage.get("outputTokens") or 0),
            "model": m.get("modelId") if isinstance(m, dict) else (str(m) if m else None),
            "started_at": parse_iso(rec.get("startedAt")),
        }
    if agent == "codex":
        payload = rec.get("payload") or {}
        usage = (payload.get("info") or {}).get("total_token_usage")
        if not isinstance(usage, dict):
            return None
        m = payload.get("model") or (payload.get("state") or {}).get("model")
        # DeepSeek bills reasoning output tokens at the output rate; the API
        # reports them separately from output_tokens.
        out = int(usage.get("output_tokens") or 0) + int(usage.get("reasoning_output_tokens") or 0)
        return {
            "input": int(usage.get("input_tokens") or 0),
            "cached": int(usage.get("cached_input_tokens") or 0),
            "output": out,
            "model": str(m) if m else None,
            "started_at": parse_iso(rec.get("timestamp") or payload.get("timestamp")),
        }
    if agent == "claude":
        if rec.get("type") != "assistant":
            return None
        msg = rec.get("message") or {}
        usage = msg.get("usage") or {}
        if not usage:
            return None
        return {
            "input": int(usage.get("input_tokens") or 0),
            "cached": int(usage.get("cache_read_input_tokens") or 0),
            "output": int(usage.get("output_tokens") or 0),
            "model": msg.get("model"),
            "started_at": parse_iso(rec.get("timestamp")),
        }
    return None


# --- file / database reading -----------------------------------------------


def _iter_records(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def rollout_files(agent: str) -> list[Path]:
    """All rollout files for an agent, oldest first."""
    if agent == "opencode":
        db = AGENTS[agent] / "opencode.db"
        return [db] if db.exists() else []
    root = AGENTS[agent]
    pattern = "model-io-*.jsonl" if agent == "zcode" else "**/*.jsonl"
    paths = sorted(glob.glob(str(root / pattern), recursive=True), key=os.path.getmtime)
    return [Path(p) for p in paths]


def detect_agent() -> str:
    """Agent with the most recently modified rollout file."""
    best, best_mtime = None, -1
    for agent in AGENTS:
        files = rollout_files(agent)
        if files:
            t = os.path.getmtime(files[-1])
            if t > best_mtime:
                best, best_mtime = agent, t
    return best


def _sum_rows(rows) -> dict:
    rows = list(rows)  # materialize: the input may be a generator, used several times
    return {
        "input": sum(u["input"] for u in rows),
        "cached": sum(u["cached"] for u in rows),
        "output": sum(u["output"] for u in rows),
        "model": next((u["model"] for u in rows if u.get("model")), None),
        "started_at": next((u["started_at"] for u in rows if u.get("started_at")), None),
    }


def aggregate_file(path: Path, agent: str, latest_segment_only: bool) -> dict | None:
    """Aggregate usage in one rollout file, optionally from the last user turn."""
    rows, user_idx = [], []
    for idx, rec in enumerate(_iter_records(path)):
        if has_user_message(agent, rec):
            user_idx.append(idx)
        u = usage_of(agent, rec)
        if u:
            rows.append((idx, u))
    if not rows:
        return None
    if agent == "codex":
        # Codex total_token_usage records are CUMULATIVE session totals (each
        # record is the running total so far); the last record is the final
        # session total. Summing them would overcount by several times, and
        # per-request/segment data is not available from cumulative snapshots.
        rows = rows[-1:]
    elif latest_segment_only and user_idx:
        start = user_idx[-1]
        seg = [u for i, u in rows if i >= start]
        if not seg:
            seg = [rows[-1][1]]
        rows = [(0, u) for u in seg]
    return _sum_rows(u for _, u in rows)


def opencode_sessions(db: Path) -> list[tuple[str, dict, dict]]:
    """OpenCode: one SQLite db holds all sessions.

    Returns [(label, full_agg, segment_agg)] ordered by last activity.
    """
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.execute(
            "SELECT id, session_id, time_created, data FROM message ORDER BY time_created")
        msgs = cur.fetchall()
        conn.close()
    except (sqlite3.Error, OSError):
        return []

    by_session: dict[str, list[dict]] = {}
    for _mid, sid, t, data_json in msgs:
        try:
            data = json.loads(data_json)
        except (TypeError, json.JSONDecodeError):
            continue
        tokens = data.get("tokens") or {}
        cache = tokens.get("cache") or {}
        u = {
            "input": int(tokens.get("input") or 0),
            "cached": int(cache.get("read") or 0),
            "output": int(tokens.get("output") or 0),
            "model": data.get("modelID") or data.get("model"),
            "started_at": parse_time(t),
            "_user": data.get("role") == "user",
        }
        by_session.setdefault(sid, []).append(u)

    out = []
    for sid, us in by_session.items():
        full = _sum_rows(us)
        seg = full
        last_user = max((i for i, u in enumerate(us) if u.get("_user")), default=-1)
        if last_user >= 0:
            tail = [u for u in us[last_user:] if not u.get("_user")]
            if tail:
                seg = _sum_rows(tail)
        out.append((sid, full, seg))
    out.sort(key=lambda x: x[1]["started_at"] or dt.datetime.min)
    return out


def fmt(agg: dict, show_meta: bool = False) -> str:
    inp, cached, out = agg["input"], agg["cached"], agg["output"]
    hit = (cached / inp * 100) if inp else 0.0
    price, period = pricing_for(agg["started_at"], agg["model"])
    cost = (cached * price[0] + (inp - cached) * price[1] + out * price[2]) / 1_000_000
    line = (f"输入 {inp} / 缓存命中 {cached} / 输出 {out} / "
            f"命中率 {hit:.1f}% / 费用 ¥{cost:.2f}")
    if show_meta:
        line += f" / 模型 {agg['model'] or DEFAULT_MODEL} / {period}"
    return line


def _sessions(agent: str) -> list[tuple[str, dict, dict]]:
    """[(label, full_agg, segment_agg)] for every session of an agent."""
    if agent == "opencode":
        files = rollout_files(agent)
        return opencode_sessions(files[0]) if files else []
    out = []
    for fp in rollout_files(agent):
        full = aggregate_file(fp, agent, latest_segment_only=False)
        if full is None:
            continue
        seg = aggregate_file(fp, agent, latest_segment_only=True)
        out.append((fp.name, full, seg))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Report token usage and estimated cost for local agent sessions")
    ap.add_argument("--latest", action="store_true",
                    help="most recent conversation segment where detectable, else session [default]")
    ap.add_argument("--whole", action="store_true", help="whole latest session")
    ap.add_argument("--all", action="store_true", help="per-session summary")
    ap.add_argument("--agent", choices=sorted(AGENTS), default="auto",
                    help="agent to read (default: auto-detect)")
    args = ap.parse_args()

    agent = detect_agent() if args.agent == "auto" else args.agent
    sessions = _sessions(agent)
    if not sessions:
        print(f"No usage data found for agent '{agent}' under {AGENTS[agent]}")
        return 1

    if args.all:
        total = {"input": 0, "cached": 0, "output": 0}
        for label, full, _seg in sessions:
            print(f"{label}: {fmt(full, show_meta=True)}")
            for k in total:
                total[k] += full[k]
        inp, cached, out = total["input"], total["cached"], total["output"]
        hit = (cached / inp * 100) if inp else 0.0
        cost = 0.0
        for _label, full, _seg in sessions:
            price, _ = pricing_for(full["started_at"], full["model"])
            cost += (full["cached"] * price[0] + (full["input"] - full["cached"]) * price[1]
                     + full["output"] * price[2]) / 1_000_000
        print(f"全部会话 {len(sessions)} 个：输入 {inp} / 缓存命中 {cached} / 输出 {out} / "
              f"命中率 {hit:.1f}% / 费用 ¥{cost:.2f}")
        return 0

    label, full, seg = sessions[-1]
    if agent == "codex":
        # Codex stores only cumulative session totals, so there is no segment:
        # report the whole session on a single line.
        print(f"整个会话：{fmt(full)}")
    elif args.whole:
        print(f"整个会话：{fmt(full, show_meta=True)}")
    else:
        print(f"本段会话：{fmt(seg)}")
        print(f"整个会话：{fmt(full)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
