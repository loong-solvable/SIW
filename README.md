# SIW Intent Brain

**Local-first, BYOK (Bring Your Own Key) decision support engine** that scores commercial intent from text and returns structured Lead Cards.

SIW Intent Brain analyzes text (e.g., Reddit posts, comments, forum threads) to identify high-value commercial signals—helping you prioritize leads without manual review.

---

## Table of Contents

- [What is SIW Intent Brain](#what-is-siw-intent-brain)
- [Install](#install)
- [Quickstart](#quickstart)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Contract (lead_card.v1)](#contract-lead_cardv1)
- [Troubleshooting](#troubleshooting)

---

## What is SIW Intent Brain

SIW Intent Brain is a **decision support tool** that:

- **Scores intent** from text using LLM analysis (via OpenRouter)
- **Extracts signals** like pain points, budget hints, tool mentions
- **Tiers leads** (S/A/B/C/D) based on commercial potential
- **Recommends next steps** (offer_resource, ask_question, draft_reply, monitor, ignore)
- **Fails gracefully** — always returns valid JSON, even on errors

### Key Features

| Feature | Description |
|---------|-------------|
| **Local-first** | Your API key, your data, your control |
| **BYOK** | Bring your own OpenRouter API key |
| **Fail-closed** | Errors return valid LeadCard with `ok: false` |
| **Offline demo** | Test without API key using `siw-brain demo` |
| **Windows compatible** | Handles PowerShell UTF-16 encoding automatically |

### What It Does NOT Do

- ❌ Automate posting or replies
- ❌ Access your accounts or sessions
- ❌ Bypass platform rules or detection
- ❌ Store data externally

---

## Install

### Prerequisites

- Python 3.10+
- OpenRouter API key (for real scoring; demo works offline)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/siw-intent-brain.git
cd siw-intent-brain

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate

# Install in development mode
pip install -e .
```

### Verify Installation

```bash
siw-brain --version
# Output: siw-brain 0.1.0
```

---

## Quickstart

Get up and running in 3 steps:

### Step 1: Check Your Environment

```bash
siw-brain doctor
```

Expected output:
```
SIW Intent Brain - Doctor
==================================================
[OK  ] Python version: Python 3.10.x
[OK  ] Package imports: All core modules
[OK  ] Schema file: .../schemas/lead_card.v1.json
[OK  ] CWD writable: ...
[WARN] OPENROUTER_API_KEY: Not set (required for score command)
==================================================
All checks passed!
```

### Step 2: Run Offline Demo

```bash
siw-brain demo
```

This runs 3 sample texts (high intent, low intent, noise) using a fake client—no API key needed. You'll see LeadCard JSON output for each sample.

### Step 3: Score Real Text

Set your OpenRouter API key:

```bash
# Windows PowerShell:
$env:OPENROUTER_API_KEY = "sk-or-v1-your-key-here"

# Linux/macOS:
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

Score some text:

```bash
siw-brain score --text "ToolX is $59/mo and I need a cheaper alternative"
```

Save output to file and validate:

```bash
# Windows PowerShell (recommended):
siw-brain score --text "Looking for alternatives" | Out-File -Encoding utf8 out.json

# Or using redirect (works with encoding auto-detection):
siw-brain score --text "Looking for alternatives" > out.json

# Validate the output:
siw-brain validate --json-file out.json
# Output: VALID
```

---

## CLI Reference

### `siw-brain score`

Score intent from text and output LeadCard JSON.

```bash
siw-brain score [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--text TEXT` | Text to analyze (direct string) |
| `--text-file PATH` | Read text from file |
| `--context-json JSON` | Context as JSON string (e.g., `'{"subreddit": "marketing"}'`) |
| `--context-file PATH` | Read context from JSON file |
| `--config PATH` | Path to config YAML file |
| `--min-confidence FLOAT` | Override minimum confidence threshold (0.0-1.0) |
| `--quiet` | Output compact JSON (no indentation) |
| `--verbose` | Enable logging to stderr |

**Examples:**

```bash
# Basic usage
siw-brain score --text "Need a cheaper CRM tool"

# With context
siw-brain score --text "Anyone tried ToolX?" --context-json '{"subreddit": "SaaS"}'

# From file
siw-brain score --text-file post.txt --context-file context.json

# Compact output
siw-brain score --text "Help needed" --quiet

# Pipe from stdin (Linux/macOS)
echo "Looking for alternatives" | siw-brain score
```

### `siw-brain validate`

Validate a LeadCard JSON file against the schema.

```bash
siw-brain validate --json-file PATH
```

| Exit Code | Meaning |
|-----------|---------|
| 0 | VALID |
| 1 | File error (not found, invalid JSON) |
| 2 | INVALID (schema validation failed) |

### `siw-brain doctor`

Check system environment and dependencies.

```bash
siw-brain doctor
```

Checks:
- Python version (>= 3.10)
- Package imports
- Schema file exists
- CWD writable
- `OPENROUTER_API_KEY` set (warning if missing)

### `siw-brain demo`

Run offline demo with sample texts (no API key required).

```bash
siw-brain demo
```

Outputs 3 LeadCards (high intent, low intent, noise) using a fake client. Useful for:
- Testing installation
- Understanding output format
- Demonstrating without API costs

### `siw-brain harvest`

Harvest and score Reddit posts (optional module).

```bash
siw-brain harvest --sub SaaS --query "alternative" --limit 10
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--sub` | Yes | — | Subreddit name (without r/) |
| `--query` | No | — | Search query |
| `--limit` | No | 10 | Maximum posts to fetch |
| `--sort` | No | new | Sort order (new, hot, top) |
| `--config` | No | — | Path to config YAML |
| `--verbose` | No | — | Enable verbose output |

Output: JSONL to stdout (one JSON object per line)

```json
{"card": {...}, "source_meta": {"created_utc": 1703500000, "score": 42}}
```

Notes:
- Requires `OPENROUTER_API_KEY` for scoring
- Some posts may be skipped if empty; actual count may be less than `--limit`
- Respects Reddit rate limits (1-2s per request)

### `siw-brain report`

Generate PDF report from LeadCard JSONL.

```bash
siw-brain report --in candidates.jsonl --out report.pdf --top 20
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--in` | No | stdin | Input JSONL file path (or `-` for stdin) |
| `--out` | Yes | — | Output PDF file path |
| `--top` | No | 20 | Number of top cards to include |
| `--verbose` | No | — | Enable verbose output |

**Input formats supported:**
- Pure LeadCard JSONL (one LeadCard JSON per line)
- Harvest output format (`{"card": {...}, "source_meta": {...}}`)

**Output:**
- A4 PDF report with:
  - Summary statistics (counts, tier distribution, mean scores)
  - Top keywords and budget hints
  - Top opportunity cards (sorted by tier/confidence)
  - Invalid lines appendix

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success |
| 1 | Input/file/encoding/dependency error |
| 2 | PDF render error |

**Examples:**

```bash
# Generate report from file
siw-brain report --in candidates.jsonl --out report.pdf

# Harvest + report pipeline
siw-brain harvest --sub SaaS --limit 20 > results.jsonl
siw-brain report --in results.jsonl --out saas_report.pdf --top 10

# Verbose mode shows progress
siw-brain report --in candidates.jsonl --out report.pdf --verbose
```

Notes:
- Non-verbose mode is silent (stderr only on errors)
- Uses system CJK fonts if available (Windows: SimSun, macOS: PingFang)
- Non-ASCII without CJK font support shows `?` replacement

---

## Configuration

Configuration is loaded with this priority:

1. **Environment variables** (highest priority)
2. **YAML config file** (if `--config` specified or `config.yaml` exists)
3. **Default values** (lowest priority)

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes* | — | Your OpenRouter API key |
| `SIW_MODEL` | No | `anthropic/claude-sonnet-4` | Model to use |
| `SIW_BASE_URL` | No | `https://openrouter.ai/api/v1` | API endpoint |
| `SIW_TIMEOUT_S` | No | `30` | Request timeout (seconds) |
| `SIW_MAX_RETRIES` | No | `3` | Max retry attempts |
| `SIW_MIN_CONFIDENCE` | No | `0.35` | Minimum confidence threshold |

*Required for `score` command; not needed for `demo` or `doctor`.

### Using .env File

Create a `.env` file in your project root:

```bash
# .env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
SIW_MODEL=anthropic/claude-sonnet-4
SIW_TIMEOUT_S=30
```

### Using YAML Config

Create a `config.yaml` file:

```yaml
# config.yaml
model: anthropic/claude-sonnet-4
timeout_s: 30
max_retries: 3
min_confidence: 0.35
```

Use with `--config`:

```bash
siw-brain score --text "..." --config config.yaml
```

### Example Files

See `config.example.yaml` and `.env.example` for templates.

---

## Contract (lead_card.v1)

### LeadCard Schema

Every output conforms to the `lead_card.v1` schema:

```json
{
  "ok": true,
  "scores": {
    "urgency": 0.7,
    "pain_point_intensity": 0.8,
    "commercial_relevance": 0.6,
    "solution_seeking": 0.9
  },
  "confidence": 0.85,
  "lead_tier": "A",
  "recommended_next_step": "offer_resource",
  "rationale": "Strong buying signals detected.",
  "extracted_signals": {
    "problem_summary": "User frustrated with high costs",
    "constraints": ["budget", "time"],
    "budget_hints": ["$50/mo max"],
    "tooling_stack": ["ToolX", "ToolY"],
    "keywords": ["alternative", "cheaper"]
  },
  "safety_notes": ["Approach professionally."],
  "meta": {
    "model": "anthropic/claude-sonnet-4",
    "provider": "openrouter",
    "latency_ms": 1250,
    "retries": 0,
    "parser_mode": "strict",
    "schema_version": "lead_card.v1"
  }
}
```

### Lead Tiers

| Tier | Score Range | Description |
|------|-------------|-------------|
| S | ≥ 0.78 | Hot lead - immediate action |
| A | ≥ 0.62 | High intent - prioritize |
| B | ≥ 0.46 | Moderate intent - worth following |
| C | ≥ 0.30 | Low intent - monitor |
| D | < 0.30 | No commercial signal |

### Next Steps

| Step | When Used |
|------|-----------|
| `offer_resource` | High commercial relevance + solution seeking |
| `ask_question` | High pain point + solution seeking |
| `draft_reply` | Moderate composite score |
| `monitor` | Low confidence or low signal |
| `ignore` | Very low composite score |

### Error Codes

| Code | Description |
|------|-------------|
| `E_CONFIG_MISSING_KEY` | Missing required configuration (e.g., API key) |
| `E_UPSTREAM_HTTP` | HTTP error from LLM provider |
| `E_UPSTREAM_TIMEOUT` | Request timeout |
| `E_UPSTREAM_EMPTY_CONTENT` | Empty response from LLM |
| `E_PARSE_JSON` | Failed to parse LLM response as JSON |
| `E_CONTRACT_INVALID` | Output failed schema validation |
| `E_FILE_READ` | File read error |

When `ok: false`, check `meta.error_code` and `meta.error_detail` for details.

---

## Troubleshooting

### Missing API Key

**Symptom:**
```
ERROR: Configuration error (check OPENROUTER_API_KEY)
```

**Solution:**
```bash
# Set environment variable
$env:OPENROUTER_API_KEY = "sk-or-v1-your-key-here"  # PowerShell
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"  # Bash
```

### Upstream Timeout / 429 Rate Limit

**Symptom:**
```json
{
  "ok": false,
  "meta": {
    "error_code": "E_UPSTREAM_TIMEOUT"
  }
}
```

**Solution:**
- Increase timeout: `SIW_TIMEOUT_S=60`
- Reduce request frequency
- Check OpenRouter quota/limits

### JSON Parse Error

**Symptom:**
```json
{
  "ok": false,
  "meta": {
    "error_code": "E_PARSE_JSON",
    "parser_mode": "fail_closed"
  }
}
```

**Solution:**
- This is handled automatically (fail-closed returns valid LeadCard)
- Check if model is responding correctly
- Try a different model

### File Encoding Issues (Windows)

**Symptom:**
```
ERROR: Cannot read file 'out.json': Unable to decode file...
```

**Solution:**

SIW Intent Brain automatically handles UTF-16, UTF-8-BOM, and UTF-8 encodings. However, for best results:

```powershell
# Recommended: Use Out-File with explicit encoding
siw-brain score --text "..." | Out-File -Encoding utf8 out.json

# Alternative: Standard redirect (auto-detected)
siw-brain score --text "..." > out.json

# Validate works with any encoding
siw-brain validate --json-file out.json
```

### Verbose Mode for Debugging

Enable verbose logging:

```bash
siw-brain score --text "..." --verbose 2>debug.log
```

Logs go to stderr; stdout remains pure JSON.

---

## License

MIT License - See LICENSE file for details.

---

## Support

For issues and feature requests, please open a GitHub issue.
