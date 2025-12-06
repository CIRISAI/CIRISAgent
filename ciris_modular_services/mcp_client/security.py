"""
MCP Security Module.

Implements security measures to protect against malicious MCP servers:
- Tool poisoning detection
- Input/output validation
- Rate limiting
- Permission enforcement
- Hidden instruction detection

Based on security research from:
- https://modelcontextprotocol.io/specification/draft/basic/security_best_practices
- https://www.redhat.com/en/blog/model-context-protocol-mcp-understanding-security-risks-and-controls
- https://www.pillar.security/blog/the-security-risks-of-model-context-protocol-mcp
"""

import asyncio
import hashlib
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from .config import MCPSecurityConfig, MCPServerConfig

logger = logging.getLogger(__name__)


class SecurityViolationType(str, Enum):
    """Types of security violations."""

    TOOL_POISONING = "tool_poisoning"  # Malicious instructions in tool description
    HIDDEN_INSTRUCTION = "hidden_instruction"  # Hidden instructions detected
    INPUT_TOO_LARGE = "input_too_large"  # Input exceeds size limit
    OUTPUT_TOO_LARGE = "output_too_large"  # Output exceeds size limit
    BLOCKED_TOOL = "blocked_tool"  # Tool is on blocklist
    UNAUTHORIZED_TOOL = "unauthorized_tool"  # Tool not on allowlist
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"  # Too many calls
    PERMISSION_DENIED = "permission_denied"  # Permission level insufficient
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"  # Input/output schema mismatch
    VERSION_MISMATCH = "version_mismatch"  # Server version changed unexpectedly
    SUSPICIOUS_PATTERN = "suspicious_pattern"  # Suspicious content pattern detected


@dataclass
class SecurityViolation:
    """Record of a security violation."""

    violation_type: SecurityViolationType
    server_id: str
    tool_name: Optional[str]
    description: str
    severity: str  # "low", "medium", "high", "critical"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Dict[str, Any] = field(default_factory=dict)
    blocked: bool = True  # Whether the operation was blocked


class SecurityEvent(BaseModel):
    """Security event for logging and monitoring."""

    event_type: str = Field(..., description="Type of security event")
    server_id: str = Field(..., description="Server that triggered the event")
    tool_name: Optional[str] = Field(None, description="Tool involved if applicable")
    description: str = Field(..., description="Event description")
    severity: str = Field("medium", description="Event severity")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event time")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")

    model_config = ConfigDict(extra="forbid")


