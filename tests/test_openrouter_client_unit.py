"""
Unit tests for OpenRouterClient.

All tests are OFFLINE - no real network requests.
Uses unittest.mock to mock requests.post.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from siw_intent_brain.config import BrainConfig
from siw_intent_brain.errors import (
    UpstreamError,
    E_UPSTREAM_HTTP,
    E_UPSTREAM_TIMEOUT,
    E_UPSTREAM_EMPTY_CONTENT,
)
from siw_intent_brain.llm.openrouter_client import OpenRouterClient
from siw_intent_brain.llm.types import ChatMessage, ChatRequest


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config() -> BrainConfig:
    """Basic config for testing."""
    return BrainConfig(
        api_key="test-key-12345",
        model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        timeout_s=10,
        max_retries=3,
        backoff_s=0.01,  # Very small backoff for fast tests
    )


@pytest.fixture
def client(config: BrainConfig) -> OpenRouterClient:
    """Client instance with test config."""
    return OpenRouterClient(config)


@pytest.fixture
def chat_request() -> ChatRequest:
    """Sample chat request."""
    return ChatRequest(
        model="openai/gpt-4o-mini",
        messages=(
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user", content="Hello"),
        ),
        temperature=0.2,
        max_tokens=600,
    )


def make_success_response(content: str = '{"ok": true}') -> MagicMock:
    """Create a mock successful response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    mock_resp.text = json.dumps({"choices": [{"message": {"content": content}}]})
    return mock_resp


