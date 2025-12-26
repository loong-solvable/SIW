# SIW Intent Brain - Offline PDF Report Implementation Plan

Goal: Add a robust, offline PDF report generator (`siw-brain report`) that converts
LeadCard JSONL outputs into a human-readable, A4 PDF report. The design must fit
the current project conventions (fail-closed, encoding-safe I/O, stderr logging,
no sensitive outputs), and must be reliable in Windows PowerShell pipelines.

This plan is written in ASCII per repository editing constraints.

---

## 1) Input Format Decision (Compatibility + Canonical)

Decision:
- Canonical input format: JSONL where each line is a LeadCard object.
- Accepted compatibility format: JSONL where each line is an object containing
  "card" (LeadCard) and "source_meta" (harvest output).
- Input source: file path via --in, or stdin if --in "-" or omitted with piped input.

Rationale:
- The documentation encourages writing pure LeadCard JSONL (see USAGE_NON_TECH.md).
- The `harvest` CLI outputs a wrapper object with "card".
- Accepting both avoids user friction and aligns with "last mile" intent.
- Canonical format keeps the report tool independent of harvest details.

Normalization rule:
1) If parsed line is a dict with a "card" dict field, use the "card" value.
2) Else if parsed line is a dict, treat it as a LeadCard.
3) Else treat as invalid line.

---

## 2) Modules and Responsibilities

New package path:
- src/siw_intent_brain/report/

Files:
1) reader.py
2) curator.py
3) render_pdf.py
4) __init__.py

Primary public API:
- read_candidates_jsonl(path) -> (records, invalid_lines)
- select_top(records, top_n) -> list[LeadCard]
- compute_stats(records) -> dict
- render_report(records, stats, invalid_lines, out_path) -> None

---

## 3) reader.py (Encoding-safe JSONL reader)

Function: read_candidates_jsonl(path_or_text, from_stdin=False) -> tuple[list[dict], list[dict]]

Behavior:
- If from_stdin: read sys.stdin.read() (respect current stdin encoding).
- Else use read_text_file() from src/siw_intent_brain/io_utils.py to support:
  utf-8-sig, utf-8, utf-16 (Windows PowerShell default).
- Split into lines with .splitlines() to normalize line endings.
- Skip empty/whitespace-only lines.
- For each non-empty line:
  - Try json.loads(line)
  - On JSON error: append to invalid_lines and continue
  - Normalize to LeadCard (see rules in Section 1)
  - Always validate with validate_lead_card() to flag structural issues

Invalid line record schema:
- line_number: int (1-based)
- reason: str (short, stable, no raw tracebacks)
- raw: str (truncated, e.g. 240 chars)

Validation policy:
- If validate_lead_card() returns errors:
  - Append invalid line with "schema invalid" + error summary
  - Do NOT crash; continue reading
  - Do NOT include the record in valid records

Why validation here:
- Ensures PDF rendering does not need to guard every missing key.
- Follows fail-closed principles and keeps PDF layout predictable.

Security:
- Never print API keys or secrets.
- Never log raw full lines to stderr by default; store truncated for appendices.

---

## 4) curator.py (Sorting, selection, stats)

Tier ranking:
- tier_rank = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}

Sort key:
- (tier_rank, -confidence, -commercial_relevance,
   -solution_seeking, -pain_point_intensity, -urgency)

Score source:
- scores = record["scores"] (LeadCard)
- keys: commercial_relevance, solution_seeking, pain_point_intensity, urgency
- Missing values default to 0.0 for stability.

Functions:
1) select_top(records, top_n)
   - Filter records by ok == True (recommended)
   - Sort using key above (stable sort)
   - Return top_n (if top_n <= 0 return [])

2) compute_stats(records)
   - Use only ok == True by default; record a "excluded_ok_false" count
   - Outputs:
     - counts by lead_tier
     - counts by recommended_next_step
     - mean confidence
     - mean of 4 score dimensions
     - top keywords (Counter, top 10)
     - top budget_hints (Counter, top 10)
   - Deterministic order: sort by (count desc, token asc)
   - If no valid records, means default to 0.0 (avoid divide-by-zero)

Stats schema (example):
{
  "total": int,
  "valid": int,
  "invalid": int,
  "excluded_ok_false": int,
  "tier_counts": {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0},
  "next_step_counts": {...},
  "means": {
     "confidence": 0.0,
     "urgency": 0.0,
     "pain_point_intensity": 0.0,
     "commercial_relevance": 0.0,
     "solution_seeking": 0.0
  },
  "top_keywords": [("keyword", count), ...],
  "top_budget_hints": [("hint", count), ...]
}

---

## 5) render_pdf.py (ReportLab PDF layout)

Dependency:
- reportlab (added to pyproject.toml dependencies)

Page:
- A4 portrait, standard margins (e.g., 36-40 pt)
- Use reportlab.platypus (SimpleDocTemplate, Paragraph, Table, Spacer)

Layout Sections:
1) Cover / Summary
   - Report title + generation timestamp (local time)
   - Input file name (if provided by CLI)
   - Counts: total/valid/invalid
   - Tier and next_step distributions (simple tables)
   - Mean scores table
   - Top keywords + top budget hints lists

2) Top Opportunities (cards)
   - One card per LeadCard from select_top()
   - Each card includes:
     - Header row: Tier, Confidence, NextStep
     - Score table: urgency, pain_point_intensity,
       commercial_relevance, solution_seeking
     - problem_summary
     - rationale
     - keywords (list)
     - budget_hints (list)
     - tooling_stack (list)
   - Cards separated with Spacer or light horizontal rule

