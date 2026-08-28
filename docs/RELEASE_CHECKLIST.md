# Release Checklist

> 2026-07-16 更新：发布环境以 `AI_API_KEY / AI_BASE_URL / AI_MODEL` 为主配置，`OPENROUTER_*` 仅用于兼容旧部署；密钥值不得出现在检查记录中。

Pre-release verification steps for SIW Intent Brain.

---

## Pre-Release Verification

### 1. Run All Tests

```bash
# Activate the project virtual environment
.\.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate      # Linux/macOS

# Run full test suite
pytest -q

# Expected: All tests pass
```

### 2. Check Environment (Doctor)

```bash
siw-brain doctor
```

**Expected output:**
- All checks `[OK  ]` except API key (which may be `[WARN]`)
- Exit code: 0

### 3. Run Offline Demo

```bash
siw-brain demo
```

**Expected output:**
- 3 LeadCard JSON objects
- All validation results: `VALID`
- Exit code: 0

### 4. Run Online Demo (Real API)

```bash
# Inject the selected OpenAI-compatible gateway at runtime
$env:AI_API_KEY = "runtime-secret"  # Windows
$env:AI_BASE_URL = "https://compatible-gateway.example/v1"
$env:AI_MODEL = "selected-model"
export AI_API_KEY="runtime-secret"  # Linux/macOS
export AI_BASE_URL="https://compatible-gateway.example/v1"
export AI_MODEL="selected-model"

# Run online demo
python scripts/demo_score.py
```

**Expected output:**
- 3 LeadCard JSON objects (real LLM responses)
- All validation results: `VALID`
- Various tiers (S/A/B/C/D) depending on sample
- Exit code: 0

### 5. Test Score Command

```bash
siw-brain score --text "Looking for a cheaper alternative to ToolX"
```

**Expected:**
- Valid LeadCard JSON output
- No errors in stderr (unless `--verbose`)

### 6. Test File Redirect (Windows)

```powershell
siw-brain score --text "Test" | Out-File -Encoding utf8 out.json
siw-brain validate --json-file out.json
```

**Expected:**
- `VALID`
- Exit code: 0

---

## Security Verification

### API Key Protection

- [ ] Run `siw-brain score --text "test" --verbose 2>&1 | Select-String "sk-or"`
  - Should return **no matches** (key not logged)

- [ ] Check logs don't contain full input text
  - Logs should truncate text to 100 chars max

### Verbose Mode

- [ ] Verify `--verbose` logs go to stderr only:
  ```bash
  siw-brain score --text "test" --verbose > out.json 2>log.txt
  ```
  - `out.json` should be valid JSON (no log lines)
  - `log.txt` should contain log entries

---

## Documentation Verification

- [ ] README.md renders correctly on GitHub
- [ ] All example commands work as documented
- [ ] CHANGELOG.md is up to date
- [ ] Version in `pyproject.toml` matches CHANGELOG

---

## Packaging boundary

The supported production artifact is `Dockerfile.web`. Standalone Windows and
public PyPI publishing are not release targets for this product; do not block a
web release on work that is outside this boundary.

---

## Final Checklist

Before tagging a release:

- [ ] All tests pass (`pytest -q`)
- [ ] Doctor command works (`siw-brain doctor`)
- [ ] Offline demo works (`siw-brain demo`)
- [ ] Online demo works (`python scripts/demo_score.py`)
- [ ] No API key leakage in logs
- [ ] README is accurate
- [ ] CHANGELOG updated
- [ ] Version bumped in `pyproject.toml`
- [ ] Git tag created: `git tag v0.1.0`

---

## Maintainer release command

Only run the commit, tag, and push steps after the repository owner approves the
release version and target branch.

```bash
# Final verification
pytest -q
siw-brain doctor
siw-brain demo

# Tag release
git add -A
git commit -m "Release v0.1.0"
git tag v0.1.0
git push origin main --tags
```
