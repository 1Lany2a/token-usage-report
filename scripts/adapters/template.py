#!/usr/bin/env python3
"""Adapter template — write YOUR agent's adapter by filling this in.

Contract: read YOUR agent's session logs and print one JSON object per line:

    {"input": 123456, "cached": 98765, "output": 4321,
     "started_at": "2026-08-14T10:00:00+08:00", "model": "deepseek-v4-flash",
     "turn_start": true}

- input      = total input tokens of one request (cache-hit + miss)
- cached     = cache-hit input tokens
- output     = output tokens (include reasoning tokens if billed as output)
- started_at = ISO timestamp or null
- model      = model id or null
- turn_start = True on the FIRST request of a new user turn

Then feed the output to the core:

    python3 <skill-dir>/scripts/usage_report.py <records.jsonl>

Watch out: if your agent stores CUMULATIVE session totals per record (Codex
total_token_usage, DSH usage samples), never sum them — emit only the LAST
sample per session.
"""

import json
import sys
from pathlib import Path

LOGS = Path.home() / "<your-agent>" / "<logs-dir>"  # TODO: point at your logs


def main() -> int:
    for path in sorted(LOGS.rglob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)  # TODO: parse YOUR record
                # TODO: extract from rec ->
                print(json.dumps({
                    "input": 0,          # int
                    "cached": 0,         # int
                    "output": 0,         # int (incl. reasoning if billed as output)
                    "started_at": None,  # ISO str or null
                    "model": None,       # str or null
                    "turn_start": False, # True on the first request of a user turn
                }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
