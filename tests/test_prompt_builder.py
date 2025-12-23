"""
Tests for prompt/builder.py - Prompt construction.
"""

import json

import pytest

from siw_intent_brain.config import BrainConfig
from siw_intent_brain.prompt.builder import (
    build_chat_request,
    get_system_prompt,
    _build_output_template,
    _build_field_hints,
    _sanitize_context,
)
from siw_intent_brain.llm.types import ChatRequest, ChatMessage


# =============================================================================
# Test System Prompt
# =============================================================================

class TestSystemPrompt:
    def test_system_prompt_loads(self):
        """System prompt loads without error."""
        prompt = get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Should have substantial content
    
    def test_system_prompt_requires_json(self):
        """System prompt requires JSON output."""
        prompt = get_system_prompt()
        assert "JSON" in prompt.upper()
        assert "STRICT" in prompt.upper() or "strict" in prompt
    
    def test_system_prompt_forbids_markdown(self):
        """System prompt forbids markdown."""
        prompt = get_system_prompt()
        lower = prompt.lower()
        assert "no markdown" in lower or "no prose" in lower
    
    def test_system_prompt_forbids_bypass(self):
        """System prompt forbids bypass instructions."""
        prompt = get_system_prompt()
        lower = prompt.lower()
        assert "bypass" in lower or "forbidden" in lower
    
    def test_system_prompt_no_antidetection(self):
        """System prompt does NOT contain anti-detection terms."""
        prompt = get_system_prompt()
        lower = prompt.lower()
        assert "anti-detection" not in lower
        assert "antidetection" not in lower
        assert "human delay" not in lower
        assert "拟人化" not in prompt
    
    def test_system_prompt_score_range(self):
        """System prompt specifies score range 0-1."""
        prompt = get_system_prompt()
        assert "0" in prompt and "1" in prompt
    
    def test_system_prompt_rationale_limit(self):
        """System prompt limits rationale length."""
        prompt = get_system_prompt()
        lower = prompt.lower()
        assert "2 sentence" in lower or "two sentence" in lower
    
    def test_system_prompt_requires_all_fields(self):
        """System prompt requires all top-level fields."""
        prompt = get_system_prompt()
        lower = prompt.lower()
        assert "must include all" in lower or "all required" in lower
    
    def test_system_prompt_forbids_extra_fields(self):
        """System prompt forbids extra fields."""
        prompt = get_system_prompt()
        lower = prompt.lower()
        assert "no extra" in lower or "not include any keys not" in lower
    
    def test_system_prompt_meta_requirements(self):
        """System prompt specifies meta requirements."""
        prompt = get_system_prompt()
        assert "meta" in prompt.lower()
        assert "provider" in prompt or "openrouter" in prompt
        assert "schema_version" in prompt or "lead_card.v1" in prompt


# =============================================================================
# Test Output Template
# =============================================================================

class TestOutputTemplate:
    def test_template_has_all_required_fields(self):
        """Output template includes all required top-level fields."""
        template = _build_output_template()
        required = ["ok", "scores", "confidence", "lead_tier", 
                    "recommended_next_step", "rationale", 
                    "extracted_signals", "safety_notes", "meta"]
        for field in required:
            assert field in template, f"Missing field: {field}"
    
    def test_template_scores_structure(self):
        """Output template has correct scores structure."""
        template = _build_output_template()
        scores = template["scores"]
        assert scores["urgency"] == 0.0
        assert scores["pain_point_intensity"] == 0.0
        assert scores["commercial_relevance"] == 0.0
        assert scores["solution_seeking"] == 0.0
    
    def test_template_has_meta(self):
        """Output template includes meta with correct defaults."""
        template = _build_output_template()
        meta = template["meta"]
        assert meta["provider"] == "openrouter"
        assert meta["schema_version"] == "lead_card.v1"
        assert meta["parser_mode"] == "strict"
    
    def test_template_extracted_signals_structure(self):
        """Output template has correct extracted_signals structure."""
        template = _build_output_template()
        signals = template["extracted_signals"]
        assert signals["problem_summary"] == ""
        assert signals["constraints"] == []
        assert signals["budget_hints"] == []
        assert signals["tooling_stack"] == []
        assert signals["keywords"] == []
    
    def test_template_default_values(self):
        """Output template has sensible defaults."""
        template = _build_output_template()
        assert template["ok"] is True
        assert template["confidence"] == 0.0
        assert template["lead_tier"] == "D"
        assert template["recommended_next_step"] == "monitor"
        assert template["rationale"] == ""
        assert template["safety_notes"] == []