3) Appendix: Invalid Lines
   - List each invalid line entry with line_number and reason
   - Include raw excerpt (truncated)

Truncation rules (prevent layout overflow):
- problem_summary: max 180 chars
- rationale: max 320 chars (aligns with 400 max in schema)
- list fields: max 8 items per list
- each list item: max 80 chars
- if more items exist, append "... (+N more)"

Typography:
- Use reportlab default fonts for ASCII-only compatibility.
- If non-ASCII content is detected and a CJK font file is available in
  src/siw_intent_brain/report/assets/, register and use it.
- If non-ASCII content is detected and no CJK font is available:
  - Replace non-ASCII with "?" in rendered text
  - Emit a single WARN to stderr (no raw text)

Robustness:
- Any exception during PDF build returns error code 2 (render error).
- Fail-safe: if reportlab import fails, return error code 1 (input/dep error).

---

## 6) CLI Integration (src/siw_intent_brain/cli.py)

New subcommand:
  siw-brain report --in candidates.jsonl --out report.pdf --top 20
  siw-brain report --in - --out report.pdf --top 20
  siw-brain report --out report.pdf --top 20   (stdin)

Arguments:
- --in (optional) : input JSONL path; "-" or omitted means stdin
- --out (required): output PDF path
- --top (optional): number of top cards to render (default: 20)
- Optional: --verbose to enable logging (stderr)

Exit codes:
- 0: success
- 1: input/file/encoding/JSON/validation/dependency errors
- 2: render errors (PDF build failures)

Error handling:
- Use try/except to keep stderr messages concise and user-friendly.
- No raw tracebacks in normal operation.
- Never print or leak API keys.

---

## 7) Tests (tests/test_report.py)

Test cases:
1) Basic PDF generation
   - Create a small JSONL with 2-3 valid LeadCards
   - Call report pipeline (reader + curator + render_pdf)
   - Assert output file exists and size > 0

2) UTF-16 input
   - Write JSONL as utf-16 (PowerShell default)
   - Ensure reader returns records
   - PDF builds successfully

3) Invalid line tolerance
   - JSONL with one invalid JSON line
   - Ensure invalid_lines contains entry
   - PDF still builds successfully
4) Stdin support
   - Pipe JSONL via stdin and ensure reader accepts --in "-" or omitted

Optional tests:
- Harvest wrapper line handling ({"card": {...}})
- ok=false records excluded from top list but counted in stats

Testing policy:
- Offline-only (no network)
- No dependency on real API keys

---

## 8) Packaging and Dependencies

Update pyproject.toml:
- Add "reportlab>=4.x" to [project].dependencies

If keeping optional dependency:
- Use extras and skip tests if reportlab missing
- But for direct integration and "no missing deps", install by default

---

## 9) Documentation Updates

USAGE.md:
- Add "report" command in CLI section
- Explain accepted JSONL formats (LeadCard and harvest wrapper)
- Provide example:
  siw-brain report --in candidates.jsonl --out report.pdf --top 20

USAGE_NON_TECH.md:
- Add "generate PDF report" quick steps
- Mention that invalid lines are listed in appendix

README.md:
- Add short mention of report feature and example usage

---

## 10) Implementation Steps (Detailed)

Step 1: Create package scaffolding
- Add src/siw_intent_brain/report/__init__.py
- Export primary functions for internal import

Step 2: Implement reader.py
- Implement read_candidates_jsonl() using read_text_file()
- Implement JSONL parsing with per-line error collection
- Normalize "card" wrapper
- Add optional validate_lead_card() checks

Step 3: Implement curator.py
- Implement tier_rank and sort_key
- Implement select_top()
- Implement compute_stats() using Counter
- Ensure deterministic ordering

Step 4: Implement render_pdf.py
- Add reportlab imports and A4 layout
- Define reusable styles (title, section headers, body)
- Implement safe truncation helper functions
- Build summary tables
- Render cards with consistent spacing
- Render invalid line appendix

Step 5: Wire CLI
- Add report subcommand to argparse
- Add _cmd_report(args) with correct exit codes
- Minimal, user-friendly errors to stderr
 - Support stdin if --in "-" or omitted with piped input

Step 6: Tests
- Add tests/test_report.py (offline)
- Use tmp_path for output file
- Use ASCII fixtures for compliance
- Include utf-16 test using Path.write_text(encoding="utf-16")
 - Add stdin test

Step 7: Docs and examples
- Update USAGE.md and USAGE_NON_TECH.md with report usage
- Add short README mention

Step 8: QA checklist
- Manual run: siw-brain report --in candidates.jsonl --out report.pdf
- Validate that PDF renders on Windows and is readable
- Test invalid JSON line handling
- Confirm stderr only on errors

---

## 11) Risk Mitigations

- Encoding issues: use read_text_file() to handle utf-8-sig/utf-8/utf-16.
- Schema drift: validate LeadCards before rendering.
- Large inputs: only top N cards rendered; stats computed with O(n).
- Layout overflow: truncation and list limits.
- Determinism: stable sort and deterministic Counter ordering.

---

## 12) Definition of Done

- "report" command added and documented.
- Accepts both LeadCard JSONL and harvest wrapper JSONL.
- Accepts stdin for pipeline usage (--in "-" or omitted with pipe).
- PDF generated for valid inputs with size > 0.
- Invalid lines do not break rendering and are listed in appendix.
- Tests pass offline.
- stdout is quiet (no JSON); stderr only for errors/warnings.
- No sensitive output to stderr.
