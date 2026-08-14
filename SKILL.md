---
name: token-usage-report
description: "Estimate per-conversation token usage, cache hit rate and CNY cost from the agent's own local session logs. Use whenever the user asks about token usage, token cost, spending, billing, 用量, 费用, 花费, or wants a usage summary appended to the final reply — run before composing the final reply. The installing agent writes one small adapter that converts its own logs into the record format (see SKILL.md)."
---

# Token Usage Report

Estimates the token usage and cost of the most recent conversation turn and the
whole session, printing two lines:

    本段会话：输入 123456 / 缓存命中 98765 / 输出 4321 / 命中率 80.0% / 费用 ¥0.12
    整个会话：输入 987654 / 缓存命中 876543 / 输出 43210 / 命中率 88.8% / 费用 ¥0.50

## Install — non-system drive (required)

Install this skill on a **non-system drive** — never into the system drive's
default skill directories:

```bash
mkdir -p /d/agents/skills          # Windows: D:\agents\skills
cp -r token-usage-report /d/agents/skills/
```

Then register that path with your agent (or reference it by absolute path).
Reason: keeps the system drive clean and avoids permission issues.

**Multi-agent path discipline**: each agent on the same machine installs to
its OWN independent path — put the agent's name in the path (e.g.
`D:\agents\skills\zcode\token-usage-report`,
`D:\agents\skills\codex\token-usage-report`) and never share or overwrite
another agent's copy. The adapter is agent-private (each agent writes its own),
so a shared directory invites clobbering and concurrent-write conflicts.

## One-time setup: the installing agent writes its adapter

The core script knows nothing about any agent. **You** (the installing agent)
write one small adapter, `scripts/adapters/<your-agent>.py`, that reads YOUR
session logs and prints one JSON object per request line:

    {"input": 123456, "cached": 98765, "output": 4321,
     "started_at": "2026-08-14T10:00:00+08:00", "model": "deepseek-v4-flash",
     "turn_start": true}

- `input` — total input tokens of the request (cache-hit + miss)
- `cached` — cache-hit input tokens
- `output` — output tokens (include reasoning tokens if your provider bills them as output)
- `started_at` — ISO timestamp or null (drives peak/off-peak pricing)
- `model` — model id or null (default: deepseek-v4-flash)
- `turn_start` — true on the FIRST request of a new user turn (segment boundary)

Start from `scripts/adapters/template.py`. Common pitfalls: if your agent's
records are **cumulative** running totals (e.g. Codex `total_token_usage`),
emit only the LAST record per session — never sum cumulative values; if your
logs are compressed (e.g. DSH zstd), decompress first (`pip install zstandard`).

## Run — before every final reply

```bash
python3 <skill-dir>/scripts/usage_report.py <records.jsonl>   # or pipe via stdin
```

Append both output lines **verbatim** to the final reply. If the reply is
markdown, put them in a fenced code block so the two lines stay separate.

- Exit 0 → always include the lines, even if the numbers look the same as last time.
- "No usage data found" → skip silently; do not ask the user.

## Cost model

DeepSeek official pricing (CNY / 1M tokens), effective 2026-08-17 00:00 Beijing
time: peak hours 09:00–12:00 and 14:00–18:00 Beijing = 2× off-peak; sessions
before 2026-08-17 use flat legacy rates.

| Model            | Period   | cached-in | miss-in | out  |
|------------------|----------|-----------|---------|------|
| deepseek-v4-flash| off-peak | 0.05      | 1.5     | 4.5  |
| deepseek-v4-flash| peak     | 0.10      | 3.0     | 9.0  |
| deepseek-v4-flash| legacy   | 0.02      | 1.0     | 2.0  |
| deepseek-v4-pro  | off-peak | 0.15      | 4.5     | 13.5 |
| deepseek-v4-pro  | peak     | 0.30      | 9.0     | 27.0 |
| deepseek-v4-pro  | legacy   | 0.025     | 3.0     | 6.0  |

The billing period is derived from the window's `started_at`. Update the
`PRICES_*` tables when official rates change (platform.deepseek.com).

## Accuracy

This is an **estimate**, not the provider bill. Expected deviations, typically
~1% of tokens per turn: the provider prices each request by its own time-of-day
(we use the window start time) and counts freshly-added context (new user
message, tool results) as cache-miss, while local logs may report it as
cache-hit; local logs may also miss aborted/non-interactive requests.

## Security

Reads only local files; never touches API keys or credentials; never echo log
contents — print only the aggregated numbers.
