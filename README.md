# token-usage-report

An Agent Skill that reports per-conversation **token usage, cache hit rate, and
estimated cost** from local agent rollout files — so you can cross-check what your
agent reports you spent against the provider's real bill.

```
本段会话：输入 123456 / 缓存命中 98765 / 输出 4321 / 命中率 80.0% / 费用 ¥0.12
```

- Zero dependencies — Python 3.9+ standard library only.
- Works offline, reads local files only, never touches API keys.
- Supports **ZCode** (segment-level) and **Codex** (session-level); auto-detects
  the agent, or force with `--agent`.
- Cost estimate uses **DeepSeek official peak/off-peak pricing** (v4-flash/v4-pro,
  legacy rates before 2026-08-17).

## Install

As an Agent Skill (recommended):

```bash
npx skills add <owner>/token-usage-report   # after the repo is public
```

Or manually — copy the folder into one of the agent's skill directories, e.g.
`~/.agents/skills/token-usage-report/` (cross-tool) or
`~/.zcode/skills/token-usage-report/` (ZCode only).

## Usage

```bash
python3 scripts/usage_report.py --latest   # most recent segment (ZCode) / session (Codex)
python3 scripts/usage_report.py --whole    # whole latest session
python3 scripts/usage_report.py --all      # per-session summary
python3 scripts/usage_report.py --agent zcode|codex
```

Add to your agent's `AGENTS.md` so every final reply ends with the line:

> Run `python3 <skill-dir>/scripts/usage_report.py --latest` before every final
> reply and append the line as
> `本段会话：输入 X / 缓存命中 Y / 输出 Z / 命中率 N% / 费用 ¥M`.
> Skip only when the script prints "No usage data found".

## Supported agents

| Agent   | Data source                                     | `--latest` means                                    |
|---------|-------------------------------------------------|-----------------------------------------------------|
| ZCode   | `~/.zcode/cli/rollout/model-io-*.jsonl`         | last **segment** (since the latest user message, incl. its tool calls) |
| Codex   | `~/.codex/sessions/**/rollout-*.jsonl`          | last **session** (whole file)                       |
| Claude  | `~/.claude/projects/**/*.jsonl`                 | last **segment** (since the latest `"type":"user"` record) |
| OpenCode| `<data>/opencode/opencode.db` (SQLite; `%LOCALAPPDATA%` on Windows, `$XDG_DATA_HOME` or `~/.local/share` otherwise) | last **segment** of the most recent session |

ZCode / Codex are verified against real local data; Claude Code and OpenCode use
their documented formats (Claude Code: `message.usage` per assistant record;
OpenCode: `message.data.tokens` in the SQLite db, read with stdlib `sqlite3`).

## Adding another agent

Each agent needs a data-dir entry + a record parser in `scripts/usage_report.py`:

1. Add the rollout location to `AGENTS` (compute it cross-platform, see
   `_opencode_dir` for the pattern).
2. Write `usage_of(agent, rec)` returning
   `{"input", "cached", "output", "model", "started_at"}` for usage-bearing
   records, and `has_user_message(agent, rec)` returning `True` for records that
   mark a user prompt (enables segment-level reporting).
3. Re-test with `--agent <name> --latest` / `--all`.

**DeepSeek Harness (dsh)** recipe: sessions are append-only JSONL under
`$DSH_HOME/sessions` (default `~/.dsh/sessions`; Python SDK uses
`DSH_SESSION_ROOT`); token accounting appears in `usage_update` events and
`PromptResponse.usage`. Grab one real session file to pin the exact record
shape, then implement `usage_of("dsh", rec)` the same way as the others —
[python-sdk.md](https://github.com/deepseek-ai/DeepSeek-Harness/blob/master/docs/user/guide/python-sdk.md)
and
[@openma/deepseek-harness-acp](https://www.npmjs.com/package/@openma/deepseek-harness-acp)
document the storage.

## Pricing

DeepSeek official peak/off-peak pricing, effective 2026-08-17 00:00 Beijing
(peak: 09:00–12:00 & 14:00–18:00 Beijing = 2× off-peak):

| Model            | Period   | cached-in | miss-in | out  | CNY / 1M tokens |
|------------------|----------|-----------|---------|------|-----------------|
| deepseek-v4-flash| off-peak | 0.05      | 1.5     | 4.5  |                 |
| deepseek-v4-flash| peak     | 0.10      | 3.0     | 9.0  |                 |
| deepseek-v4-pro  | off-peak | 0.15      | 4.5     | 13.5 |                 |
| deepseek-v4-pro  | peak     | 0.30      | 9.0     | 27.0 |                 |

Rates are a snapshot; update `PRICES_*` in the script when they change
(authoritative source: [platform.deepseek.com](https://platform.deepseek.com)).

## License

MIT
