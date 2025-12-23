"""
Tests for config.py - Configuration loading.
"""

import os
import tempfile
from unittest import mock

import pytest

from siw_intent_brain.config import BrainConfig, load_config
from siw_intent_brain.errors import ConfigError, E_CONFIG_MISSING_KEY


# =============================================================================
# Test BrainConfig Dataclass
# =============================================================================

class TestBrainConfig:
    def test_required_api_key(self):
        """BrainConfig requires api_key."""
        cfg = BrainConfig(api_key="test-key")
        assert cfg.api_key == "test-key"
    
    def test_default_values(self):
        """BrainConfig has sensible defaults."""
        cfg = BrainConfig(api_key="test-key")
        assert cfg.model == "openai/gpt-4o-mini"
        assert cfg.base_url == "https://openrouter.ai/api/v1/chat/completions"
        assert cfg.timeout_s == 30
        assert cfg.max_retries == 3
        assert cfg.backoff_s == 1.2
        assert cfg.min_confidence == 0.35
        assert cfg.max_rationale_chars == 400
        assert cfg.max_list_items == 50
        assert cfg.response_format_json is True
        assert cfg.http_referer is None
        assert cfg.x_title is None
    
    def test_custom_values(self):
        """BrainConfig accepts custom values."""
        cfg = BrainConfig(
            api_key="my-key",
            model="anthropic/claude-3",
            timeout_s=60,
            min_confidence=0.5,
        )
        assert cfg.api_key == "my-key"
        assert cfg.model == "anthropic/claude-3"
        assert cfg.timeout_s == 60
        assert cfg.min_confidence == 0.5
    
    def test_immutable(self):
        """BrainConfig is immutable (frozen)."""
        cfg = BrainConfig(api_key="test")
        with pytest.raises(Exception):  # FrozenInstanceError
            cfg.api_key = "other"  # type: ignore


# =============================================================================
# Test load_config - Missing API Key
# =============================================================================

class TestLoadConfigMissingKey:
    def test_missing_api_key_raises_config_error(self):
        """load_config raises ConfigError if OPENROUTER_API_KEY is missing."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Also clear any loaded .env
            with mock.patch("siw_intent_brain.config.load_dotenv"):
                with pytest.raises(ConfigError) as exc_info:
                    load_config(load_dotenv_file=False)
                
                assert E_CONFIG_MISSING_KEY in str(exc_info.value)
                assert "OPENROUTER_API_KEY" in str(exc_info.value)
    
    def test_empty_api_key_raises_config_error(self):
        """Empty string API key should raise ConfigError."""
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                load_config(load_dotenv_file=False)
            
            assert E_CONFIG_MISSING_KEY in str(exc_info.value)
    
    def test_whitespace_api_key_raises_config_error(self):
        """Whitespace-only API key should raise ConfigError."""
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "   "}, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                load_config(load_dotenv_file=False)
            
            assert E_CONFIG_MISSING_KEY in str(exc_info.value)


# =============================================================================
# Test load_config - Environment Variables
# =============================================================================

class TestLoadConfigEnv:
    def test_api_key_from_env(self):
        """API key loaded from environment."""
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key"}, clear=True):
            cfg = load_config(load_dotenv_file=False)
            assert cfg.api_key == "env-key"
    
    def test_all_env_vars(self):
        """All config values can be set via environment."""
        env = {
            "OPENROUTER_API_KEY": "env-key",
            "OPENROUTER_MODEL": "custom/model",
            "OPENROUTER_BASE_URL": "https://custom.api/v1",
            "OPENROUTER_TIMEOUT_S": "45",
            "OPENROUTER_MAX_RETRIES": "5",
            "OPENROUTER_BACKOFF_S": "2.5",
            "OPENROUTER_HTTP_REFERER": "https://mysite.com",
            "OPENROUTER_X_TITLE": "MyApp",
            "BRAIN_MIN_CONFIDENCE": "0.5",
            "BRAIN_MAX_RATIONALE_CHARS": "300",
            "BRAIN_MAX_LIST_ITEMS": "25",
            "BRAIN_RESPONSE_FORMAT_JSON": "false",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = load_config(load_dotenv_file=False)
            
            assert cfg.api_key == "env-key"
            assert cfg.model == "custom/model"
            assert cfg.base_url == "https://custom.api/v1"
            assert cfg.timeout_s == 45
            assert cfg.max_retries == 5
            assert cfg.backoff_s == 2.5
            assert cfg.http_referer == "https://mysite.com"
            assert cfg.x_title == "MyApp"
            assert cfg.min_confidence == 0.5
            assert cfg.max_rationale_chars == 300
            assert cfg.max_list_items == 25
            assert cfg.response_format_json is False
    
    def test_bool_parsing_variations(self):
        """Boolean parsing handles various string formats."""
        for true_val in ["true", "True", "TRUE", "1", "yes", "Yes", "on"]:
            with mock.patch.dict(os.environ, {
                "OPENROUTER_API_KEY": "key",
                "BRAIN_RESPONSE_FORMAT_JSON": true_val,
            }, clear=True):
                cfg = load_config(load_dotenv_file=False)
                assert cfg.response_format_json is True, f"Failed for '{true_val}'"
        
        for false_val in ["false", "False", "FALSE", "0", "no", "No", "off"]:
            with mock.patch.dict(os.environ, {
                "OPENROUTER_API_KEY": "key",
                "BRAIN_RESPONSE_FORMAT_JSON": false_val,
            }, clear=True):
                cfg = load_config(load_dotenv_file=False)
                assert cfg.response_format_json is False, f"Failed for '{false_val}'"


# =============================================================================
# Test load_config - YAML Config
# =============================================================================

class TestLoadConfigYaml:
    def test_yaml_api_key(self):
        """API key can be loaded from YAML."""
        yaml_content = """