def make_error_response(status_code: int, body: str = "Error") -> MagicMock:
    """Create a mock error response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = body
    mock_resp.json.return_value = {"error": body}
    return mock_resp


# =============================================================================
# Test: Successful Request (200 OK)
# =============================================================================

class TestSuccessfulRequest:
    """Tests for successful 200 OK responses."""

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_complete_success_returns_content(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Complete returns correct content on 200 OK."""
        expected_content = '{"scores": {"urgency": 0.5}}'
        mock_post.return_value = make_success_response(expected_content)
        
        response = client.complete(chat_request)
        
        assert response.content == expected_content
        assert response.status_code == 200
        assert response.retries == 0
        assert response.latency_ms >= 0

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_complete_success_raw_response(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Complete includes raw response dict."""
        mock_post.return_value = make_success_response("test content")
        
        response = client.complete(chat_request)
        
        assert "choices" in response.raw
        assert response.raw["choices"][0]["message"]["content"] == "test content"

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_complete_sends_correct_headers(
        self, mock_post: MagicMock, config: BrainConfig, chat_request: ChatRequest
    ) -> None:
        """Complete sends Authorization and Content-Type headers."""
        mock_post.return_value = make_success_response()
        client = OpenRouterClient(config)
        
        client.complete(chat_request)
        
        call_kwargs = mock_post.call_args.kwargs
        headers = call_kwargs["headers"]
        assert headers["Authorization"] == f"Bearer {config.api_key}"
        assert headers["Content-Type"] == "application/json"

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_complete_sends_optional_headers(
        self, mock_post: MagicMock, chat_request: ChatRequest
    ) -> None:
        """Complete sends HTTP-Referer and X-Title if configured."""
        config = BrainConfig(
            api_key="test-key",
            http_referer="https://example.com",
            x_title="Test App",
            backoff_s=0.01,
        )
        client = OpenRouterClient(config)
        mock_post.return_value = make_success_response()
        
        client.complete(chat_request)
        
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["HTTP-Referer"] == "https://example.com"
        assert headers["X-Title"] == "Test App"


# =============================================================================
# Test: HTTP Errors (429, 500, etc.)
# =============================================================================

class TestHTTPErrors:
    """Tests for HTTP error responses."""

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_http_429_retries_and_fails(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """429 Too Many Requests retries then raises UpstreamError."""
        mock_post.return_value = make_error_response(429, "Rate limited")
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert E_UPSTREAM_HTTP in str(exc_info.value)
        assert "429" in str(exc_info.value)
        # Should have tried max_retries times
        assert mock_post.call_count == client.cfg.max_retries

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_http_500_retries_and_fails(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """500 Internal Server Error retries then raises UpstreamError."""
        mock_post.return_value = make_error_response(500, "Server error")
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert E_UPSTREAM_HTTP in str(exc_info.value)
        assert mock_post.call_count == client.cfg.max_retries

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_http_502_is_retryable(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """502 Bad Gateway is retryable."""
        mock_post.return_value = make_error_response(502, "Bad gateway")
        
        with pytest.raises(UpstreamError):
            client.complete(chat_request)
        
        assert mock_post.call_count == client.cfg.max_retries

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_http_503_is_retryable(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """503 Service Unavailable is retryable."""
        mock_post.return_value = make_error_response(503, "Service unavailable")
        
        with pytest.raises(UpstreamError):
            client.complete(chat_request)
        
        assert mock_post.call_count == client.cfg.max_retries

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_http_400_not_retried(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """400 Bad Request is NOT retried (client error)."""
        mock_post.return_value = make_error_response(400, "Bad request")
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert E_UPSTREAM_HTTP in str(exc_info.value)
        # Should NOT retry on 400
        assert mock_post.call_count == 1

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_http_401_not_retried(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """401 Unauthorized is NOT retried."""
        mock_post.return_value = make_error_response(401, "Unauthorized")
        
        with pytest.raises(UpstreamError):
            client.complete(chat_request)
        
        assert mock_post.call_count == 1

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_retry_succeeds_on_second_attempt(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """First request fails with 500, second succeeds."""
        mock_post.side_effect = [
            make_error_response(500, "Server error"),
            make_success_response("ok"),
        ]
        
        response = client.complete(chat_request)
        
        assert response.content == "ok"
        assert response.retries == 1
        assert mock_post.call_count == 2


# =============================================================================
# Test: Timeout Handling
# =============================================================================

class TestTimeoutHandling:
    """Tests for request timeout scenarios."""

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_timeout_retries_and_fails(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Timeout retries then raises UpstreamError with timeout code."""
        import requests as req
        mock_post.side_effect = req.Timeout("Connection timed out")
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert E_UPSTREAM_TIMEOUT in str(exc_info.value)
        assert mock_post.call_count == client.cfg.max_retries

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_timeout_then_success(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """First request times out, second succeeds."""
        import requests as req
        mock_post.side_effect = [
            req.Timeout("Timeout"),
            make_success_response("recovered"),
        ]
        
        response = client.complete(chat_request)
        
        assert response.content == "recovered"
        assert response.retries == 1


# =============================================================================
# Test: Empty Content
# =============================================================================

class TestEmptyContent:
    """Tests for empty content responses."""

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_empty_content_raises_error(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Empty content string raises UpstreamError."""
        mock_post.return_value = make_success_response("")
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert E_UPSTREAM_EMPTY_CONTENT in str(exc_info.value)

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_whitespace_only_content_raises_error(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Whitespace-only content raises UpstreamError."""
        mock_post.return_value = make_success_response("   \n\t  ")
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert E_UPSTREAM_EMPTY_CONTENT in str(exc_info.value)

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_missing_choices_raises_empty_content(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Response without choices raises empty content error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "123"}  # No choices
        mock_post.return_value = mock_resp
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert E_UPSTREAM_EMPTY_CONTENT in str(exc_info.value)


# =============================================================================
# Test: Retry Count Tracking
# =============================================================================

class TestRetryCount:
    """Tests for correct retry count in response."""

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_no_retries_count_zero(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Successful first attempt has retries=0."""
        mock_post.return_value = make_success_response()
        
        response = client.complete(chat_request)
        
        assert response.retries == 0

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_one_retry_count_one(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """One retry (two attempts) has retries=1."""
        mock_post.side_effect = [
            make_error_response(500, "Error"),
            make_success_response(),
        ]
        
        response = client.complete(chat_request)
        
        assert response.retries == 1

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_two_retries_count_two(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Two retries (three attempts) has retries=2."""
        mock_post.side_effect = [
            make_error_response(500, "Error 1"),
            make_error_response(502, "Error 2"),
            make_success_response(),
        ]
        
        response = client.complete(chat_request)
        
        assert response.retries == 2


# =============================================================================
# Test: Request Exceptions
# =============================================================================

class TestRequestExceptions:
    """Tests for various request exceptions."""

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_connection_error_retries(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """ConnectionError retries then fails."""
        import requests as req
        mock_post.side_effect = req.ConnectionError("Connection refused")
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert E_UPSTREAM_HTTP in str(exc_info.value)
        assert mock_post.call_count == client.cfg.max_retries

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_connection_error_then_success(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """ConnectionError on first try, success on second."""
        import requests as req
        mock_post.side_effect = [
            req.ConnectionError("Connection refused"),
            make_success_response("ok"),
        ]
        
        response = client.complete(chat_request)
        
        assert response.content == "ok"
        assert response.retries == 1


# =============================================================================
# Test: Security (No API Key Logging)
# =============================================================================

class TestSecurity:
    """Tests to ensure API key is not exposed."""

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_api_key_in_header_not_in_response(
        self, mock_post: MagicMock, config: BrainConfig, chat_request: ChatRequest
    ) -> None:
        """API key is sent in header but not in response object."""
        mock_post.return_value = make_success_response()
        client = OpenRouterClient(config)
        
        response = client.complete(chat_request)
        
        # API key should not appear in response content or raw
        assert config.api_key not in str(response.content)
        assert config.api_key not in str(response.raw)

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_error_message_does_not_contain_api_key(
        self, mock_post: MagicMock, config: BrainConfig, chat_request: ChatRequest
    ) -> None:
        """Error messages do not expose API key."""
        mock_post.return_value = make_error_response(401, "Unauthorized")
        client = OpenRouterClient(config)
        
        with pytest.raises(UpstreamError) as exc_info:
            client.complete(chat_request)
        
        assert config.api_key not in str(exc_info.value)


# =============================================================================
# Test: Latency Measurement
# =============================================================================

class TestLatencyMeasurement:
    """Tests for latency measurement in response."""

    @patch("siw_intent_brain.llm.openrouter_client.requests.post")
    def test_latency_is_positive(
        self, mock_post: MagicMock, client: OpenRouterClient, chat_request: ChatRequest
    ) -> None:
        """Latency measurement is a positive integer."""
        mock_post.return_value = make_success_response()
        
        response = client.complete(chat_request)
        
        assert isinstance(response.latency_ms, int)
        assert response.latency_ms >= 0

