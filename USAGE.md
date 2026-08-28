# SIW Intent Brain 使用说明

> 配置说明更新：新环境以 `AI_API_KEY / AI_BASE_URL / AI_MODEL` 为准；本文出现的 `OPENROUTER_*` 仅代表兼容旧环境。Web 工作台、任务历史与健康检查请优先参阅根目录 `README.md`。

本文件基于当前代码实现整理，覆盖 CLI 和 Python API 的使用方式。

## 1. 项目简介

SIW Intent Brain 是一个本地优先的意图评分引擎。输入文本后输出严格的 LeadCard JSON，用于商业意图判断和后续流程决策。系统具备以下特点：

- 输出符合 `schemas/lead_card.v1.json` 的固定结构。
- 全流程 fail-closed: 出错时返回 `ok=false` 的 LeadCard，不抛异常。
- CLI 和 Python API 都可使用。
- stdout 只输出 JSON，日志和提示输出到 stderr。

## 2. 环境与安装

### 2.1 运行要求
- Python 3.10+

### 2.2 安装

```bash
python -m venv venv
# Windows PowerShell
.\venv\Scripts\Activate.ps1
# Linux/macOS
source venv/bin/activate

pip install -e .
```

### 2.3 可选依赖

`scripts/demo_score.py` 使用 `rich` 输出 JSON，需要单独安装：

```bash
pip install rich
```

## 3. 配置

### 3.1 环境变量

代码实际读取的环境变量如下：

必需：
- `OPENROUTER_API_KEY`

OpenRouter 相关：
- `OPENROUTER_MODEL` (默认 `openai/gpt-4o-mini`)
- `OPENROUTER_BASE_URL` (默认 `https://openrouter.ai/api/v1/chat/completions`)
- `OPENROUTER_TIMEOUT_S` (默认 30)
- `OPENROUTER_MAX_RETRIES` (默认 3)
- `OPENROUTER_BACKOFF_S` (默认 1.2)
- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_X_TITLE`

Brain 行为相关：
- `BRAIN_MIN_CONFIDENCE` (默认 0.35)
- `BRAIN_MAX_RATIONALE_CHARS` (默认 400)
- `BRAIN_MAX_LIST_ITEMS` (默认 50)
- `BRAIN_RESPONSE_FORMAT_JSON` (默认 true)

注意：代码不读取 `SIW_*` 环境变量。

### 3.2 .env 文件

在项目根目录放置 `.env` 即可自动加载：

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=openai/gpt-4o-mini
```

### 3.3 YAML 配置文件

CLI 参数 `--config` 会加载 YAML，结构为分组形式：

```yaml
openrouter:
  api_key: sk-or-v1-...
  model: openai/gpt-4o-mini
  base_url: https://openrouter.ai/api/v1/chat/completions
  timeout_s: 30
  max_retries: 3
  backoff_s: 1.2
  http_referer: https://your-app.com
  x_title: Your App

brain:
  min_confidence: 0.35
  max_rationale_chars: 400
  max_list_items: 50
  response_format_json: true
```

优先级：环境变量 > YAML > 默认值。

## 4. CLI 使用说明

CLI 入口：`siw-brain`。

### 4.1 score

输出 LeadCard JSON。

```bash
siw-brain score --text "Need a cheaper CRM tool"
siw-brain score --text-file input.txt --context-file ctx.json
```

输入方式：
- `--text` 直接传入
- `--text-file` 从文件读取 (支持 utf-8-sig, utf-8, utf-16)
- stdin: 无 `--text` 且 stdin 非 TTY 时读取

上下文方式：
- `--context-json` JSON 字符串
- `--context-file` JSON 文件

常用参数：
- `--min-confidence` 覆盖本次运行阈值
- `--quiet` 输出紧凑 JSON
- `--verbose` 启用日志 (stderr)

### 4.2 validate

验证 JSON 是否符合 LeadCard 结构。

```bash
siw-brain validate --json-file out.json
```

返回码：
- 0: VALID
- 1: 文件或 JSON 解析错误
- 2: 结构不符合 LeadCard

### 4.3 doctor

环境检查：Python 版本、核心模块、schema、CWD 可写性、API Key 状态。

```bash
siw-brain doctor
```

缺少 `OPENROUTER_API_KEY` 仅为 WARN，不影响返回码 (仍返回 0)。

### 4.4 demo (离线)

使用 FakeClient 输出 3 个示例 LeadCard，不需要 API Key。

```bash
siw-brain demo
```

stdout: 仅 JSON
stderr: 运行信息和验证结果

### 4.5 harvest

从 Reddit 公共 `.json` 接口抓取并评分。

```bash
siw-brain harvest --sub SaaS --query "alternative" --limit 5
```

参数：
- `--sub` 子版块名 (不含 r/)
- `--query` 搜索关键词 (可选)
- `--limit` 最大抓取数量
- `--sort` `new` / `hot` / `top`
- `--config` YAML 配置路径
- `--verbose` 启用日志