openrouter:
  api_key: yaml-key
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                cfg = load_config(config_path=yaml_path, load_dotenv_file=False)
                assert cfg.api_key == "yaml-key"
        finally:
            os.unlink(yaml_path)
    
    def test_yaml_all_values(self):
        """All config values can be set via YAML."""
        yaml_content = """
openrouter:
  api_key: yaml-key
  model: yaml/model
  base_url: https://yaml.api/v1
  timeout_s: 60
  max_retries: 2
  backoff_s: 1.5
  http_referer: https://yaml-site.com
  x_title: YamlApp

brain:
  min_confidence: 0.4
  max_rationale_chars: 350
  max_list_items: 30
  response_format_json: false
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                cfg = load_config(config_path=yaml_path, load_dotenv_file=False)
                
                assert cfg.api_key == "yaml-key"
                assert cfg.model == "yaml/model"
                assert cfg.base_url == "https://yaml.api/v1"
                assert cfg.timeout_s == 60
                assert cfg.max_retries == 2
                assert cfg.backoff_s == 1.5
                assert cfg.http_referer == "https://yaml-site.com"
                assert cfg.x_title == "YamlApp"
                assert cfg.min_confidence == 0.4
                assert cfg.max_rationale_chars == 350
                assert cfg.max_list_items == 30
                assert cfg.response_format_json is False
        finally:
            os.unlink(yaml_path)
    
    def test_yaml_file_not_found(self):
        """Missing YAML file raises ConfigError."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path="/nonexistent/config.yaml", load_dotenv_file=False)
            
            assert "not found" in str(exc_info.value)
    
    def test_yaml_invalid_syntax(self):
        """Invalid YAML raises ConfigError."""
        yaml_content = """
openrouter:
  api_key: [invalid yaml
  missing: closing bracket
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                with pytest.raises(ConfigError) as exc_info:
                    load_config(config_path=yaml_path, load_dotenv_file=False)
                
                assert "Invalid YAML" in str(exc_info.value)
        finally:
            os.unlink(yaml_path)


# =============================================================================
# Test load_config - Priority (Env > YAML > Default)
# =============================================================================

class TestLoadConfigPriority:
    def test_env_overrides_yaml(self):
        """Environment variables take priority over YAML."""
        yaml_content = """
