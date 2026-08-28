"""
SIW Intent Brain - Configuration loading.

Priority:
  1. Environment variables (highest)
  2. YAML config file (optional)
  3. Default values (lowest)

AI_API_KEY is the primary key name. OPENROUTER_API_KEY remains a compatibility
fallback; all other fields have defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from .errors import ConfigError, E_CONFIG_MISSING_KEY

# Try to import yaml; it's optional but included in dependencies
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


# =============================================================================
# BrainConfig Dataclass
# =============================================================================

@dataclass(frozen=True)
class BrainConfig:
    """
    Immutable configuration for IntentBrain.
    
    All fields except api_key have sensible defaults.
    """
    # OpenAI-compatible connection
    api_key: str
    model: str = "openai/gpt-4o-mini"
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    provider: str = "openai_compatible"
    timeout_s: int = 30
    max_retries: int = 3
    backoff_s: float = 1.2
    
    # Optional headers
    http_referer: Optional[str] = None
    x_title: Optional[str] = None
    
    # Brain behavior
    min_confidence: float = 0.35
    max_rationale_chars: int = 400
    max_list_items: int = 50
    response_format_json: bool = True  # Allow disabling if model doesn't support


def _normalize_ai_base_url(base_url: str) -> str:
    """Turn an OpenAI-compatible base URL into the chat completions endpoint."""
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


# =============================================================================
# Config Loading
# =============================================================================

def _load_yaml_file(path: str) -> Dict[str, Any]:
    """
    Load YAML file into dict.
    
    Raises:
        ConfigError: If yaml not installed or file unreadable.
    """
    if yaml is None:
        raise ConfigError("PyYAML not installed but YAML config requested.")
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}")


def _get_nested(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely get nested dict value."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is None:
            return default
    return current


def _parse_bool(val: Any) -> Optional[bool]:
    """Parse boolean from string or bool."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        lower = val.lower().strip()
        if lower in ("true", "1", "yes", "on"):
            return True
        if lower in ("false", "0", "no", "off"):
            return False
    return None