输出：
- stdout: JSONL (每行一个对象，含 `card` + `source_meta`)
- stderr: 进度和警告

注意：
- 仍需要 `OPENROUTER_API_KEY` 来评分。
- 抓取失败时返回空结果 (fail-closed) 并输出 WARN。

### 4.6 report

从 LeadCard JSONL 生成 PDF 报告。

```bash
siw-brain report --in candidates.jsonl --out report.pdf --top 20
```

参数：
- `--in` JSONL 输入文件路径；`-` 或省略表示 stdin
- `--out` (必需) 输出 PDF 文件路径
- `--top` 包含的顶部卡片数量 (默认: 20)
- `--verbose` 启用日志

输入格式：
- 纯 LeadCard JSONL (每行一个 LeadCard JSON)
- harvest 输出格式 (每行包含 `{"card": {...}, "source_meta": {...}}`)
- 两种格式都支持

输出：
- A4 PDF 报告，包含：
  - 摘要统计 (总数、层级分布、平均分数等)
  - 顶部商机卡片
  - 无效行附录

返回码：
- 0: 成功
- 1: 输入/文件/编码/JSON/验证/依赖错误
- 2: 渲染错误 (PDF 生成失败)

示例：

```powershell
# 直接从文件生成报告（推荐）
siw-brain report --in candidates.jsonl --out report.pdf

# 与 harvest 配合使用（推荐）
siw-brain harvest --sub SaaS --limit 10 > results.jsonl
siw-brain report --in results.jsonl --out saas_report.pdf --top 10
```

PowerShell 管道输入注意事项：

PowerShell 默认使用 UTF-16 编码进行管道传输，report 命令已内置编码自动检测。
但为确保最佳兼容性，推荐使用文件输入方式：

```powershell
# 推荐：先保存到文件，再生成报告
siw-brain harvest --sub SaaS --limit 10 | Out-File -Encoding utf8 results.jsonl
siw-brain report --in results.jsonl --out report.pdf

# 如需使用管道，命令会自动检测 UTF-16 编码
Get-Content candidates.jsonl | siw-brain report --in - --out report.pdf
```

## 5. Python API 使用

### 5.1 基本用法

```python
from siw_intent_brain import IntentBrain, validate_lead_card

brain = IntentBrain.from_env()
card = brain.score(
    text="Looking for a cheaper alternative to ToolX",
    context={"subreddit": "SaaS", "title": "Cheaper ToolX alternative?"}
)

errors = validate_lead_card(card)
print(errors)  # [] 表示有效
```

context 只保留 4 个字段：`subreddit` / `title` / `author` / `permalink`。

### 5.2 自定义配置

```python
from siw_intent_brain import BrainConfig, IntentBrain

cfg = BrainConfig(
    api_key="sk-or-v1-...",
    model="openai/gpt-4o-mini",
    min_confidence=0.35,
)
brain = IntentBrain(cfg)
```

### 5.3 Harvester API

```python
from siw_intent_brain.harvester import RedditHarvester

harvester = RedditHarvester()
result = harvester.fetch_posts("SaaS", query="alternative", limit=5)

print(result.items)
print(result.skipped_count)
print(result.error_message)
```

`result.items` 内每项包含：
- `text`
- `context`
- `_meta` (下游使用，不传给 LLM)

## 6. 输出结构 (LeadCard)

LeadCard schema 见 `schemas/lead_card.v1.json`。核心字段：
- `ok`: bool
- `scores`: 4 个评分 (0..1)
- `confidence`: 0..1
- `lead_tier`: S/A/B/C/D
- `recommended_next_step`: ignore/monitor/draft_reply/ask_question/offer_resource
- `rationale`: <= 400 字符
- `extracted_signals`: 摘要与列表字段
- `safety_notes`
- `meta`: model/provider/latency_ms/retries/parser_mode/schema_version

失败时 (ok=false) 会在 `meta.error_code` / `meta.error_detail` 中给出原因。

## 7. 日志与指标

- `--verbose` 会打开结构化日志 (stderr)。
- stdout 始终保持纯 JSON 以便管道处理。

## 8. 在线 demo 脚本

`scripts/demo_score.py` 使用真实 OpenRouter API：

```bash
python scripts/demo_score.py
```

需要：
- `OPENROUTER_API_KEY`
- `rich` (用于格式化输出)

## 9. 测试

```bash
pytest -q
```

测试默认离线，使用 FakeClient/FakeHarvester，不需要网络。

## 10. 常见问题

- 缺少 API Key:
  - 设置 `OPENROUTER_API_KEY`

- Windows 输出文件编码问题:
  - PowerShell 推荐:
    ```powershell
    siw-brain score --text "..." | Out-File -Encoding utf8 out.json
    ```

- demo_score.py 报 `ImportError: rich`:
  - `pip install rich`
