"""
ReportLab PDF layout renderer for SIW Intent Brain reports.

Generates A4 PDF reports with:
  - Cover/Summary section with counts and statistics
  - Top Opportunities cards section
  - Appendix with invalid lines

Dependencies:
  - reportlab (required)

Typography:
  - Uses reportlab default fonts for ASCII
  - Non-ASCII characters replaced with "?" if no CJK font available
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Truncation limits
_MAX_PROBLEM_SUMMARY = 180
_MAX_RATIONALE = 320
_MAX_LIST_ITEMS = 8
_MAX_ITEM_CHARS = 80


def _truncate_str(s: str, max_len: int) -> str:
    """Truncate string to max_len, appending '...' if truncated."""
    if not isinstance(s, str):
        return ""
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


def _truncate_list(items: List[str], max_items: int, max_chars: int) -> List[str]:
    """Truncate list to max items, each item to max chars."""
    if not isinstance(items, list):
        return []
    
    result = []
    for item in items[:max_items]:
        if isinstance(item, str):
            result.append(_truncate_str(item, max_chars))
    
    remaining = len(items) - max_items
    if remaining > 0:
        result.append(f"... (+{remaining} more)")
    
    return result


def _sanitize_text(text: str) -> str:
    """
    Sanitize text for PDF rendering.
    
    - Removes control characters (C0/C1) that break ReportLab Paragraph
    - Escapes XML special chars for Paragraph markup
    - Non-ASCII printable chars are kept (CJK handling done elsewhere)
    """
    if not isinstance(text, str):
        return ""
    
    # Remove control characters (ASCII 0-31 except tab/newline, and 127-159)
    # These can cause ReportLab Paragraph to crash
    cleaned = []
    for ch in text:
        code = ord(ch)
        # Keep: tab (9), newline (10), carriage return (13), and printable chars (32+)
        # Remove: 0-8, 11-12, 14-31, 127-159
        if code == 9 or code == 10 or code == 13:
            cleaned.append(ch)
        elif code >= 32 and code != 127:
            # Skip C1 control characters (128-159) in Latin-1
            if code < 128 or code >= 160:
                cleaned.append(ch)
            # else: skip C1 control char
        # else: skip C0 control char
    
    text = "".join(cleaned)
    
    # Escape XML special characters for Paragraph
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    
    return text


# Cache for CJK font registration
_cjk_font_registered: bool | None = None
_cjk_font_name: str | None = None


def _check_cjk_available() -> bool:
    """
    Check if CJK fonts are available and register if found.
    
    Tries to find and register a CJK font from common system locations:
      - Windows: SimSun, Microsoft YaHei, SimHei
      - macOS: Hiragino Sans GB, PingFang SC
      - Linux: Noto Sans CJK, WenQuanYi
    
    Returns True if a CJK font was successfully registered.
    """
    global _cjk_font_registered, _cjk_font_name
    
    # Return cached result if available
    if _cjk_font_registered is not None:
        return _cjk_font_registered
    
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        _cjk_font_registered = False
        return False
    
    # Common CJK font paths by platform
    import os
    import platform
    
    font_candidates = []
    system = platform.system()
    
    if system == "Windows":
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        font_candidates = [
            (os.path.join(fonts_dir, "simsun.ttc"), "SimSun"),
            (os.path.join(fonts_dir, "msyh.ttc"), "Microsoft YaHei"),
            (os.path.join(fonts_dir, "simhei.ttf"), "SimHei"),
            (os.path.join(fonts_dir, "malgun.ttf"), "Malgun Gothic"),
        ]
    elif system == "Darwin":  # macOS
        font_candidates = [
            ("/System/Library/Fonts/Hiragino Sans GB.ttc", "Hiragino Sans GB"),
            ("/System/Library/Fonts/PingFang.ttc", "PingFang SC"),
            ("/Library/Fonts/Arial Unicode.ttf", "Arial Unicode"),
        ]
    else:  # Linux and others
        font_candidates = [
            ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "Noto Sans CJK"),
            ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "WenQuanYi Zen Hei"),
            ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", "Droid Sans Fallback"),
        ]
    
    # Try to register each font
    for font_path, font_name in font_candidates:
        if os.path.exists(font_path):
            try:
                # For TTC files, use subfont index 0
                if font_path.endswith('.ttc'):
                    pdfmetrics.registerFont(TTFont(font_name, font_path, subfontIndex=0))
                else:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                _cjk_font_registered = True
                _cjk_font_name = font_name
                return True
            except Exception:
                # Font registration failed, try next
                continue
    
    _cjk_font_registered = False
    return False


def _get_cjk_font_name() -> str | None:
    """Get the registered CJK font name, or None if not available."""
    if _check_cjk_available():
        return _cjk_font_name
    return None


def _has_non_ascii(text: str) -> bool:
    """Check if text contains non-ASCII characters."""
    try:
        text.encode('ascii')
        return False
    except UnicodeEncodeError:
        return True


def _replace_non_ascii(text: str) -> str:
    """Replace non-ASCII characters with '?'."""
    return text.encode('ascii', errors='replace').decode('ascii')


def render_report(
    records: List[Dict[str, Any]],
    stats: Dict[str, Any],
    invalid_lines: List[Dict[str, Any]],
    out_path: str,
    *,
    input_filename: str = "",
    verbose: bool = False,
) -> None:
    """
    Render PDF report to file.
    
    Args:
        records: List of LeadCard dicts (already sorted/selected by caller).
        stats: Statistics dict from compute_stats().
        invalid_lines: List of invalid line records.
        out_path: Output PDF file path.
        input_filename: Optional input filename for report header.
        verbose: If True, emit warnings to stderr (e.g., CJK font missing).
    
    Raises:
        ImportError: If reportlab is not installed.
        Exception: If PDF rendering fails.
    
    Notes:
        - A4 portrait with standard margins
        - Uses reportlab.platypus for layout
        - Uses system CJK fonts if available (Windows: SimSun, macOS: PingFang, etc.)
        - Non-ASCII without CJK font: characters replaced with '?' silently
          (warning only shown if verbose=True)
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as e:
        raise ImportError(
            f"reportlab is required for PDF generation: {e}. "
            "Install with: pip install reportlab"
        ) from e
    
    # Check for CJK support and get font name
    cjk_available = _check_cjk_available()
    cjk_font = _get_cjk_font_name()
    non_ascii_warned = False
    
    def safe_text(text: str) -> str:
        """Make text safe for PDF rendering."""
        nonlocal non_ascii_warned
        
        if _has_non_ascii(text):
            if not cjk_available:
                if not non_ascii_warned and verbose:
                    print(
                        "WARN: Non-ASCII characters detected but no CJK font available. "
                        "Some characters may be replaced with '?'.",
                        file=sys.stderr
                    )
                    non_ascii_warned = True
                text = _replace_non_ascii(text)
        
        return _sanitize_text(text)
    
    # Create document
    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    
    # Styles - use CJK font if available for proper rendering
    styles = getSampleStyleSheet()
    font_name = cjk_font if cjk_font else 'Helvetica'
    font_name_bold = cjk_font if cjk_font else 'Helvetica-Bold'
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=font_name_bold,
        fontSize=18,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=font_name_bold,
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
    )
    subheading_style = ParagraphStyle(
        'CustomSubheading',
        parent=styles['Heading3'],
        fontName=font_name_bold,
        fontSize=11,
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontName=font_name,
    )
    small_style = ParagraphStyle(
        'Small',
        fontName=font_name,
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
    )
    
    # Label style - use Helvetica-Bold for ASCII labels to avoid CJK bold issues
    # This ensures labels like "Problem:", "Rationale:" always render correctly
    label_style = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
    )
    
    # Combined label+content helper that avoids <b> tags with CJK content
    def labeled_paragraph(label: str, content: str, style: ParagraphStyle) -> Paragraph:
        """Create paragraph with ASCII label and potentially CJK content.
        
        Uses Helvetica-Bold for label via <font> tag to avoid CJK bold issues.
        """
        # Use <font> tag to force Helvetica-Bold for ASCII label only
        return Paragraph(
            f'<font face="Helvetica-Bold">{label}:</font> {content}',
            style
        )
    
    # Helper to create table styles with correct fonts
    def make_table_style(
        header_font_size: int = 9,
        body_font_size: int = 9,
        right_align_col: int | None = 1,
        center_align: bool = False,
    ) -> TableStyle:
        """Create TableStyle with CJK font support."""
        cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), font_name_bold),  # Header row
            ('FONTNAME', (0, 1), (-1, -1), font_name),       # Body rows
            ('FONTSIZE', (0, 0), (-1, 0), header_font_size),
            ('FONTSIZE', (0, 1), (-1, -1), body_font_size),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]
        if right_align_col is not None:
            cmds.append(('ALIGN', (right_align_col, 0), (right_align_col, -1), 'RIGHT'))
        if center_align:
            cmds.append(('ALIGN', (0, 1), (-1, -1), 'CENTER'))
        return TableStyle(cmds)
    
    # Build story (content)
    story: List[Any] = []
    
    # =================================================================
    # COVER / SUMMARY
    # =================================================================
    story.append(Paragraph("SIW Intent Brain Report", title_style))
    
    # Generation timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph(f"Generated: {now}", small_style))
    
    if input_filename:
        story.append(Paragraph(f"Input: {safe_text(input_filename)}", small_style))
    
    story.append(Spacer(1, 12))
    
    # Counts summary
    story.append(Paragraph("Summary", heading_style))
    
    counts_data = [
        ["Metric", "Value"],
        ["Total Lines", str(stats.get("total", 0))],
        ["Valid Records", str(stats.get("valid", 0))],
        ["Invalid Lines", str(stats.get("invalid", 0))],
        ["Excluded (ok=false)", str(stats.get("excluded_ok_false", 0))],
    ]
    counts_table = Table(counts_data, colWidths=[150, 100])
    counts_table.setStyle(make_table_style(right_align_col=1))
    story.append(counts_table)
    story.append(Spacer(1, 12))
    
    # Tier distribution
    story.append(Paragraph("Tier Distribution", subheading_style))
    tier_counts = stats.get("tier_counts", {})
    tier_data = [["Tier", "Count"]]
    for tier in ["S", "A", "B", "C", "D"]:
        tier_data.append([tier, str(tier_counts.get(tier, 0))])
    tier_table = Table(tier_data, colWidths=[50, 80])
    tier_table.setStyle(make_table_style(right_align_col=1))
    story.append(tier_table)
    story.append(Spacer(1, 12))
    
    # Next step distribution
    story.append(Paragraph("Next Step Distribution", subheading_style))
    next_step_counts = stats.get("next_step_counts", {})
    next_step_data = [["Next Step", "Count"]]
    for step in ["ignore", "monitor", "draft_reply", "ask_question", "offer_resource"]:
        count = next_step_counts.get(step, 0)
        if count > 0:
            next_step_data.append([step, str(count)])
    if len(next_step_data) > 1:
        ns_table = Table(next_step_data, colWidths=[120, 80])
        ns_table.setStyle(make_table_style(right_align_col=1))
        story.append(ns_table)
    else:
        story.append(Paragraph("No data", body_style))
    story.append(Spacer(1, 12))
    
    # Mean scores
    story.append(Paragraph("Mean Scores", subheading_style))
    means = stats.get("means", {})
    means_data = [
        ["Metric", "Mean"],
        ["Confidence", f"{means.get('confidence', 0.0):.4f}"],
        ["Urgency", f"{means.get('urgency', 0.0):.4f}"],
        ["Pain Point Intensity", f"{means.get('pain_point_intensity', 0.0):.4f}"],
        ["Commercial Relevance", f"{means.get('commercial_relevance', 0.0):.4f}"],
        ["Solution Seeking", f"{means.get('solution_seeking', 0.0):.4f}"],
    ]
    means_table = Table(means_data, colWidths=[150, 80])
    means_table.setStyle(make_table_style(right_align_col=1))
    story.append(means_table)
    story.append(Spacer(1, 12))
    
    # Top keywords
    top_keywords = stats.get("top_keywords", [])
    if top_keywords:
        story.append(Paragraph("Top Keywords", subheading_style))
        kw_data = [["Keyword", "Count"]]
        for kw, count in top_keywords:
            kw_data.append([safe_text(_truncate_str(kw, 60)), str(count)])
        kw_table = Table(kw_data, colWidths=[200, 60])
        kw_table.setStyle(make_table_style(right_align_col=1))
        story.append(kw_table)
        story.append(Spacer(1, 12))
    
    # Top budget hints
    top_budget_hints = stats.get("top_budget_hints", [])
    if top_budget_hints:
        story.append(Paragraph("Top Budget Hints", subheading_style))
        bh_data = [["Budget Hint", "Count"]]
        for hint, count in top_budget_hints:
            bh_data.append([safe_text(_truncate_str(hint, 60)), str(count)])
        bh_table = Table(bh_data, colWidths=[200, 60])
        bh_table.setStyle(make_table_style(right_align_col=1))
        story.append(bh_table)
        story.append(Spacer(1, 12))
    
    # =================================================================
    # TOP OPPORTUNITIES
    # =================================================================
    if records:
        story.append(Paragraph(f"Top {len(records)} Opportunities", heading_style))
        
        for i, card in enumerate(records, start=1):
            # Card header
            tier = card.get("lead_tier", "D")
            confidence = card.get("confidence", 0.0)
            next_step = card.get("recommended_next_step", "monitor")
            
            header_text = f"#{i} | Tier: {tier} | Confidence: {confidence:.2f} | Next Step: {next_step}"
            story.append(Paragraph(header_text, subheading_style))
            
            # Scores table
            scores = card.get("scores", {})
            scores_data = [
                ["Urgency", "Pain Point", "Commercial", "Solution Seeking"],
                [
                    f"{scores.get('urgency', 0.0):.2f}",
                    f"{scores.get('pain_point_intensity', 0.0):.2f}",
                    f"{scores.get('commercial_relevance', 0.0):.2f}",
                    f"{scores.get('solution_seeking', 0.0):.2f}",
                ],
            ]
            scores_table = Table(scores_data, colWidths=[80, 80, 80, 100])
            scores_table.setStyle(make_table_style(
                header_font_size=8,
                body_font_size=8,
                right_align_col=None,
                center_align=True,
            ))
            story.append(scores_table)
            story.append(Spacer(1, 4))
            
            # Problem summary
            signals = card.get("extracted_signals", {})
            problem_summary = signals.get("problem_summary", "")
            if problem_summary:
                ps_text = _truncate_str(problem_summary, _MAX_PROBLEM_SUMMARY)
                story.append(labeled_paragraph("Problem", safe_text(ps_text), body_style))
            
            # Rationale
            rationale = card.get("rationale", "")
            if rationale:
                rat_text = _truncate_str(rationale, _MAX_RATIONALE)
                story.append(labeled_paragraph("Rationale", safe_text(rat_text), body_style))
            
            # Keywords
            keywords = signals.get("keywords", [])
            if keywords:
                kw_list = _truncate_list(keywords, _MAX_LIST_ITEMS, _MAX_ITEM_CHARS)
                kw_str = ", ".join(safe_text(k) for k in kw_list)
                story.append(labeled_paragraph("Keywords", kw_str, body_style))
            
            # Budget hints
            budget_hints = signals.get("budget_hints", [])
            if budget_hints:
                bh_list = _truncate_list(budget_hints, _MAX_LIST_ITEMS, _MAX_ITEM_CHARS)
                bh_str = ", ".join(safe_text(h) for h in bh_list)
                story.append(labeled_paragraph("Budget Hints", bh_str, body_style))
            
            # Tooling stack
            tooling_stack = signals.get("tooling_stack", [])
            if tooling_stack:
                ts_list = _truncate_list(tooling_stack, _MAX_LIST_ITEMS, _MAX_ITEM_CHARS)
                ts_str = ", ".join(safe_text(t) for t in ts_list)
                story.append(labeled_paragraph("Tooling Stack", ts_str, body_style))
            
            # Safety notes
            safety_notes = card.get("safety_notes", [])
            if safety_notes:
                sn_list = _truncate_list(safety_notes, _MAX_LIST_ITEMS, _MAX_ITEM_CHARS)
                sn_str = ", ".join(safe_text(n) for n in sn_list)
                story.append(labeled_paragraph("Safety Notes", sn_str, small_style))
            
            # Separator
            story.append(Spacer(1, 12))
    
    # =================================================================
    # APPENDIX: INVALID LINES
    # =================================================================
    if invalid_lines:
        story.append(Paragraph("Appendix: Invalid Lines", heading_style))
        
        for entry in invalid_lines:
            line_num = entry.get("line_number", "?")
            reason = entry.get("reason", "unknown error")
            raw = entry.get("raw", "")
            
            story.append(labeled_paragraph(f"Line {line_num}", safe_text(reason), body_style))
            if raw:
                # Use <font> for "Raw:" label, avoid <i> for CJK content
                story.append(Paragraph(
                    f'<font face="Helvetica-Oblique">Raw:</font> {safe_text(raw)}',
                    small_style
                ))
            story.append(Spacer(1, 6))
    
    # Build PDF
    doc.build(story)

