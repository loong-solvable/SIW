# SIW Intent Brain

SIW 是一个商机意图分析产品：把帖子、评论或客户原话转成结构化 Lead Card，并支持批量评分、PDF/JSONL 报告和任务历史。

当前仓库同时包含两种入口：

- Web 工作台：适合在线评分、批量任务、查看历史和下载报告；
- `siw-brain` CLI：适合离线批处理、验证、诊断和运维。

SIW 不会自动发帖、登录第三方账号或规避平台规则。

## 产品闭环

### 单条评分

用户输入文本与可选上下文，系统调用 OpenAI-compatible 模型，校验 `lead_card.v1` 结构，然后把任务状态和结果写入 SQLite。结果包含意图分层、置信度、信号、建议动作和安全说明。

### 批量报告

用户可输入 Reddit 板块/关键词，也可直接粘贴手动线索。系统逐条评分，生成 JSONL 与 PDF，并将产物绑定到当前浏览器会话的任务记录。

报告下载使用所有者校验；所有产物只能从 `/api/jobs/<任务号>/artifacts/<格式>` 获取，旧的无会话报告地址不再暴露。

## 安装与测试

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=src pytest -q
```

最低 Python 版本为 3.10。

## AI 配置

模型调用使用 OpenAI-compatible HTTP 契约。新环境使用以下变量，并由部署过程注入 cc-switch 当前选中的兼容网关配置：

| 变量 | 必需 | 默认 | 说明 |
|---|---:|---|---|
| `AI_API_KEY` | 是 | — | 运行时注入，不写入仓库 |
| `AI_BASE_URL` | 否 | OpenRouter 兼容地址 | 可填写 `/v1` 根地址或完整 `/chat/completions` 地址 |
| `AI_MODEL` | 否 | `openai/gpt-4o-mini` | cc-switch 当前网关可用的模型名 |
| `AI_PROVIDER` | 否 | `openai_compatible` | 记录到结果元数据的供应别名，可设为 `cc_switch` |
| `AI_TIMEOUT_S` | 否 | `30` | 单次请求超时秒数 |
| `AI_MAX_RETRIES` | 否 | `3` | 最大重试次数 |
| `AI_BACKOFF_S` | 否 | `1.2` | 重试退避基数 |
| `AI_HTTP_REFERER` | 否 | — | 可选请求来源元数据 |
| `AI_APP_NAME` | 否 | — | 可选应用名称元数据 |

`OPENROUTER_*` 变量仍作为旧环境兼容输入，但新代码和新部署不应优先使用它们。密钥不会出现在 Lead Card、任务记录或用户错误信息中。

也可使用 `config.example.yaml`。优先级为：环境变量 > YAML > 默认值。

## 启动 Web 工作台

```bash
export AI_API_KEY="由运行环境注入"
export AI_BASE_URL="https://兼容网关.example/v1"
export AI_MODEL="当前模型名"
export SIW_DATA_DIR="./data"

python -m siw_intent_brain.webapp --host 127.0.0.1 --port 8080
```

打开 `http://127.0.0.1:8080/`。

运行数据位于：

- `${SIW_DATA_DIR}/siw.sqlite3`：任务、状态、结果索引与所有者；
- `${SIW_DATA_DIR}/reports/`：PDF 和 JSONL 产物。

Web 使用 HttpOnly、SameSite=Lax 的持久会话 cookie 做浏览器级所有权隔离。生产 HTTPS 默认启用 Secure；本地纯 HTTP 调试可设置 `SIW_SESSION_COOKIE_SECURE=false`。这不是独立账号系统，后续统一账号接入应由 Bigpoplar 的身份层完成，不能在 SIW 再造一套密码库。

应用启动时会把上一次进程留下的排队中或运行中任务收口为 `E_PROCESS_RESTARTED`，历史页会保留可读原因，用户可以安全地重新提交。

### 健康检查

- `GET /health/live`：进程存活，不依赖数据库或模型；
- `GET /health/ready`：检查 SQLite 任务库与模型配置；
- `GET /api/health`：旧探针兼容入口。

## Docker

```bash
docker build -f Dockerfile.web -t siw-intent-brain:web .
docker run --rm -p 8080:8080 \
  -e AI_API_KEY \
  -e AI_BASE_URL \
  -e AI_MODEL \
  -v siw-data:/data \
  siw-intent-brain:web
```

生产环境应把密钥作为环境变量或密钥挂载注入，不写进镜像、Compose 文件或日志。

候选容器切换前可执行一次最小真实模型探针：

```bash
python -m siw_intent_brain.smoke
```

探针只输出成功状态、模型/供应方标识、token 与供应方上报成本；不会输出提示词、模型正文、密钥或上游错误详情。

## CLI

### 诊断与离线演示

```bash
siw-brain doctor
siw-brain demo
```

`doctor` 只显示密钥是否存在，不显示密钥值；`demo` 使用离线假客户端，不消耗模型额度。

### 单条评分

```bash
siw-brain score --text "ToolX 太贵了，需要一个更便宜的监控工具"
siw-brain score --text-file post.txt --context-json '{"subreddit":"SaaS"}'
```

### 抓取与报告

```bash
siw-brain harvest --sub SaaS --query "alternative" --limit 10 > candidates.jsonl
siw-brain report --in candidates.jsonl --out report.pdf --top 10
```

### 合同验证

```bash
siw-brain validate --json-file lead-card.json
```

退出码：`0` 表示成功，`1` 表示输入或文件错误，`2` 表示合同校验失败。

## Lead Card 合同

输出遵循 `schemas/lead_card.v1.json`，核心字段包括：

- `ok`
- `scores`
- `confidence`
- `lead_tier`（S/A/B/C/D）
- `recommended_next_step`
- `rationale`
- `extracted_signals`
- `safety_notes`
- `meta`（模型、供应别名、耗时、重试、解析方式、错误码）

成功结果的 `meta` 同时保留服务方返回的输入、输出、总 token 与美元百万分之一费用；上游未返回费用时为 `null`，系统不自行估价。

解析或上游失败时，系统使用 fail-closed 结果，不伪造成功。

## 工程边界

- `src/siw_intent_brain/brain.py`：评分编排；
- `src/siw_intent_brain/llm/`：兼容模型客户端；
- `src/siw_intent_brain/job_store.py`：SQLite 任务仓库；
- `src/siw_intent_brain/webapp.py`：Web 工作台与受控下载；
- `src/siw_intent_brain/report.py`：PDF 报告；
- `schemas/lead_card.v1.json`：结果合同；
- `tests/`：内核、CLI、Web、任务存储和真实 HTTP 边界测试。

任何新业务链都必须保留：输入、任务状态、结果、用户可读错误、历史和产物授权。部署与线上模型 smoke 在代码门禁全部通过后单独执行。
