"""
PDF Report Generation Module for SIW Intent Brain.

Provides offline PDF report generation from LeadCard JSONL outputs.
Converts scored leads into a human-readable, A4 PDF report with
summary statistics, top opportunities, and an invalid lines appendix.

Public API:
  - read_candidates_jsonl(path_or_stdin, from_stdin=False) -> (records, invalid_lines)
      Read from file path, or from stdin with from_stdin=True.
      Handles UTF-8, UTF-8-sig, UTF-16 encodings automatically.
  - select_top(records, top_n) -> list[LeadCard]
      Sort and select top N records by tier and scores.
  - compute_stats(records, invalid_lines=None) -> dict
      Compute summary statistics from records.
  - render_report(records, stats, invalid_lines, out_path, ...) -> None
      Render PDF report to file. Uses CJK fonts if available on system.
"""

from __future__ import annotations

from .reader import read_candidates_jsonl
from .curator import select_top, compute_stats
from .render_pdf import render_report

__all__ = [
    "read_candidates_jsonl",
    "select_top",
    "compute_stats",
    "render_report",
]

