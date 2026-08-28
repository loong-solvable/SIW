# SIW Intent Brain 使用说明（小白可用）

> 当前产品已有 Web 工作台，普通用户优先使用网页。若必须使用命令行，新环境由管理员配置 `AI_API_KEY / AI_BASE_URL / AI_MODEL`；下文 `OPENROUTER_*` 示例仅为旧环境兼容说明。

这份说明尽量"少术语、可复制"。你只需要照着做。

---

## 你需要准备的东西

1) **Python 3.10+**
   - 这是运行工具的"启动器"。
   - 安装时勾选 "Add Python to PATH"。

2) **项目文件夹**
   - 你的项目在 `D:\code\SIW`（下面示例按这个路径写）。

3) **OpenRouter API Key**
   - 这是让工具"真正评分"的钥匙。
   - 去 OpenRouter 官网生成一个 Key，复制好备用。

---

## 第一次使用（只做一次）

### Windows PowerShell（复制粘贴即可）

```powershell
# 进入项目文件夹
cd d:\code\SIW

# 创建隔离环境（避免影响系统）
python -m venv venv

# 启动隔离环境
.\venv\Scripts\Activate.ps1

# 安装项目
pip install -e .
```

如果你要运行在线演示脚本（`scripts/demo_score.py`），再加这句：

```powershell
pip install rich
```

---

## 每次使用前（每次打开新窗口都要做）

这一步是告诉工具："用哪个 Key 去评分"。

```powershell
# 进入项目文件夹
cd d:\code\SIW

# 启动隔离环境
.\venv\Scripts\Activate.ps1

# 设置 API Key（把你的 Key 替换进去）
$env:OPENROUTER_API_KEY = "sk-or-v1-你的Key"
```

---

## 最常用的 4 个命令

### 1) 检查环境
"看看能不能正常跑"。

```powershell
siw-brain doctor
```

看到 `WARN: OPENROUTER_API_KEY` 就说明 Key 没设置。

---

### 2) 直接评分一句话
"我给一句话 → 输出一个结果"。

```powershell
siw-brain score --text "我在找一个更便宜的 ToolX 替代品" | Out-File -Encoding utf8 out.json
```

- 这条命令会生成 `out.json`（**单个 LeadCard**）。
- 你可以用下面命令检查它是否合格：

```powershell
siw-brain validate --json-file out.json
```

---

### 3) 从 Reddit 抓取并批量评分
"自动抓 10 条 → 每条评分 → 保存到文件"。

```powershell
siw-brain harvest --sub SaaS --query "expensive" --limit 10 |
  ForEach-Object { ($_ | ConvertFrom-Json).card | ConvertTo-Json -Compress -Depth 20 } |
  Out-File -Encoding utf8 candidates.jsonl
```

- 这会生成 `candidates.jsonl`。
- **每一行就是一个 LeadCard**（方便做批量处理）。

---

### 4) 生成 PDF 报告
"把 candidates.jsonl 变成漂亮的 PDF"。

```powershell
siw-brain report --in candidates.jsonl --out report.pdf --top 20
```

- 这会生成 `report.pdf`（A4 格式）。
- 报告包含：摘要统计、顶部商机卡片、无效行附录。
- `--top 20` 表示只包含前 20 个最佳商机。

想看详细进度？加 `--verbose`：

```powershell
siw-brain report --in candidates.jsonl --out report.pdf --top 20 --verbose
```

---

## 完整工作流示例（从抓取到报告）

下面是一个完整的例子，从抓取 Reddit 帖子到生成 PDF 报告：

```powershell
# 第 1 步：抓取并评分（保存到 jsonl 文件）
siw-brain harvest --sub SaaS --query "alternative" --limit 20 |
  ForEach-Object { ($_ | ConvertFrom-Json).card | ConvertTo-Json -Compress -Depth 20 } |
  Out-File -Encoding utf8 candidates.jsonl

# 第 2 步：生成 PDF 报告
siw-brain report --in candidates.jsonl --out report.pdf --top 10 --verbose

# 完成！打开 report.pdf 查看结果
```