class TestFieldHints:
    def test_hints_cover_all_scores(self):
        """Field hints cover all score fields."""
        hints = _build_field_hints()
        assert "scores.urgency" in hints
        assert "scores.pain_point_intensity" in hints
        assert "scores.commercial_relevance" in hints
        assert "scores.solution_seeking" in hints
    
    def test_hints_specify_ranges(self):
        """Field hints specify value ranges."""
        hints = _build_field_hints()
        assert "0..1" in hints["confidence"]
        assert "0..1" in hints["scores.urgency"]
    
    def test_hints_specify_enums(self):
        """Field hints specify enum values."""
        hints = _build_field_hints()
        assert "S" in hints["lead_tier"] and "D" in hints["lead_tier"]
        assert "monitor" in hints["recommended_next_step"]
        assert "offer_resource" in hints["recommended_next_step"]
    
    def test_hints_specify_limits(self):
        """Field hints specify length limits."""
        hints = _build_field_hints()
        assert "400" in hints["rationale"] or "max" in hints["rationale"].lower()
        assert "50" in hints["extracted_signals.constraints"]


# =============================================================================
# Test Context Sanitization
# =============================================================================

class TestSanitizeContext:
    def test_none_context(self):
        """None context returns empty strings."""
        ctx = _sanitize_context(None)
        assert ctx == {
            "subreddit": "",
            "title": "",
            "author": "",
            "permalink": "",
        }
    
    def test_valid_context(self):
        """Valid context passes through."""
        ctx = _sanitize_context({
            "subreddit": "python",
            "title": "Help needed",
            "author": "user123",
            "permalink": "https://reddit.com/...",
        })
        assert ctx["subreddit"] == "python"
        assert ctx["title"] == "Help needed"
    
    def test_strips_whitespace(self):
        """Context values are stripped."""
        ctx = _sanitize_context({
            "subreddit": "  python  ",
            "title": "\n title \n",
        })
        assert ctx["subreddit"] == "python"
        assert ctx["title"] == "title"
    
    def test_handles_none_values(self):
        """None values in context become empty strings."""
        ctx = _sanitize_context({
            "subreddit": None,
            "title": "Test",
        })
        assert ctx["subreddit"] == ""
        assert ctx["title"] == "Test"
    
    def test_extra_fields_ignored(self):
        """Extra fields in context are ignored."""
        ctx = _sanitize_context({
            "subreddit": "test",
            "extra_field": "ignored",
            "api_key": "should_not_appear",
        })
        assert "extra_field" not in ctx
        assert "api_key" not in ctx
        assert len(ctx) == 4  # Only standard 4 fields


# =============================================================================
# Test build_chat_request
# =============================================================================

