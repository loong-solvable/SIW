"""
Prompt building for LLM requests.

Constructs stable, deterministic prompts with:
  - System prompt enforcing strict JSON output
  - User payload containing context, text, and output schema
  - Optional response_format for JSON mode
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import BrainConfig
from ..llm.types import ChatMessage, ChatRequest


# Cache for system prompt (loaded once)
_SYSTEM_PROMPT_CACHE: Optional[str] = None


def _load_system_prompt() -> str:
    """
    Load system prompt from system.txt file.
    
    Uses module-level cache to avoid repeated file reads.
    """
    global _SYSTEM_PROMPT_CACHE
    
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE
    
    # system.txt is in the same directory as this module
    prompt_path = Path(__file__).parent / "system.txt"
    
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            _SYSTEM_PROMPT_CACHE = f.read().strip()
    except FileNotFoundError:
        # Fallback if file not found (shouldn't happen in production)
        _SYSTEM_PROMPT_CACHE = (
            "You are an intent-scoring engine. "
            "Output STRICT JSON ONLY. No markdown. No prose. "
            "All scores must be numbers between 0 and 1."
        )
    
    return _SYSTEM_PROMPT_CACHE


def _build_output_template() -> Dict[str, Any]:
    """
    Build the output template for the LLM.
    
    This is a strict JSON template with placeholder values.
    The model should return exactly this shape with values replaced.
    Field order is fixed for stability.
    """
    return {
        "ok": True,
        "scores": {
            "urgency": 0.0,
            "pain_point_intensity": 0.0,
            "commercial_relevance": 0.0,
            "solution_seeking": 0.0,
        },
        "confidence": 0.0,
        "lead_tier": "D",
        "recommended_next_step": "monitor",
        "rationale": "",
        "extracted_signals": {
            "problem_summary": "",
            "constraints": [],
            "budget_hints": [],
            "tooling_stack": [],
            "keywords": [],
        },
        "safety_notes": [],
        "meta": {
            "model": "",
            "provider": "openrouter",
            "latency_ms": 0,
            "retries": 0,
            "parser_mode": "strict",
            "schema_version": "lead_card.v1",
        },
    }


def _build_field_hints() -> Dict[str, str]:
    """
    Build hints for each field (what values are valid).
    
    Separate from template to keep template clean.
    """
    return {
        "ok": "always true (system sets false on error)",
        "scores.urgency": "float 0..1 (time pressure: deadline, ASAP, urgent)",
        "scores.pain_point_intensity": "float 0..1 (complaint intensity, loss, cost)",
        "scores.commercial_relevance": "float 0..1 (purchasable solution path exists)",
        "scores.solution_seeking": "float 0..1 (explicitly seeking advice/alternatives)",
        "confidence": "float 0..1 (your confidence in this assessment)",
        "lead_tier": "S | A | B | C | D (S=highest intent, D=lowest)",
        "recommended_next_step": "ignore | monitor | draft_reply | ask_question | offer_resource",
        "rationale": "max 2 sentences, max 400 chars",
        "extracted_signals.problem_summary": "one-line summary of the problem",
        "extracted_signals.constraints": "array of strings, max 50 items",
        "extracted_signals.budget_hints": "array of strings, max 50 items",
        "extracted_signals.tooling_stack": "array of strings, max 50 items",
        "extracted_signals.keywords": "array of strings, max 50 items",
        "safety_notes": "array of strings, etiquette/spam-risk only, max 50 items",
        "meta.model": "will be filled by system",
        "meta.provider": "always 'openrouter'",
        "meta.latency_ms": "will be filled by system",
        "meta.retries": "will be filled by system",
        "meta.parser_mode": "strict | extracted | fail_closed",
        "meta.schema_version": "always 'lead_card.v1'",
    }


def _sanitize_context(context: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Sanitize context dict to only include safe string fields.
    
    Does NOT include any sensitive data like API keys.
    """
    if context is None:
        return {
            "subreddit": "",
            "title": "",
            "author": "",
            "permalink": "",
        }
    
    return {
        "subreddit": str(context.get("subreddit", "") or "").strip(),
        "title": str(context.get("title", "") or "").strip(),
        "author": str(context.get("author", "") or "").strip(),
        "permalink": str(context.get("permalink", "") or "").strip(),
    }


def build_chat_request(
    cfg: BrainConfig,
    text: str,
    context: Optional[Dict[str, Any]] = None,
) -> ChatRequest:
    """
    Build a ChatRequest for intent scoring.
    
    Args:
        cfg: Brain configuration (contains model, response_format_json flag).
        text: The text to analyze.
        context: Optional context dict (subreddit, title, author, permalink).
    
    Returns:
        ChatRequest ready to send to LLM provider.
    
    Note:
        - Does NOT log or print any content.
        - Does NOT include API key in the request payload.
        - Payload structure is stable (fixed field names and order).
    """
    system_prompt = _load_system_prompt()
    
    # Build user payload with stable field order
    user_payload = {
        "task": "Analyze the following text for commercial intent signals. Return exactly the output_template shape with placeholder values replaced by your analysis.",
        "context": _sanitize_context(context),
        "text": text,
        "output_template": _build_output_template(),
        "field_hints": _build_field_hints(),
    }
    
    # Convert to JSON string for user message
    user_content = json.dumps(user_payload, ensure_ascii=False, indent=None)
    
    # Build messages tuple
    messages = (
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_content),
    )
    
    # Response format (optional, some models don't support it)
    response_format: Optional[Dict[str, Any]] = None
    if cfg.response_format_json:
        response_format = {"type": "json_object"}
    
    return ChatRequest(
        model=cfg.model,
        messages=messages,
        temperature=0.2,
        max_tokens=600,
        response_format=response_format,
    )


def get_system_prompt() -> str:
    """
    Get the system prompt (for testing/inspection).
    
    Returns:
        The system prompt string.
    """
    return _load_system_prompt()

