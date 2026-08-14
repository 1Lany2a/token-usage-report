# token-usage-report

[中文版 README](README.zh-CN.md)

An Agent Skill that estimates per-conversation **token usage, cache hit rate,
and CNY cost** for the agent that installs it:

```
本段会话：输入 123456 / 缓存命中 98765 / 输出 4321 / 命中率 80.0% / 费用 ¥0.12
整个会话：输入 987654 / 缓存命中 876543 / 输出 43210 / 命中率 88.8% / 费用 ¥0.50
```

- Core is agent-agnostic: the **installing agent writes one small adapter**
  that converts its own session logs into a simple JSONL record format.
- Python 3.9+, standard library only (zstd logs need the optional
  `zstandard` package).
- Cost estimate uses **DeepSeek official pricing** (v4-flash/v4-pro,
  peak/off-peak from 2026-08-17, legacy rates before).

## Install — non-system drive (required)

Install on a **non-system drive**, never into the system drive's default skill
directories:

```bash
mkdir -p /d/agents/skills          # Windows: D:\agents\skills
cp -r token-usage-report /d/agents/skills/
```

Register that path with your agent, or reference the skill by absolute path.

## Multi-agent install discipline (same device)

Multiple agents on the same machine must share **one canonical copy**:

1. Use a fixed canonical path (e.g. `D:\agents\skills\token-usage-report`) —
   never copy the skill into per-agent directories.
2. Before installing, check whether the canonical path already has a copy: if
   yes, reuse/overwrite it (update in place); if no, copy there.
3. Reference the shared copy by its **absolute path**, so every agent uses the
   same version — per-agent copies drift apart and produce inconsistent reports.

## One-time setup: write your adapter

The installing agent fills in `scripts/adapters/<your-agent>.py` (start from
`scripts/adapters/template.py`): read YOUR session logs and print one JSON
object per request line —

```json
{"input": 123456, "cached": 98765, "output": 4321,
 "started_at": "2026-08-14T10:00:00+08:00", "model": "deepseek-v4-flash",
 "turn_start": true}
```

- `input` = total input tokens (cache-hit + miss), `cached` = cache-hit input,
  `output` = output tokens (include reasoning tokens if billed as output)
- `started_at` = ISO timestamp or null, `model` = model id or null
- `turn_start` = true on the first request of a new user turn

Pitfalls: if your agent stores **cumulative** running totals (Codex
`total_token_usage`), emit only the LAST record — never sum cumulative values;
decompress compressed logs (DSH zstd) first.

## Usage

```bash
python3 scripts/usage_report.py <records.jsonl>   # two lines: segment + whole
python3 scripts/usage_report.py --whole <records.jsonl>
cat records.jsonl | python3 scripts/usage_report.py
```

Add to your agent's `AGENTS.md` so every final reply ends with the lines:

> Run `python3 <skill-dir>/scripts/usage_report.py <records.jsonl>` before
> every final reply and append its two output lines verbatim (in a fenced code
> block if markdown). Skip only on "No usage data found".

## Pricing

DeepSeek official (CNY / 1M tokens), effective 2026-08-17 00:00 Beijing:
peak 09:00–12:00 & 14:00–18:00 Beijing = 2× off-peak; earlier sessions use
legacy flat rates.

| Model            | Period   | cached-in | miss-in | out  |
|------------------|----------|-----------|---------|------|
| deepseek-v4-flash| legacy   | 0.02      | 1.0     | 2.0  |
| deepseek-v4-flash| off-peak | 0.05      | 1.5     | 4.5  |
| deepseek-v4-flash| peak     | 0.10      | 3.0     | 9.0  |
| deepseek-v4-pro  | legacy   | 0.025     | 3.0     | 6.0  |
| deepseek-v4-pro  | off-peak | 0.15      | 4.5     | 13.5 |
| deepseek-v4-pro  | peak     | 0.30      | 9.0     | 27.0 |

This is an **estimate**, not the provider bill (expect ~1% token deviation per
turn from per-request pricing and cache-miss attribution). Update `PRICES_*` in
the script when rates change ([platform.deepseek.com](https://platform.deepseek.com)).

## License

MIT