class TestBuildChatRequest:
    @pytest.fixture
    def config(self):
        """Create a test config."""
        return BrainConfig(
            api_key="test-key-do-not-use",
            model="openai/gpt-4o-mini",
            response_format_json=True,
        )
    
    def test_returns_chat_request(self, config):
        """build_chat_request returns ChatRequest."""
        req = build_chat_request(config, "test text", None)
        assert isinstance(req, ChatRequest)
    
    def test_uses_config_model(self, config):
        """Request uses model from config."""
        req = build_chat_request(config, "test", None)
        assert req.model == "openai/gpt-4o-mini"
    
    def test_has_system_and_user_messages(self, config):
        """Request has exactly 2 messages: system and user."""
        req = build_chat_request(config, "test", None)
        assert len(req.messages) == 2
        assert req.messages[0].role == "system"
        assert req.messages[1].role == "user"
    
    def test_user_message_is_json(self, config):
        """User message content is valid JSON."""
        req = build_chat_request(config, "test text", {"subreddit": "python"})
        user_content = req.messages[1].content
        
        # Should be valid JSON
        payload = json.loads(user_content)
        assert isinstance(payload, dict)
    
    def test_user_payload_has_required_fields(self, config):
        """User payload contains task, context, text, output_template, field_hints."""
        req = build_chat_request(config, "analyze this", {"subreddit": "test"})
        payload = json.loads(req.messages[1].content)
        
        assert "task" in payload
        assert "context" in payload
        assert "text" in payload
        assert "output_template" in payload
        assert "field_hints" in payload
    
    def test_text_in_payload(self, config):
        """Text is included in payload."""
        req = build_chat_request(config, "my input text", None)
        payload = json.loads(req.messages[1].content)
        assert payload["text"] == "my input text"
    
    def test_context_in_payload(self, config):
        """Context fields are in payload."""
        req = build_chat_request(config, "text", {"subreddit": "saas", "title": "Help"})
        payload = json.loads(req.messages[1].content)
        
        assert payload["context"]["subreddit"] == "saas"
        assert payload["context"]["title"] == "Help"
    
    def test_output_template_in_payload(self, config):
        """Output template is included in payload."""
        req = build_chat_request(config, "text", None)
        payload = json.loads(req.messages[1].content)
        
        template = payload["output_template"]
        assert "ok" in template
        assert "scores" in template
        assert "lead_tier" in template
        assert "recommended_next_step" in template
        assert "meta" in template
    
    def test_field_hints_in_payload(self, config):
        """Field hints are included in payload."""
        req = build_chat_request(config, "text", None)
        payload = json.loads(req.messages[1].content)
        
        hints = payload["field_hints"]
        assert "confidence" in hints
        assert "lead_tier" in hints
    
    def test_response_format_enabled(self, config):
        """response_format is set when config enables it."""
        req = build_chat_request(config, "text", None)
        assert req.response_format == {"type": "json_object"}
    
    def test_response_format_disabled(self):
        """response_format is None when config disables it."""
        config = BrainConfig(
            api_key="test-key",
            response_format_json=False,
        )
        req = build_chat_request(config, "text", None)
        assert req.response_format is None
    
    def test_temperature_is_02(self, config):
        """Temperature is fixed at 0.2."""
        req = build_chat_request(config, "text", None)
        assert req.temperature == 0.2
    
    def test_max_tokens_is_600(self, config):
        """Max tokens is fixed at 600."""
        req = build_chat_request(config, "text", None)
        assert req.max_tokens == 600


# =============================================================================
# Test Security: No Key Leakage
# =============================================================================

class TestNoKeyLeakage:
    def test_api_key_not_in_messages(self):
        """API key never appears in message content."""
        config = BrainConfig(
            api_key="sk-super-secret-key-12345",
            model="test/model",
        )
        req = build_chat_request(config, "analyze this", {"subreddit": "test"})
        
        # Check all message contents
        for msg in req.messages:
            assert "sk-super-secret-key-12345" not in msg.content
            assert "super-secret" not in msg.content
    
    def test_api_key_not_in_request_dict(self):
        """API key never appears in request dict."""
        config = BrainConfig(
            api_key="sk-secret-key-xyz",
            model="test/model",
        )
        req = build_chat_request(config, "text", None)
        req_dict = req.to_dict()
        
        req_str = json.dumps(req_dict)
        assert "sk-secret-key-xyz" not in req_str
        assert "secret-key" not in req_str
    
    def test_context_api_key_not_passed(self):
        """API key in context is not passed through."""
        config = BrainConfig(api_key="real-key", model="test")
        req = build_chat_request(config, "text", {
            "subreddit": "test",
            "api_key": "SHOULD_NOT_APPEAR",
            "secret": "ALSO_HIDDEN",
        })
        
        payload = json.loads(req.messages[1].content)
        context = payload["context"]
        
        assert "api_key" not in context
        assert "secret" not in context
        assert "SHOULD_NOT_APPEAR" not in json.dumps(payload)


# =============================================================================
# Test ChatRequest.to_dict
# =============================================================================

class TestChatRequestToDict:
    def test_to_dict_structure(self):
        """to_dict produces correct structure."""
        req = ChatRequest(
            model="test/model",
            messages=(
                ChatMessage(role="system", content="sys"),
                ChatMessage(role="user", content="usr"),
            ),
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        d = req.to_dict()
        
        assert d["model"] == "test/model"
        assert len(d["messages"]) == 2
        assert d["messages"][0] == {"role": "system", "content": "sys"}
        assert d["messages"][1] == {"role": "user", "content": "usr"}
        assert d["temperature"] == 0.2
        assert d["max_tokens"] == 600
        assert d["response_format"] == {"type": "json_object"}
    
    def test_to_dict_without_response_format(self):
        """to_dict omits response_format when None."""
        req = ChatRequest(
            model="test",
            messages=(ChatMessage(role="user", content="hi"),),
            response_format=None,
        )
        d = req.to_dict()
        
        assert "response_format" not in d

