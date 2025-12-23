# Changelog

All notable changes to SIW Intent Brain will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2024-12-23

### Added

#### Core Features
- **IntentBrain** - Main scoring API with fail-closed behavior
- **LeadCard Contract** - Structured JSON output with `lead_card.v1` schema
- **Score Dimensions** - Urgency, pain point intensity, commercial relevance, solution seeking
- **Lead Tiering** - S/A/B/C/D tiers based on composite score
- **Next Step Recommendations** - offer_resource, ask_question, draft_reply, monitor, ignore

#### Parsing & Normalization
- **JSON Extractor** - Tolerant JSON parsing with strict/extracted modes
- **Normalizer** - Score clamping, list cleanup, string truncation
- **Heuristics Fallback** - Rule-based tiering and next_step when LLM output is invalid

#### LLM Integration
- **OpenRouter Client** - HTTP client with retry, backoff, timeout handling
- **Prompt Builder** - Stable, deterministic prompt construction
- **Response Parsing** - Robust extraction from potentially malformed LLM output

#### CLI Commands
- `siw-brain score` - Score text and output LeadCard JSON
- `siw-brain validate` - Validate LeadCard JSON against schema
- `siw-brain doctor` - Check environment and dependencies
- `siw-brain demo` - Run offline demo with sample texts

#### Configuration
- Environment variable support (`OPENROUTER_API_KEY`, `SIW_MODEL`, etc.)
- YAML config file support
- `.env` file support via python-dotenv
- Priority: env > yaml > defaults

#### Error Handling
- Fail-closed design - always returns valid LeadCard
- Structured error codes (`E_UPSTREAM_HTTP`, `E_PARSE_JSON`, etc.)
- Soft fail-closed for low confidence scores

#### Observability
- Structured JSON logging (disabled by default, `--verbose` to enable)
- In-memory metrics (request counts, latency tracking)
- Logs output to stderr, keeping stdout clean

#### Windows Compatibility
- Multi-encoding file reading (UTF-8, UTF-8-sig, UTF-16)
- Handles PowerShell ">" redirect encoding automatically
- Tested on Windows PowerShell

#### Testing
- 390+ unit tests (all offline, no network required)
- FakeClient injection for isolated testing
- Contract validation tests
- Heuristics boundary tests

#### Documentation
- Comprehensive README with quickstart guide
- CLI reference with examples
- Configuration guide
- Troubleshooting section

### Security

- API key never logged or printed
- Input text truncated in logs
- No sensitive data in error messages
- Verbose logs only to stderr

---

## [Unreleased]

### Planned
- PyPI package publishing
- Additional model support
- Batch scoring API
- Custom prompt templates