def _parse_int(val: Any) -> Optional[int]:
    """Parse int from string or int."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_float(val: Any) -> Optional[float]:
    """Parse float from string or float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def load_config(
    config_path: Optional[str] = None,
    load_dotenv_file: bool = True,
) -> BrainConfig:
    """
    Load configuration from environment and optional YAML file.
    
    Priority (highest to lowest):
      1. Environment variables
      2. YAML config file (if provided)
      3. Default values
    
    Args:
        config_path: Optional path to YAML config file.
        load_dotenv_file: Whether to load .env file (default True).
    
    Returns:
        BrainConfig instance.
    
    Raises:
        ConfigError: If neither AI_API_KEY nor its compatibility fallback exists.
    """
    # Load .env file if exists
    if load_dotenv_file:
        load_dotenv()
    
    # Load YAML if provided
    yaml_data: Dict[str, Any] = {}
    if config_path:
        yaml_data = _load_yaml_file(config_path)
    
    # Helper to get value with priority: env > yaml > default
    def get_str(env_key: str, yaml_keys: tuple, default: Optional[str] = None) -> Optional[str]:
        # Environment first
        env_val = os.getenv(env_key)
        if env_val is not None and env_val.strip():
            return env_val.strip()
        # YAML second
        yaml_val = _get_nested(yaml_data, *yaml_keys)
        if yaml_val is not None:
            return str(yaml_val).strip() if yaml_val else None
        # Default last
        return default
    
    def get_int(env_key: str, yaml_keys: tuple, default: int) -> int:
        env_val = _parse_int(os.getenv(env_key))
        if env_val is not None:
            return env_val
        yaml_val = _parse_int(_get_nested(yaml_data, *yaml_keys))
        if yaml_val is not None:
            return yaml_val
        return default
    
    def get_float(env_key: str, yaml_keys: tuple, default: float) -> float:
        env_val = _parse_float(os.getenv(env_key))
        if env_val is not None:
            return env_val
        yaml_val = _parse_float(_get_nested(yaml_data, *yaml_keys))
        if yaml_val is not None:
            return yaml_val
        return default
    
    def get_bool(env_key: str, yaml_keys: tuple, default: bool) -> bool:
        env_val = _parse_bool(os.getenv(env_key))
        if env_val is not None:
            return env_val
        yaml_val = _parse_bool(_get_nested(yaml_data, *yaml_keys))
        if yaml_val is not None:
            return yaml_val
        return default
    
    # --- Required: API Key (provider-neutral first, legacy fallback second) ---
    api_key = get_str("AI_API_KEY", ("ai", "api_key")) or get_str(
        "OPENROUTER_API_KEY", ("openrouter", "api_key")
    )
    if not api_key:
        raise ConfigError(
            f"{E_CONFIG_MISSING_KEY}: AI_API_KEY is required "
            "(OPENROUTER_API_KEY is accepted for compatibility)"
        )
    
    # --- OpenAI-compatible provider settings ---
    model = (
        get_str("AI_MODEL", ("ai", "model"))
        or get_str("OPENROUTER_MODEL", ("openrouter", "model"), "openai/gpt-4o-mini")
        or "openai/gpt-4o-mini"
    )
    provider = (
        get_str("AI_PROVIDER", ("ai", "provider"), "openai_compatible")
        or "openai_compatible"
    )
    ai_base_url = get_str("AI_BASE_URL", ("ai", "base_url"))
    if ai_base_url:
        base_url = _normalize_ai_base_url(ai_base_url)
    else:
        base_url = (
            get_str(
                "OPENROUTER_BASE_URL",
                ("openrouter", "base_url"),
                "https://openrouter.ai/api/v1/chat/completions",
            )
            or "https://openrouter.ai/api/v1/chat/completions"
        )

    timeout_s = _parse_int(os.getenv("AI_TIMEOUT_S"))
    if timeout_s is None:
        timeout_s = _parse_int(_get_nested(yaml_data, "ai", "timeout_s"))
    if timeout_s is None:
        timeout_s = get_int("OPENROUTER_TIMEOUT_S", ("openrouter", "timeout_s"), 30)

    max_retries = _parse_int(os.getenv("AI_MAX_RETRIES"))
    if max_retries is None:
        max_retries = _parse_int(_get_nested(yaml_data, "ai", "max_retries"))
    if max_retries is None:
        max_retries = get_int("OPENROUTER_MAX_RETRIES", ("openrouter", "max_retries"), 3)

    backoff_s = _parse_float(os.getenv("AI_BACKOFF_S"))
    if backoff_s is None:
        backoff_s = _parse_float(_get_nested(yaml_data, "ai", "backoff_s"))
    if backoff_s is None:
        backoff_s = get_float("OPENROUTER_BACKOFF_S", ("openrouter", "backoff_s"), 1.2)
    
    # --- Optional headers ---
    http_referer = get_str("AI_HTTP_REFERER", ("ai", "http_referer")) or get_str(
        "OPENROUTER_HTTP_REFERER", ("openrouter", "http_referer")
    )
    x_title = get_str("AI_APP_NAME", ("ai", "app_name")) or get_str(
        "OPENROUTER_X_TITLE", ("openrouter", "x_title")
    )
    
    # --- Brain behavior ---
    min_confidence = get_float("BRAIN_MIN_CONFIDENCE", ("brain", "min_confidence"), 0.35)
    max_rationale_chars = get_int("BRAIN_MAX_RATIONALE_CHARS", ("brain", "max_rationale_chars"), 400)
    max_list_items = get_int("BRAIN_MAX_LIST_ITEMS", ("brain", "max_list_items"), 50)
    response_format_json = get_bool("BRAIN_RESPONSE_FORMAT_JSON", ("brain", "response_format_json"), True)
    
    return BrainConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider,
        timeout_s=timeout_s,
        max_retries=max_retries,
        backoff_s=backoff_s,
        http_referer=http_referer,
        x_title=x_title,
        min_confidence=min_confidence,
        max_rationale_chars=max_rationale_chars,
        max_list_items=max_list_items,
        response_format_json=response_format_json,
    )