---

## 怎么改参数（改哪里就换哪里）

### harvest 命令参数

| 参数 | 含义 | 例子 |
|------|------|------|
| `--sub` | 要抓哪个版块 | `--sub SaaS` / `--sub marketing` |
| `--query` | 必须包含的关键词 | `--query "expensive"` / `--query "pricing"` |
| `--limit` | 抓多少条 | `--limit 10` / `--limit 30` |
| `--sort` | 排序方式 | `--sort new` / `--sort hot` / `--sort top` |

### report 命令参数

| 参数 | 含义 | 例子 |
|------|------|------|
| `--in` | 输入文件 | `--in candidates.jsonl` |
| `--out` | 输出 PDF 文件 | `--out report.pdf` |
| `--top` | 包含前 N 个最佳商机 | `--top 20` / `--top 10` |
| `--verbose` | 显示详细进度 | `--verbose` |

---

## 文件输出是什么？能做什么？

### 1) `out.json`（单个结果）
- 适合：单条内容的评分
- 用途：保存、发送给别人、人工查看

### 2) `candidates.jsonl`（多条结果）
- 每行一个 LeadCard
- 适合：批量分析、筛选、后续导入数据工具

### 3) `report.pdf`（PDF 报告）
- 人类可读的 A4 报告
- 包含：统计摘要、层级分布、关键词、顶部商机卡片
- 适合：分享给团队、打印、汇报

---

## 如果重复运行会覆盖怎么办？

默认会覆盖旧文件。你有 2 种选择：

### 方式 A：追加到同一个文件
```powershell
siw-brain harvest --sub SaaS --query "expensive" --limit 10 |
  ForEach-Object { ($_ | ConvertFrom-Json).card | ConvertTo-Json -Compress -Depth 20 } |
  Out-File -Encoding utf8 -Append candidates.jsonl
```

### 方式 B：自动带时间戳
```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
siw-brain harvest --sub SaaS --query "expensive" --limit 10 |
  ForEach-Object { ($_ | ConvertFrom-Json).card | ConvertTo-Json -Compress -Depth 20 } |
  Out-File -Encoding utf8 "candidates-$ts.jsonl"
```

---

## 常见问题

### 1) 提示 API Key 缺失
- 重新执行"每次使用前"的 Key 设置步骤。

### 2) 没输出 / 输出很少
- 可能是关键词太少或版块没有符合的内容。
- 换个 `--query` 关键词试试。

### 3) 输出里 `ok=false`
- 看 `meta.error_code` 和 `meta.error_detail`，里面会说明原因。

### 4) 报错：UnicodeEncodeError / gbk 无法编码
这是 PowerShell 默认编码导致的。先切换到 UTF-8 再执行命令：

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
```

再重新运行你的命令即可。

### 5) PDF 报告中文显示为问号 (?)
- 这是因为系统没有安装 CJK 字体或字体无法加载。
- Windows 系统通常会自动使用宋体 (SimSun)。
- 用 `--verbose` 查看是否有字体警告。

### 6) demo_score.py 报 `ImportError: rich`
- 执行：
  ```powershell
  pip install rich
  ```

---

## 快速参考卡片

| 我想做什么 | 命令 |
|------------|------|
| 检查环境 | `siw-brain doctor` |
| 评分单条文字 | `siw-brain score --text "..." \| Out-File -Encoding utf8 out.json` |
| 从 Reddit 抓取评分 | `siw-brain harvest --sub SaaS --limit 10 \| ... \| Out-File ...` |
| 生成 PDF 报告 | `siw-brain report --in candidates.jsonl --out report.pdf` |
| 验证 JSON 文件 | `siw-brain validate --json-file out.json` |
| 离线演示 | `siw-brain demo` |

---

如果你告诉我"你想要什么效果"，我可以直接给你一条能用的命令。