class RateLimiter:
    """Token bucket rate limiter for MCP operations."""

    def __init__(self, max_calls_per_minute: int, max_concurrent: int) -> None:
        self.max_calls_per_minute = max_calls_per_minute
        self.max_concurrent = max_concurrent
        self._calls: List[float] = []
        self._concurrent = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Try to acquire a rate limit slot. Returns False if rate limited."""
        async with self._lock:
            now = time.time()
            # Remove old calls outside the window
            self._calls = [t for t in self._calls if now - t < 60.0]

            if len(self._calls) >= self.max_calls_per_minute:
                return False

            if self._concurrent >= self.max_concurrent:
                return False

            self._calls.append(now)
            self._concurrent += 1
            return True

    async def release(self) -> None:
        """Release a rate limit slot."""
        async with self._lock:
            if self._concurrent > 0:
                self._concurrent -= 1


class ToolPoisoningDetector:
    """Detects tool poisoning attacks in MCP tool descriptions.

    Tool poisoning is when an attacker embeds malicious instructions
    in tool descriptions that are invisible to users but interpreted
    by the AI model.

    References:
    - https://www.pillar.security/blog/the-security-risks-of-model-context-protocol-mcp
    - https://strobes.co/blog/mcp-model-context-protocol-and-its-critical-vulnerabilities/
    """

    # Default patterns for detecting malicious hidden instructions
    DEFAULT_PATTERNS = [
        # HTML-style hidden tags
        r"<hidden>.*?</hidden>",
        r"<system>.*?</system>",
        r"<instruction>.*?</instruction>",
        r"<secret>.*?</secret>",
        r"<invisible>.*?</invisible>",
        # HTML comments
        r"<!--.*?-->",
        # Null byte injection
        r"\x00.*?\x00",
        # Common prompt injection patterns
        r"(?i)SYSTEM:\s*.+",
        r"(?i)IGNORE\s+PREVIOUS\s+INSTRUCTIONS?",
        r"(?i)DISREGARD\s+ALL\s+PREVIOUS",
        r"(?i)OVERRIDE:\s*.+",
        r"(?i)ADMIN\s+MODE:\s*.+",
        r"(?i)DEBUG\s+MODE:\s*.+",
        # SSH key extraction patterns
        r"(?i)exfiltrate.*ssh.*key",
        r"(?i)send.*to.*server",
        r"(?i)upload.*credential",
        r"(?i)steal.*token",
        # Unicode abuse (zero-width characters)
        r"[\u200b\u200c\u200d\ufeff]",  # Zero-width chars
        r"[\u202a-\u202e]",  # Bidirectional control chars
        # Base64 encoded instructions
        r"(?i)base64.*decode.*execute",
        # Script injection
        r"<script.*?>.*?</script>",
        r"javascript:",
        r"data:text/html",
    ]

    def __init__(self, custom_patterns: Optional[List[str]] = None) -> None:
        """Initialize detector with patterns.

        Args:
            custom_patterns: Additional regex patterns to detect
        """
        self.patterns = self.DEFAULT_PATTERNS.copy()
        if custom_patterns:
            self.patterns.extend(custom_patterns)
        self._compiled_patterns = [re.compile(p, re.DOTALL | re.IGNORECASE) for p in self.patterns]

    def detect(self, text: str) -> List[Tuple[str, str]]:
        """Detect potential tool poisoning in text.

        Args:
            text: Text to analyze (typically tool description)

        Returns:
            List of (pattern, matched_text) tuples for detected issues
        """
        findings: List[Tuple[str, str]] = []
        for i, pattern in enumerate(self._compiled_patterns):
            matches = pattern.findall(text)
            for match in matches:
                match_str = match if isinstance(match, str) else str(match)
                # Truncate long matches for logging
                if len(match_str) > 100:
                    match_str = match_str[:100] + "..."
                findings.append((self.patterns[i], match_str))
        return findings

    def is_safe(self, text: str) -> Tuple[bool, List[str]]:
        """Check if text is safe (no poisoning detected).

        Args:
            text: Text to check

        Returns:
            (is_safe, list of reason strings)
        """
        findings = self.detect(text)
        if not findings:
            return True, []
        reasons = [f"Pattern '{p}' matched: {m}" for p, m in findings]
        return False, reasons


class InputValidator:
    """Validates inputs and outputs for MCP operations."""

    def __init__(self, config: MCPSecurityConfig) -> None:
        self.config = config
        self.poisoning_detector = ToolPoisoningDetector(config.hidden_instruction_patterns)

    def validate_input_size(self, data: Any) -> Tuple[bool, Optional[str]]:
        """Validate input data size."""
        import json

        try:
            size = len(json.dumps(data).encode("utf-8"))
            if size > self.config.max_input_size_bytes:
                return False, f"Input size {size} exceeds limit {self.config.max_input_size_bytes}"
            return True, None
        except (TypeError, ValueError) as e:
            return False, f"Failed to serialize input: {e}"

    def validate_output_size(self, data: Any) -> Tuple[bool, Optional[str]]:
        """Validate output data size."""
        import json

        try:
            size = len(json.dumps(data).encode("utf-8"))
            if size > self.config.max_output_size_bytes:
                return False, f"Output size {size} exceeds limit {self.config.max_output_size_bytes}"
            return True, None
        except (TypeError, ValueError) as e:
            return False, f"Failed to serialize output: {e}"

    def validate_tool_description(self, description: str) -> Tuple[bool, List[str]]:
        """Validate a tool description for poisoning attempts."""
        if not self.config.detect_tool_poisoning:
            return True, []
        return self.poisoning_detector.is_safe(description)


class MCPSecurityManager:
    """
    Central security manager for MCP operations.

    Provides comprehensive security controls including:
    - Tool allowlist/blocklist enforcement
    - Rate limiting per server
    - Tool poisoning detection
    - Input/output validation
    - Version change detection
    - Permission enforcement
    """

    def __init__(self, global_config: MCPSecurityConfig) -> None:
        """Initialize security manager.

        Args:
            global_config: Global security configuration
        """
        self.global_config = global_config
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._server_configs: Dict[str, MCPSecurityConfig] = {}
        self._server_versions: Dict[str, str] = {}
        self._tool_hashes: Dict[str, Dict[str, str]] = defaultdict(dict)  # server_id -> {tool_name -> hash}
        self._violations: List[SecurityViolation] = []
        self._lock = asyncio.Lock()

    def register_server(self, server_config: MCPServerConfig) -> None:
        """Register a server for security management."""
        server_id = server_config.server_id
        security = server_config.security

        # Merge with global config (server-specific overrides)
        effective_security = MCPSecurityConfig(
            pin_version=security.pin_version or self.global_config.pin_version,
            allow_version_updates=security.allow_version_updates,
            permission_level=security.permission_level,
            allowed_tools=security.allowed_tools or self.global_config.allowed_tools,
            blocked_tools=list(set(security.blocked_tools + self.global_config.blocked_tools)),
            validate_inputs=security.validate_inputs and self.global_config.validate_inputs,
            validate_outputs=security.validate_outputs and self.global_config.validate_outputs,
            max_input_size_bytes=min(security.max_input_size_bytes, self.global_config.max_input_size_bytes),
            max_output_size_bytes=min(security.max_output_size_bytes, self.global_config.max_output_size_bytes),
            detect_tool_poisoning=security.detect_tool_poisoning and self.global_config.detect_tool_poisoning,
            max_calls_per_minute=min(security.max_calls_per_minute, self.global_config.max_calls_per_minute),
            max_concurrent_calls=min(security.max_concurrent_calls, self.global_config.max_concurrent_calls),
            sandbox_enabled=security.sandbox_enabled or self.global_config.sandbox_enabled,
        )

        self._server_configs[server_id] = effective_security

        # Create rate limiter for this server
        self._rate_limiters[server_id] = RateLimiter(
            effective_security.max_calls_per_minute,
            effective_security.max_concurrent_calls,
        )

        logger.info(f"Registered MCP server '{server_id}' with security controls")

    async def check_tool_access(
        self, server_id: str, tool_name: str, tool_description: str
    ) -> Tuple[bool, Optional[SecurityViolation]]:
        """Check if access to a tool is allowed.

        Args:
            server_id: Server providing the tool
            tool_name: Name of the tool
            tool_description: Tool description (checked for poisoning)

        Returns:
            (allowed, violation) - violation is None if allowed
        """
        config = self._server_configs.get(server_id, self.global_config)

        # Check blocklist first
        if tool_name in config.blocked_tools:
            violation = SecurityViolation(
                violation_type=SecurityViolationType.BLOCKED_TOOL,
                server_id=server_id,
                tool_name=tool_name,
                description=f"Tool '{tool_name}' is on the blocklist",
                severity="high",
            )
            await self._record_violation(violation)
            return False, violation

        # Check allowlist if specified
        if config.allowed_tools and tool_name not in config.allowed_tools:
            violation = SecurityViolation(
                violation_type=SecurityViolationType.UNAUTHORIZED_TOOL,
                server_id=server_id,
                tool_name=tool_name,
                description=f"Tool '{tool_name}' is not on the allowlist",
                severity="medium",
            )
            await self._record_violation(violation)
            return False, violation

        # Check for tool poisoning
        if config.detect_tool_poisoning:
            validator = InputValidator(config)
            is_safe, reasons = validator.validate_tool_description(tool_description)
            if not is_safe:
                violation = SecurityViolation(
                    violation_type=SecurityViolationType.TOOL_POISONING,
                    server_id=server_id,
                    tool_name=tool_name,
                    description=f"Tool poisoning detected: {'; '.join(reasons)}",
                    severity="critical",
                    context={"reasons": reasons},
                )
                await self._record_violation(violation)
                return False, violation

        # Check for tool description changes (detect updates that may be malicious)
        desc_hash = hashlib.sha256(tool_description.encode()).hexdigest()
        if tool_name in self._tool_hashes[server_id]:
            if self._tool_hashes[server_id][tool_name] != desc_hash:
                logger.warning(
                    f"Tool '{tool_name}' description changed for server '{server_id}'. "
                    "This may indicate a malicious update."
                )
                # Don't block, but log the change
                event = SecurityEvent(
                    event_type="tool_description_changed",
                    server_id=server_id,
                    tool_name=tool_name,
                    description="Tool description changed since last seen",
                    severity="medium",
                    context={"old_hash": self._tool_hashes[server_id][tool_name], "new_hash": desc_hash},
                )
                logger.info(f"Security event: {event.model_dump_json()}")

        self._tool_hashes[server_id][tool_name] = desc_hash
        return True, None

    async def check_rate_limit(self, server_id: str) -> Tuple[bool, Optional[SecurityViolation]]:
        """Check if operation is within rate limits.

        Args:
            server_id: Server to check rate limit for

        Returns:
            (allowed, violation)
        """
        rate_limiter = self._rate_limiters.get(server_id)
        if not rate_limiter:
            # No rate limiter configured, allow
            return True, None

        allowed = await rate_limiter.acquire()
        if not allowed:
            violation = SecurityViolation(
                violation_type=SecurityViolationType.RATE_LIMIT_EXCEEDED,
                server_id=server_id,
                tool_name=None,
                description="Rate limit exceeded for server",
                severity="medium",
            )
            await self._record_violation(violation)
            return False, violation

        return True, None

    async def release_rate_limit(self, server_id: str) -> None:
        """Release rate limit slot after operation completes."""
        rate_limiter = self._rate_limiters.get(server_id)
        if rate_limiter:
            await rate_limiter.release()

    async def validate_input(
        self, server_id: str, tool_name: str, parameters: Any
    ) -> Tuple[bool, Optional[SecurityViolation]]:
        """Validate input parameters.

        Args:
            server_id: Server ID
            tool_name: Tool being called
            parameters: Input parameters

        Returns:
            (valid, violation)
        """
        config = self._server_configs.get(server_id, self.global_config)

        if not config.validate_inputs:
            return True, None

        validator = InputValidator(config)
        is_valid, error = validator.validate_input_size(parameters)

        if not is_valid:
            violation = SecurityViolation(
                violation_type=SecurityViolationType.INPUT_TOO_LARGE,
                server_id=server_id,
                tool_name=tool_name,
                description=error or "Input validation failed",
                severity="medium",
            )
            await self._record_violation(violation)
            return False, violation

        return True, None

    async def validate_output(
        self, server_id: str, tool_name: str, result: Any
    ) -> Tuple[bool, Optional[SecurityViolation]]:
        """Validate output result.

        Args:
            server_id: Server ID
            tool_name: Tool that produced the output
            result: Output result

        Returns:
            (valid, violation)
        """
        config = self._server_configs.get(server_id, self.global_config)

        if not config.validate_outputs:
            return True, None

        validator = InputValidator(config)
        is_valid, error = validator.validate_output_size(result)

        if not is_valid:
            violation = SecurityViolation(
                violation_type=SecurityViolationType.OUTPUT_TOO_LARGE,
                server_id=server_id,
                tool_name=tool_name,
                description=error or "Output validation failed",
                severity="medium",
            )
            await self._record_violation(violation)
            return False, violation

        return True, None

    async def check_version(self, server_id: str, current_version: str) -> Tuple[bool, Optional[SecurityViolation]]:
        """Check server version against pinned version.

        Args:
            server_id: Server to check
            current_version: Current server version

        Returns:
            (allowed, violation)
        """
        config = self._server_configs.get(server_id, self.global_config)

        # Check pinned version
        if config.pin_version and config.pin_version != current_version:
            if not config.allow_version_updates:
                violation = SecurityViolation(
                    violation_type=SecurityViolationType.VERSION_MISMATCH,
                    server_id=server_id,
                    tool_name=None,
                    description=(f"Server version mismatch: expected {config.pin_version}, got {current_version}"),
                    severity="high",
                    context={"expected": config.pin_version, "actual": current_version},
                )
                await self._record_violation(violation)
                return False, violation
            else:
                # Log the version change but allow
                logger.warning(
                    f"MCP server '{server_id}' version changed from {config.pin_version} to {current_version}"
                )

        # Track version for future checks
        if server_id in self._server_versions:
            if self._server_versions[server_id] != current_version:
                logger.info(
                    f"MCP server '{server_id}' version updated: "
                    f"{self._server_versions[server_id]} -> {current_version}"
                )

        self._server_versions[server_id] = current_version
        return True, None

    async def _record_violation(self, violation: SecurityViolation) -> None:
        """Record a security violation."""
        async with self._lock:
            self._violations.append(violation)
            # Keep only last 1000 violations
            if len(self._violations) > 1000:
                self._violations = self._violations[-1000:]

        # Log the violation
        log_method = (
            logger.critical
            if violation.severity == "critical"
            else (
                logger.error
                if violation.severity == "high"
                else (logger.warning if violation.severity == "medium" else logger.info)
            )
        )
        log_method(
            f"MCP Security Violation [{violation.violation_type.value}] "
            f"server={violation.server_id} tool={violation.tool_name}: {violation.description}"
        )

    def get_violations(
        self, server_id: Optional[str] = None, since: Optional[datetime] = None
    ) -> List[SecurityViolation]:
        """Get recorded security violations.

        Args:
            server_id: Filter by server ID
            since: Filter violations after this time

        Returns:
            List of violations matching criteria
        """
        violations = self._violations.copy()
        if server_id:
            violations = [v for v in violations if v.server_id == server_id]
        if since:
            violations = [v for v in violations if v.timestamp >= since]
        return violations

    def get_security_metrics(self) -> Dict[str, Any]:
        """Get security metrics for telemetry."""
        return {
            "total_violations": len(self._violations),
            "violations_by_type": {
                vtype.value: len([v for v in self._violations if v.violation_type == vtype])
                for vtype in SecurityViolationType
            },
            "violations_by_severity": {
                sev: len([v for v in self._violations if v.severity == sev])
                for sev in ["low", "medium", "high", "critical"]
            },
            "servers_monitored": len(self._server_configs),
            "tool_hashes_tracked": sum(len(hashes) for hashes in self._tool_hashes.values()),
        }


__all__ = [
    "SecurityViolationType",
    "SecurityViolation",
    "SecurityEvent",
    "RateLimiter",
    "ToolPoisoningDetector",
    "InputValidator",
    "MCPSecurityManager",
]