openrouter:
  api_key: yaml-key
  model: yaml/model
  timeout_s: 60

brain:
  min_confidence: 0.4
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            env = {
                "OPENROUTER_API_KEY": "env-key",  # Override YAML
                "OPENROUTER_MODEL": "env/model",  # Override YAML
                # timeout_s not in env, should use YAML value
                # min_confidence not in env, should use YAML value
            }
            with mock.patch.dict(os.environ, env, clear=True):
                cfg = load_config(config_path=yaml_path, load_dotenv_file=False)
                
                # Env overrides
                assert cfg.api_key == "env-key"
                assert cfg.model == "env/model"
                
                # YAML values (not overridden)
                assert cfg.timeout_s == 60
                assert cfg.min_confidence == 0.4
        finally:
            os.unlink(yaml_path)
    
    def test_yaml_overrides_defaults(self):
        """YAML values override defaults."""
        yaml_content = """
openrouter:
  api_key: yaml-key
  timeout_s: 45
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                cfg = load_config(config_path=yaml_path, load_dotenv_file=False)
                
                # YAML overrides default (30)
                assert cfg.timeout_s == 45
                
                # Default values (not in YAML)
                assert cfg.max_retries == 3  # default
                assert cfg.min_confidence == 0.35  # default
        finally:
            os.unlink(yaml_path)
    
    def test_defaults_used_when_no_override(self):
        """Default values used when not in env or YAML."""
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "key"}, clear=True):
            cfg = load_config(load_dotenv_file=False)
            
            # All defaults
            assert cfg.model == "openai/gpt-4o-mini"
            assert cfg.timeout_s == 30
            assert cfg.max_retries == 3
            assert cfg.backoff_s == 1.2
            assert cfg.min_confidence == 0.35
            assert cfg.max_rationale_chars == 400
            assert cfg.max_list_items == 50
            assert cfg.response_format_json is True


# =============================================================================
# Test ErrorInfo
# =============================================================================

from siw_intent_brain.errors import ErrorInfo


class TestErrorInfo:
    def test_basic_creation(self):
        """ErrorInfo can be created with required fields."""
        err = ErrorInfo(code="E_TEST", detail="Test error")
        assert err.code == "E_TEST"
        assert err.detail == "Test error"
        assert err.retryable is False
        assert err.http_status is None
    
    def test_all_fields(self):
        """ErrorInfo accepts all fields."""
        err = ErrorInfo(
            code="E_UPSTREAM_HTTP",
            detail="HTTP 500 error",
            retryable=True,
            http_status=500,
        )
        assert err.code == "E_UPSTREAM_HTTP"
        assert err.detail == "HTTP 500 error"
        assert err.retryable is True
        assert err.http_status == 500
    
    def test_to_meta_fields(self):
        """to_meta_fields returns correct dict."""
        err = ErrorInfo(code="E_TEST", detail="Short detail")
        meta = err.to_meta_fields()
        assert meta == {
            "error_code": "E_TEST",
            "error_detail": "Short detail",
        }
    
    def test_to_meta_fields_truncates_long_detail(self):
        """to_meta_fields truncates detail over 280 chars."""
        long_detail = "x" * 300
        err = ErrorInfo(code="E_TEST", detail=long_detail)
        meta = err.to_meta_fields()
        
        assert len(meta["error_detail"]) == 280
        assert meta["error_detail"].endswith("...")
    
    def test_immutable(self):
        """ErrorInfo is immutable (frozen)."""
        err = ErrorInfo(code="E_TEST", detail="Test")
        with pytest.raises(Exception):  # FrozenInstanceError
            err.code = "E_OTHER"  # type: ignore

