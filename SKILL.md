---
name: token-usage-report
description: "Report per-conversation token usage, cache hit rate, and estimated CNY cost from local agent rollout files (ZCode, Codex). Use whenever the user asks about token usage, token cost, spending, billing, 用量, 费用, 花费, how many tokens were used, session cost, or wants a usage summary — even if they don't say 'usage report'. Run before composing the final reply so the summary line is appended automatically."
---

# Token Usage Report

Reads the agent's local rollout files and prints the usage of the most recent
conversation segment **plus** the whole session (two lines):

    本段会话：输入 123456 / 缓存命中 98765 / 输出 4321 / 命中率 80.0% / 费用 ¥0.12
    整个会话：输入 987654 / 缓存命中 876543 / 输出 43210 / 命中率 88.8% / 费用 ¥0.50

Why both lines? The whole-session numbers are computed locally by the script
(no extra model calls), so reporting them costs only a few dozen extra
characters in the reply — negligible token overhead, and the user can compare
the current turn against the session total.

## When to run

- Run **before composing the final reply** of every session.
- Trigger phrasings: "token usage", "用量", "费用", "cost", "billing",
  "多少 tokens", "汇报", "spent".
- Why: it gives the user a per-turn usage line they can cross-check against the
  provider's real bill. The cost is an *estimate* (pricing snapshot), not the bill.

## How to run

Script: `scripts/usage_report.py` — Python 3.9+, standard library only, no install.

```bash
python3 <this-skill-dir>/scripts/usage_report.py --latest   # most recent segment/session (default)
python3 <this-skill-dir>/scripts/usage_report.py --whole    # whole latest session
python3 <this-skill-dir>/scripts/usage_report.py --all      # per-session list
python3 <this-skill-dir>/scripts/usage_report.py --agent zcode|codex|claude|opencode
```

Always use the **absolute path** to this skill's directory. Do not `cd` elsewhere
first. The script auto-detects the agent (the one with the newest rollout file);
`--agent` overrides that.

Append the script's output to the final reply **verbatim** — both lines, on
separate lines (本段会话 above, 整个会话 below). If the reply is markdown, a
single newline renders as a space and merges the two lines, so put them inside a
fenced code block (or leave a blank line between them):

    ```text
    本段会话：输入 123456 / 缓存命中 98765 / 输出 4321 / 命中率 80.0% / 费用 ¥0.12
    整个会话：输入 987654 / 缓存命中 876543 / 输出 43210 / 命中率 88.8% / 费用 ¥0.50
    ```

- Exit code 0 → **always** include both lines, even if the numbers look
  identical to the previous report (the user wants them every turn).
- Exit code 1 / "No usage data found" → skip silently; do not ask the user.
- Any other error → fix the cause (missing Python, moved skill dir) before
  responding; do not silently skip.

## Supported agents

| Agent   | Data source                                     | `--latest` means                                   |
|---------|-------------------------------------------------|----------------------------------------------------|
| ZCode   | `~/.zcode/cli/rollout/model-io-*.jsonl`         | last **segment**: records since the latest request containing a user message (that turn incl. its tool calls) |
| Codex   | `~/.codex/sessions/**/rollout-*.jsonl`          | last **session** (whole file)                      |
| Claude  | `~/.claude/projects/**/*.jsonl`                 | last **segment**: records since the latest `"type":"user"` record |
| OpenCode| `<data>/opencode/opencode.db` (SQLite; `%LOCALAPPDATA%` on Windows, `$XDG_DATA_HOME` or `~/.local/share` otherwise) | last **segment** of the most recent session (from the latest user message) |

All four are parsed from documented, locally-verified or well-known formats.
DeepSeek Harness (dsh) and other agents can be added with a small parser —
see README.md for the recipe.

## Cost model

DeepSeek official peak/off-peak pricing, effective **2026-08-17 00:00 Beijing
time** (announced 2026-08-13). Peak hours: 09:00–12:00 and 14:00–18:00 Beijing;
all other times are off-peak at **half price**. Sessions before 2026-08-17 use
the flat legacy rates.

| Model            | Period   | cached-in | miss-in | out  | (CNY / 1M tokens) |
|------------------|----------|-----------|---------|------|--------------------|
| deepseek-v4-flash| off-peak | 0.05      | 1.5     | 4.5  |                    |
| deepseek-v4-flash| peak     | 0.10      | 3.0     | 9.0  |                    |
| deepseek-v4-pro  | off-peak | 0.15      | 4.5     | 13.5 |                    |
| deepseek-v4-pro  | peak     | 0.30      | 9.0     | 27.0 |                    |

The billing period comes from the session start time (machine-local time). If the
official rates change, update the `PRICES_*` tables in `scripts/usage_report.py`;
the authoritative source is platform.deepseek.com.

## Integration (report every session automatically)

Add this rule to the agent's user-level instruction file (`~/.zcode/AGENTS.md`,
`~/.codex/AGENTS.md`, `CLAUDE.md`, or a project `AGENTS.md`):

> Run `python3 <skill-dir>/scripts/usage_report.py --latest` before every final
> reply and append its two output lines verbatim:
> `本段会话：输入 X / 缓存命中 Y / 输出 Z / 命中率 N% / 费用 ¥M`
> `整个会话：输入 X / 缓存命中 Y / 输出 Z / 命中率 N% / 费用 ¥M`.
> Skip only when the script prints "No usage data found".

## Security

- The script reads **only** local rollout JSON files under the user's home
  directory. It never reads, prints, or requires API keys, `.env` files, or
  credentials.
- Rollout files may contain prompt text — never echo their contents. Print only
  the aggregated numbers the script outputs.
