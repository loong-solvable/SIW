# SIW Intent Brain 使用说明（小白可用）

这份说明尽量“少术语、可复制”。你只需要照着做。

---

## 你需要准备的东西

1) **Python 3.10+**
   - 这是运行工具的“启动器”。
   - 安装时勾选 “Add Python to PATH”。

2) **项目文件夹**
   - 你的项目在 `D:\code\SIW`（下面示例按这个路径写）。

3) **OpenRouter API Key**
   - 这是让工具“真正评分”的钥匙。
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

这一步是告诉工具：“用哪个 Key 去评分”。

```powershell
# 进入项目文件夹
cd d:\code\SIW

# 启动隔离环境
.\venv\Scripts\Activate.ps1

# 设置 API Key（把你的 Key 替换进去）
$env:OPENROUTER_API_KEY = "sk-or-v1-你的Key"
```

---

## 最常用的 3 个命令（记住它们）

### 1) 检查环境
“看看能不能正常跑”。

```powershell
siw-brain doctor
```

看到 `WARN: OPENROUTER_API_KEY` 就说明 Key 没设置。

---

### 2) 直接评分一句话（生成单个文件）
“我给一句话 → 输出一个结果”。

```powershell
siw-brain score --text "我在找一个更便宜的 ToolX 替代品" | Out-File -Encoding utf8 out.json
```

- 这条命令会生成 `out.json`（**单个 LeadCard**）。
- 你可以用下面命令检查它是否合格：

```powershell
siw-brain validate --json-file out.json
```

---

### 3) 从 Reddit 抓取并批量评分（生成 candidates.jsonl）
“自动抓 10 条 → 每条评分 → 保存到文件”。

```powershell
siw-brain harvest --sub SaaS --query "expensive" --limit 10 |
  ForEach-Object { ($_ | ConvertFrom-Json).card | ConvertTo-Json -Compress -Depth 20 } |
  Out-File -Encoding utf8 candidates.jsonl
```

- 这会生成 `candidates.jsonl`。
- **每一行就是一个 LeadCard**（方便做批量处理）。

---

## 怎么改参数（改哪里就换哪里）

下面是常见参数的含义：

- `--sub`：要抓哪个版块（例如 SaaS）
- `--query`：必须包含的关键词（例如 expensive）
- `--limit`：抓多少条（例如 10）
- `--sort`：排序方式（new / hot / top）

例子：

- 改版块：
  ```powershell
  --sub SaaS  ->  --sub marketing
  ```

- 改关键词：
  ```powershell
  --query "expensive"  ->  --query "pricing"
  ```

- 改数量：
  ```powershell
  --limit 10  ->  --limit 30
  ```

- 改排序：
  ```powershell
  --sort new  ->  --sort hot
  ```

---

## 文件输出是什么？能做什么？

### 1) `out.json`（单个结果）
- 适合：单条内容的评分
- 用途：保存、发送给别人、人工查看

### 2) `candidates.jsonl`（多条结果）
- 每行一个 LeadCard
- 适合：批量分析、筛选、后续导入数据工具

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
- 重新执行“每次使用前”的 Key 设置步骤。

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

再重新运行你的 `harvest` 命令即可。

### 5) demo_score.py 报 `ImportError: rich`
- 执行：
  ```powershell
  pip install rich
  ```

---

如果你告诉我“你想要什么效果”，我可以直接给你一条能用的命令。
