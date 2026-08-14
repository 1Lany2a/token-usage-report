# token-usage-report

一个 Agent Skill，用于估算**本段会话的 token 用量、缓存命中率与人民币费用**：

```
本段会话：输入 123456 / 缓存命中 98765 / 输出 4321 / 命中率 80.0% / 费用 ¥0.12
整个会话：输入 987654 / 缓存命中 876543 / 输出 43210 / 命中率 88.8% / 费用 ¥0.50
```

- **核心与 agent 无关**：由安装它的 agent 写一个很小的适配器，把自己的会话日志转换成统一的 JSONL 记录格式。
- Python 3.9+，纯标准库（zstd 压缩日志需可选依赖 `zstandard`）。
- 费用按 **DeepSeek 官方价格**估算（v4-flash/v4-pro；2026-08-17 起峰谷价，此前 legacy 价）。

## 安装——必须装在非系统盘

请安装到**非系统盘**，不要放进系统盘的默认 skill 目录：

```bash
mkdir -p /d/agents/skills          # Windows: D:\agents\skills
cp -r token-usage-report /d/agents/skills/
```

然后向你的 agent 注册该路径（或直接用绝对路径引用）。

## 一次性配置：安装者自行编写适配器

安装本 skill 的 agent 需要填写 `scripts/adapters/<你的-agent>.py`（从
`scripts/adapters/template.py` 复制起步）：读取**你自己**的会话日志，按每请求
一行打印一个 JSON 对象——

```json
{"input": 123456, "cached": 98765, "output": 4321,
 "started_at": "2026-08-14T10:00:00+08:00", "model": "deepseek-v4-flash",
 "turn_start": true}
```

- `input` = 该请求总输入 tokens（缓存命中 + 未命中），`cached` = 缓存命中输入，
  `output` = 输出 tokens（若按输出价计费，请把推理 tokens 一并计入）
- `started_at` = ISO 时间戳或 null，`model` = 模型名或 null
- `turn_start` = 该请求是否是新用户回合的第一条（分段边界）

常见坑：若你的 agent 记录的是**累计值**（如 Codex 的 `total_token_usage`），
每个会话只输出**最后一条**，绝不能对累计值求和；压缩日志（如 DSH zstd）需先解压。

## 用法

```bash
python3 scripts/usage_report.py <records.jsonl>   # 两行：本段 + 整个
python3 scripts/usage_report.py --whole <records.jsonl>
cat records.jsonl | python3 scripts/usage_report.py
```

在 agent 的 `AGENTS.md` 中加入规则，让每次最终回复都以这两行结尾：

> 每次最终回复前运行 `python3 <skill-dir>/scripts/usage_report.py <records.jsonl>`，
> 并把输出的两行原样附在回复末尾（markdown 回复请放入代码块以保证分行）。
> 仅当脚本输出 "No usage data found" 时跳过。

## 计价

DeepSeek 官方价格（元 / 百万 tokens），2026-08-17 00:00 北京时间起生效：
高峰时段 09:00–12:00、14:00–18:00（北京时间）= 空闲时段 2 倍；更早的会话按
legacy 平段价。

| 模型            | 时段   | 缓存命中 | 未命中 | 输出 |
|------------------|--------|----------|--------|------|
| deepseek-v4-flash| legacy | 0.02     | 1.0    | 2.0  |
| deepseek-v4-flash| 空闲   | 0.05     | 1.5    | 4.5  |
| deepseek-v4-flash| 高峰   | 0.10     | 3.0    | 9.0  |
| deepseek-v4-pro  | legacy | 0.025    | 3.0    | 6.0  |
| deepseek-v4-pro  | 空闲   | 0.15     | 4.5    | 13.5 |
| deepseek-v4-pro  | 高峰   | 0.30     | 9.0    | 27.0 |

这是**估算值，不是账单**（每回合 token 偏差约 1%，来自逐请求计价与缓存未命中
归属差异）。官方调价后请同步更新脚本中的 `PRICES_*` 表
（权威来源：[platform.deepseek.com](https://platform.deepseek.com)）。

## 许可

MIT
