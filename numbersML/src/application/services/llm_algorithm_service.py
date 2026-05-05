"""
LLM Algorithm Service - AI-assisted algorithm configuration generation.

Provides safe, guardrailed LLM integration for:
- Generating algorithm configs from natural language
- Modifying existing configs based on change requests
- Suggesting improvements from backtest results

Safety features:
- Prompt injection detection
- JSON schema validation
- Business rule validation
- Audit logging of all LLM interactions
- Never auto-activates generated configs
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from src.domain.repositories.algorithm_repository import AlgorithmRepository
from src.domain.algorithms.config_schema import ValidationIssue, validate_algorithm_config
from src.domain.algorithms.algorithm_config import AlgorithmDefinition

logger = logging.getLogger(__name__)

# Try to import OpenAI
try:
    import openai
    from openai import AsyncOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI package not installed. LLM features will be disabled.")


@dataclass(frozen=True)
class LLMGenerationResult:
    """Result of LLM config generation."""

    success: bool
    config: dict[str, Any] | None
    issues: list[ValidationIssue]
    raw_response: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error_message: str | None = None


@dataclass(frozen=True)
class LLMSuggestionResult:
    """Result of LLM improvement suggestion."""

    success: bool
    suggestions: str
    suggested_config: dict[str, Any] | None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error_message: str | None = None


class LLMAlgorithmService:
    """
    LLM-assisted algorithm configuration service.

    Responsibilities:
    1. Generate algorithm configs from natural language descriptions
    2. Modify existing configs based on change requests
    3. Suggest improvements from backtest performance
    4. Enforce safety through validation and guardrails
    5. Never auto-activate - always save as draft
    """

    # Prompt injection patterns to detect and block
    _INJECTION_PATTERNS = [
        r"ignore previous instructions",
        r"ignore all instructions",
        r"disregard.*instructions",
        r"forget.*prompt",
        r"system prompt",
        r"you are now.*",
        r"new role.*",
        r"act as.*ignore",
        r"DAN mode",
        r"jailbreak",
        r"""begin.*IGNORE.*end""",
    ]

    # Maximum allowed tokens for safety
    _MAX_INPUT_TOKENS = 2000
    _MAX_OUTPUT_TOKENS = 1500

    def __init__(
        self,
        algorithm_repository: AlgorithmRepository,
        api_key: Optional[str] = None,
        model: str = "gpt-4",
    ) -> None:
        """
        Initialize LLM algorithm service.

        Args:
            algorithm_repository: Repository for saving generated algorithms
            api_key: OpenAI API key (or from OPENAI_API_KEY env var)
            model: LLM model to use
        """
        self._repository = algorithm_repository
        self._model = model
        self._client: Optional[AsyncOpenAI] = None

        if OPENAI_AVAILABLE:
            key = api_key or os.getenv("OPENAI_API_KEY")
            if key:
                self._client = AsyncOpenAI(api_key=key)
                logger.info(f"LLMAlgorithmService initialized with model {model}")
            else:
                logger.warning("OpenAI API key not provided. LLM features disabled.")
        else:
            logger.warning("OpenAI package not available. LLM features disabled.")

    async def generate_config(
        self,
        description: str,
        symbols: list[str],
        timeframe: str = "1M",
        mode: str = "paper",
        created_by: str = "llm",
    ) -> LLMGenerationResult:
        """
        Generate algorithm configuration from natural language description.

        Args:
            description: Natural language algorithm description
            symbols: Trading symbols to include
            timeframe: Candle timeframe (TICK, 1S, 1M, 5M, 15M, 1H, 4H, 1D)
            mode: Trading mode (paper/live)
            created_by: Actor identifier for audit

        Returns:
            LLMGenerationResult with generated config or error details
        """
        # Guardrail 1: Prompt injection check
        injection_check = self._detect_prompt_injection(description)
        if injection_check:
            logger.warning(f"Prompt injection detected: {injection_check}")
            return LLMGenerationResult(
                success=False,
                config=None,
                issues=[
                    ValidationIssue(path="input", message=f"Security violation: {injection_check}")
                ],
                raw_response="",
                error_message=f"Input rejected: {injection_check}",
            )

        # Guardrail 2: Input size limit
        if len(description) > self._MAX_INPUT_TOKENS * 4:  # Rough chars to tokens estimate
            return LLMGenerationResult(
                success=False,
                config=None,
                issues=[ValidationIssue(path="input", message="Description too long")],
                raw_response="",
                error_message="Description exceeds maximum length",
            )

        if not self._client:
            return LLMGenerationResult(
                success=False,
                config=None,
                issues=[ValidationIssue(path="system", message="LLM not configured")],
                raw_response="",
                error_message="LLM service not available. Check OPENAI_API_KEY.",
            )

        try:
            # Build prompt with schema context
            prompt = self._build_generation_prompt(description, symbols, timeframe, mode)

            # Call LLM
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a trading algorithm configuration expert. "
                            "Generate valid JSON algorithm configurations only. "
                            "No explanations, markdown, or comments. "
                            "Output must be valid JSON matching the provided schema exactly."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=self._MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},  # Enforce JSON output
            )

            raw_response = response.choices[0].message.content or "{}"
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0

            # Parse and validate
            try:
                config = json.loads(raw_response)
            except json.JSONDecodeError as e:
                logger.error(f"LLM returned invalid JSON: {e}")
                return LLMGenerationResult(
                    success=False,
                    config=None,
                    issues=[ValidationIssue(path="llm", message="Invalid JSON response")],
                    raw_response=raw_response,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_message="LLM returned invalid JSON",
                )

            # Guardrail 3: Schema validation
            is_valid, issues = validate_algorithm_config(config)

            if not is_valid:
                logger.warning(f"Generated config failed validation: {issues}")
                return LLMGenerationResult(
                    success=False,
                    config=config,
                    issues=issues,
                    raw_response=raw_response,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_message="Generated config failed validation",
                )

            # Success
            logger.info(
                f"Generated valid config for algorithm: {config.get('meta', {}).get('name', 'unnamed')}"
            )
            return LLMGenerationResult(
                success=True,
                config=config,
                issues=[],
                raw_response=raw_response,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            return LLMGenerationResult(
                success=False,
                config=None,
                issues=[ValidationIssue(path="system", message=str(e))],
                raw_response="",
                error_message=f"LLM generation failed: {str(e)}",
            )

    async def modify_config(
        self,
        existing_config: dict[str, Any],
        change_request: str,
        modified_by: str = "llm",
    ) -> LLMGenerationResult:
        """
        Modify existing algorithm config based on change request.

        Args:
            existing_config: Current algorithm configuration
            change_request: Natural language change description
            modified_by: Actor identifier for audit

        Returns:
            LLMGenerationResult with modified config
        """
        # Guardrail 1: Prompt injection check
        injection_check = self._detect_prompt_injection(change_request)
        if injection_check:
            return LLMGenerationResult(
                success=False,
                config=None,
                issues=[
                    ValidationIssue(path="input", message=f"Security violation: {injection_check}")
                ],
                raw_response="",
                error_message=f"Input rejected: {injection_check}",
            )

        if not self._client:
            return LLMGenerationResult(
                success=False,
                config=None,
                issues=[ValidationIssue(path="system", message="LLM not configured")],
                raw_response="",
                error_message="LLM service not available",
            )

        try:
            # Build modification prompt
            prompt = self._build_modification_prompt(existing_config, change_request)

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a trading algorithm configuration expert. "
                            "Modify the provided algorithm config based on the user's request. "
                            "Return valid JSON only. Preserve all fields not being modified. "
                            "Never change mode from paper to live without explicit confirmation."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=self._MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
            )

            raw_response = response.choices[0].message.content or "{}"
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0

            # Parse and validate
            try:
                config = json.loads(raw_response)
            except json.JSONDecodeError:
                return LLMGenerationResult(
                    success=False,
                    config=None,
                    issues=[ValidationIssue(path="llm", message="Invalid JSON response")],
                    raw_response=raw_response,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_message="LLM returned invalid JSON",
                )

            # Guardrail: Check for forbidden field changes
            issues = self._check_forbidden_changes(existing_config, config, change_request)
            if issues:
                return LLMGenerationResult(
                    success=False,
                    config=config,
                    issues=issues,
                    raw_response=raw_response,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_message="Changes require explicit approval",
                )

            # Schema validation
            is_valid, validation_issues = validate_algorithm_config(config)
            issues.extend(validation_issues)

            if not is_valid:
                return LLMGenerationResult(
                    success=False,
                    config=config,
                    issues=issues,
                    raw_response=raw_response,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_message="Modified config failed validation",
                )

            return LLMGenerationResult(
                success=True,
                config=config,
                issues=[],
                raw_response=raw_response,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except Exception as e:
            logger.error(f"LLM modification failed: {e}", exc_info=True)
            return LLMGenerationResult(
                success=False,
                config=None,
                issues=[ValidationIssue(path="system", message=str(e))],
                raw_response="",
                error_message=f"LLM modification failed: {str(e)}",
            )

    async def suggest_improvements(
        self,
        algorithm_config: dict[str, Any],
        backtest_metrics: dict[str, Any],
    ) -> LLMSuggestionResult:
        """
        Suggest algorithm improvements based on backtest performance.

        Args:
            algorithm_config: Current algorithm configuration
            backtest_metrics: Performance metrics from backtest

        Returns:
            LLMSuggestionResult with natural language suggestions
        """
        if not self._client:
            return LLMSuggestionResult(
                success=False,
                suggestions="",
                suggested_config=None,
                error_message="LLM service not available",
            )

        try:
            prompt = self._build_suggestion_prompt(algorithm_config, backtest_metrics)

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a quantitative trading analyst. "
                            "Provide concise, actionable recommendations for algorithm improvement. "
                            "Be specific about parameter adjustments. "
                            "Return plain text, not JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=800,
            )

            suggestions = response.choices[0].message.content or ""
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0

            return LLMSuggestionResult(
                success=True,
                suggestions=suggestions,
                suggested_config=None,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except Exception as e:
            logger.error(f"LLM suggestion failed: {e}", exc_info=True)
            return LLMSuggestionResult(
                success=False,
                suggestions="",
                suggested_config=None,
                error_message=f"Failed to generate suggestions: {str(e)}",
            )

    async def save_generated_algorithm(
        self,
        config: dict[str, Any],
        created_by: str = "llm",
    ) -> AlgorithmDefinition:
        """
        Save LLM-generated config as a new draft algorithm.

        Args:
            config: Validated algorithm configuration
            created_by: Actor identifier

        Returns:
            Created AlgorithmDefinition (always as draft)
        """
        # Force status to draft - never auto-activate
        config["status"] = "draft"
        config["mode"] = config.get("mode", "paper")

        meta = config.get("meta", {})

        algorithm_def = AlgorithmDefinition(
            name=meta.get("name", "Untitled LLM Algorithm"),
            description=meta.get("description", "Generated by LLM"),
            mode=config.get("mode", "paper"),
            status="draft",
            current_version=1,
            created_by=created_by,
        )

        # Save to repository
        saved = await self._repository.save(algorithm_def)

        # Save first version with config
        await self._repository.create_version(
            algorithm_id=saved.id,
            config=config,
            schema_version=1,
            created_by=created_by,
        )

        logger.info(f"Saved LLM-generated algorithm as draft: {saved.id}")
        return saved

    def _detect_prompt_injection(self, text: str) -> Optional[str]:
        """Detect potential prompt injection attempts."""
        text_lower = text.lower()
        for pattern in self._INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return f"Detected pattern: {pattern}"
        return None

    def _check_forbidden_changes(
        self,
        old_config: dict[str, Any],
        new_config: dict[str, Any],
        change_request: str,
    ) -> list[ValidationIssue]:
        """Check for changes that require explicit approval."""
        issues: list[ValidationIssue] = []

        # Check for mode change to live
        old_mode = old_config.get("mode", "paper")
        new_mode = new_config.get("mode", "paper")
        if old_mode == "paper" and new_mode == "live":
            # Only allow if change request explicitly mentions "live"
            if "live" not in change_request.lower():
                issues.append(
                    ValidationIssue(
                        path="mode",
                        message="Mode change to live requires explicit user confirmation",
                    )
                )

        # Check for large risk limit increases
        old_risk = old_config.get("risk", {})
        new_risk = new_config.get("risk", {})

        old_max_pos = old_risk.get("max_position_size_pct", 10)
        new_max_pos = new_risk.get("max_position_size_pct", 10)
        if new_max_pos > old_max_pos * 2:
            issues.append(
                ValidationIssue(
                    path="risk.max_position_size_pct",
                    message=f"Position size increase from {old_max_pos}% to {new_max_pos}% requires approval",
                )
            )

        return issues

    def _build_generation_prompt(
        self,
        description: str,
        symbols: list[str],
        timeframe: str,
        mode: str,
    ) -> str:
        """Build prompt for algorithm generation."""
        return f"""Generate a trading algorithm configuration based on the following description.

