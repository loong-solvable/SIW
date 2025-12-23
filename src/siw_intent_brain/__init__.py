"""
SIW Intent Brain - Local-first decision support intent scoring engine.

Public exports:
- IntentBrain: Main scoring API
- BrainConfig: Configuration dataclass
- LeadCard: Output type (TypedDict)
- validate_lead_card: Contract validator
- Error types and codes
"""

__version__ = "0.1.0"

from .contracts import (
    LEAD_TIERS,
    NEXT_STEPS,
    PARSER_MODES,
    SCHEMA_VERSION,
    ExtractedSignals,
    LeadCard,
    LeadTier,
    Meta,
    ParserMode,
    RecommendedNextStep,
    Scores,
    build_lead_card,
    default_extracted_signals,
    default_scores,
    validate_lead_card,
)

from .config import BrainConfig, load_config

from .errors import (
    ConfigError,
    ContractError,
    E_CONFIG_MISSING_KEY,
    E_CONTRACT_INVALID,
    E_PARSE_JSON,
    E_UPSTREAM_EMPTY_CONTENT,
    E_UPSTREAM_HTTP,
    E_UPSTREAM_TIMEOUT,
    ErrorInfo,
    ParseError,
    SIWError,
    UpstreamError,
)

from .brain import IntentBrain

__all__ = [
    "__version__",
    # Main API
    "IntentBrain",
    # Types
    "LeadCard",
    "Scores",
    "ExtractedSignals",
    "Meta",
    "LeadTier",
    "RecommendedNextStep",
    "ParserMode",
    # Constants
    "SCHEMA_VERSION",
    "LEAD_TIERS",
    "NEXT_STEPS",
    "PARSER_MODES",
    # Functions
    "default_scores",
    "default_extracted_signals",
    "build_lead_card",
    "validate_lead_card",
    # Config
    "BrainConfig",
    "load_config",
    # Errors
    "SIWError",
    "ConfigError",
    "UpstreamError",
    "ParseError",
    "ContractError",
    "ErrorInfo",
    # Error codes
    "E_CONFIG_MISSING_KEY",
    "E_UPSTREAM_HTTP",
    "E_UPSTREAM_TIMEOUT",
    "E_UPSTREAM_EMPTY_CONTENT",
    "E_PARSE_JSON",
    "E_CONTRACT_INVALID",
]