Description: {description}

Required settings:
- Symbols: {json.dumps(symbols)}
- Timeframe: {timeframe}
- Mode: {mode}
- Status: draft

Output must be valid JSON matching this exact structure:
{{
  "meta": {{
    "name": "Algorithm name",
    "description": "Brief description",
    "schema_version": 1
  }},
  "universe": {{
    "symbols": {json.dumps(symbols)},
    "timeframe": "{timeframe}"
  }},
  "signal": {{
    "type": "rsi|macd|sma_cross|bollinger|composite",
    "params": {{}}
  }},
  "risk": {{
    "max_position_size_pct": 10,
    "max_daily_loss_pct": 5,
    "stop_loss_pct": 2,
    "take_profit_pct": 4
  }},
  "execution": {{
    "order_type": "market|limit",
    "slippage_bps": 10,
    "fee_bps": 10
  }},
  "mode": "{mode}",
  "status": "draft"
}}

Signal type parameters:
- rsi: {{"period": 14, "oversold": 30, "overbought": 70}}
- macd: {{"fast": 12, "slow": 26, "signal": 9}}
- sma_cross: {{"fast": 20, "slow": 50}}
- bollinger: {{"period": 20, "std_dev": 2.0}}

Output JSON only, no markdown, no explanations."""

    def _build_modification_prompt(
        self,
        existing_config: dict[str, Any],
        change_request: str,
    ) -> str:
        """Build prompt for config modification."""
        return f"""Modify the following algorithm configuration based on the user's request.

Current configuration:
{json.dumps(existing_config, indent=2)}

User request: {change_request}

Rules:
1. Preserve all fields not being modified
2. Maintain valid JSON structure
3. Never change mode from paper to live unless explicitly requested
4. Keep status as draft
5. Output JSON only

Output the complete modified configuration as JSON:"""

    def _build_suggestion_prompt(
        self,
        algorithm_config: dict[str, Any],
        backtest_metrics: dict[str, Any],
    ) -> str:
        """Build prompt for improvement suggestions."""
        return f"""Analyze this algorithm's backtest performance and suggest improvements.

Algorithm Configuration:
{json.dumps(algorithm_config, indent=2)}

Backtest Metrics:
{json.dumps(backtest_metrics, indent=2)}

Provide 2-3 specific, actionable recommendations:
1. Which parameters to adjust and why
2. What risk settings to modify
3. Any signal logic improvements

Be specific with suggested values. Keep recommendations concise and practical."""
