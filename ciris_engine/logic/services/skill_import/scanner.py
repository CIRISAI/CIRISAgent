"""Skill Security Scanner.

Scans imported OpenClaw skills for known attack patterns from the
ClawHub security crisis (Feb 2026). Based on findings from:

- Snyk ToxicSkills audit: 1,467 malicious skills, 36% with prompt injection
- Koi Security ClawHavoc campaign: 335 skills delivering AMOS stealer
- CVE-2026-25593, CVE-2026-24763, CVE-2026-25157 and related

Threat categories:
1. Prompt injection in instructions (indirect manipulation of agent reasoning)
2. Credential exfiltration (env vars, API keys, SSH keys, browser data)
3. Reverse shell / backdoor installation
4. Cryptominer deployment
5. Typosquatting on popular skill names
6. Undeclared network access (curl/wget in scripts not declared in requires)
7. File system access beyond declared scope
8. Time-shifted / logic bomb activation patterns

Each check returns a SkillSecurityFinding with severity and explanation
in plain English so non-technical users can understand the risk.
"""

import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .parser import ParsedSkill

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    """Finding severity levels."""

    CRITICAL = "critical"  # Immediate danger - do not install
    HIGH = "high"  # Likely malicious - review carefully
    MEDIUM = "medium"  # Suspicious pattern - investigate
    LOW = "low"  # Minor concern - be aware
    INFO = "info"  # Informational - no action needed


class SkillSecurityFinding(BaseModel):
    """A single security finding from scanning a skill."""

    severity: Severity = Field(..., description="How serious is this?")
    category: str = Field(..., description="Type of issue found")
    title: str = Field(..., description="Short title (plain English)")
    description: str = Field(..., description="What we found (plain English)")
    evidence: Optional[str] = Field(None, description="The specific text that triggered this finding")
    recommendation: str = Field("", description="What should you do?")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class SkillSecurityReport(BaseModel):
    """Complete security scan report for a skill."""

    skill_name: str
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    findings: List[SkillSecurityFinding] = Field(default_factory=list)
    safe_to_import: bool = Field(True, description="Overall recommendation")
    summary: str = Field("", description="Plain English summary")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# Pattern Databases (from real ClawHub malware analysis)
# ============================================================================

# Prompt injection patterns - phrases that manipulate agent reasoning
_PROMPT_INJECTION_PATTERNS = [
    # Direct instruction override
    (r"ignore\s+(all\s+)?previous\s+instructions", "Attempts to override agent's core instructions"),
    (r"disregard\s+(all\s+)?prior\s+(instructions|rules|guidelines)", "Attempts to disregard safety rules"),
    (r"you\s+are\s+now\s+(a|an)\s+", "Tries to reassign agent identity"),
    (r"forget\s+(everything|all)\s+(you|about)", "Attempts to wipe agent memory"),
    (r"system\s*:\s*you\s+are", "Fake system prompt injection"),
    # Indirect manipulation
    (r"do\s+not\s+(tell|inform|alert|notify)\s+(the\s+)?user", "Hides actions from user"),
    (r"silently|without\s+(the\s+)?user\s+knowing", "Conceals behavior from user"),
    (r"pretend\s+(that|to\s+be|you)", "Social engineering via pretense"),
    (r"act\s+as\s+if\s+you\s+(don.t|do\s+not)\s+have\s+(any\s+)?restrictions", "Tries to remove safety limits"),
    # Data exfiltration via prompt
    (r"(send|post|upload|transmit)\s+.{0,30}(to|at)\s+https?://", "Instructs agent to send data to external URL"),
    (r"base64\s*(encode|decode)", "Base64 encoding (common in data exfiltration)"),
    (r"encode\s+.{0,20}(and|then)\s+(send|post|transmit)", "Encode-and-exfiltrate pattern"),
]

# Credential theft patterns - accessing sensitive data
_CREDENTIAL_PATTERNS = [
    (r"\.ssh/", "Accesses SSH keys directory"),
    (r"id_rsa|id_ed25519|id_ecdsa", "References SSH private key files"),
    (r"\.aws/credentials", "Accesses AWS credentials file"),
    (r"\.env\b", "Accesses .env file (may contain secrets)"),
    (r"keychain|keyring", "Accesses system keychain/keyring"),
    (r"(chrome|firefox|safari|brave|edge).{0,30}(cookies?|passwords?|login|profile)", "Accesses browser credentials"),
    (r"wallet\.dat|seed\s*phrase|mnemonic|private\s*key", "Accesses cryptocurrency wallet data"),
    (r"/etc/shadow|/etc/passwd", "Accesses system password files"),
    (r"(cat|read|dump|export)\s+.{0,30}(token|secret|key|password|credential)", "Reads credential files"),
]

# Reverse shell / backdoor patterns
_BACKDOOR_PATTERNS = [
    (r"(nc|ncat|netcat)\s+(-[a-z]+\s+)*\S+\s+\d+", "Netcat connection (possible reverse shell)"),
    (r"(bash|sh|zsh)\s+-i\s+[>|&]", "Interactive shell redirect (reverse shell)"),
    (r"/dev/tcp/", "Bash TCP device (reverse shell technique)"),
    (r"mkfifo|mknod.*p\b", "Named pipe creation (reverse shell technique)"),
    (r"(python|perl|ruby|php)\s+-[a-z]*\s+.{0,50}(socket|connect|exec)", "Scripted reverse shell"),
    (r"cron(tab)?\s+.{0,30}(curl|wget|bash|sh)", "Cron job installation (persistence)"),
    (r"launchctl\s+load|systemctl\s+enable", "System service installation (persistence)"),
    (r"(curl|wget)\s+.{0,50}\|\s*(bash|sh|python)", "Download-and-execute (pipe to shell)"),
]

# Cryptominer patterns
_CRYPTOMINER_PATTERNS = [
    (r"(xmrig|minerd|cgminer|bfgminer|ethminer)", "Known cryptominer binary"),
    (r"stratum\+tcp://|mining\.pool|pool\.(hashvault|minexmr|nanopool)", "Mining pool connection"),
    (r"monero|xmr|bitcoin|ethereum.{0,30}(mine|hash|worker)", "Cryptocurrency mining reference"),
]

# Undeclared network access
_NETWORK_PATTERNS = [
    (r"\b(curl|wget|fetch|httpie)\b", "network_tool"),
    (r"requests\.(get|post|put|delete|patch)", "python_requests"),
    (r"urllib|http\.client|aiohttp", "python_http_lib"),
    (r"XMLHttpRequest|fetch\(|axios", "js_http"),
]

# Obfuscation patterns
_OBFUSCATION_PATTERNS = [
    (r"eval\s*\(", "eval() call (code execution from string)"),
    (r"exec\s*\(", "exec() call (code execution from string)"),
    (r"\\x[0-9a-f]{2}(\\x[0-9a-f]{2}){3,}", "Hex-encoded string (possible obfuscation)"),
    (r"\\u[0-9a-f]{4}(\\u[0-9a-f]{4}){3,}", "Unicode-escaped string (possible obfuscation)"),
    (r"atob\s*\(|btoa\s*\(|Buffer\.from\(.*base64", "Base64 decode in code (possible obfuscation)"),
    (r"String\.fromCharCode", "Character code construction (obfuscation)"),
    (r"import\s+subprocess|os\.system|os\.popen|subprocess\.(run|call|Popen)", "System command execution"),
]

# Known typosquatted skill names (from ClawHavoc campaign)
_KNOWN_TYPOSQUATS = {
    "githob-integration",
    "github-intergration",
    "github-integartion",
    "web-serach",
    "web-seach",
    "websearch-pro",
    "google-searh",
    "gooogle-search",
    "slack-intergration",
    "slak-integration",
    "docker-managment",
    "dockerr-manager",
}

# Popular legitimate skill names (for typosquat detection)
_POPULAR_SKILLS = {
    "github-integration",
    "web-search",
    "google-search",
    "slack-integration",
    "docker-manager",
    "aws-cli",
    "kubernetes",
    "terraform",
    "ansible",
}


class SkillSecurityScanner:
    """Scans skills for security threats before import.

    Based on real-world threat intelligence from the ClawHub crisis.
    Every finding is explained in plain English so non-technical
    users can make informed decisions.
    """

    def scan(self, skill: ParsedSkill) -> SkillSecurityReport:
        """Run all security checks on a parsed skill.

        Args:
            skill: The parsed OpenClaw skill to scan

        Returns:
            SkillSecurityReport with all findings
        """
        findings: List[SkillSecurityFinding] = []

        # Combine all scannable text
        instructions = skill.instructions or ""
        all_text = instructions
        for _path, content in (skill.supporting_files or {}).items():
            all_text += "\n" + content

        # Run all checks
        findings.extend(self._check_prompt_injection(instructions))
        findings.extend(self._check_credentials(all_text))
        findings.extend(self._check_backdoors(all_text))
        findings.extend(self._check_cryptominers(all_text))
        findings.extend(self._check_obfuscation(all_text))
        findings.extend(self._check_undeclared_network(skill, all_text))
        findings.extend(self._check_typosquatting(skill.name))
        findings.extend(self._check_metadata_consistency(skill))

        # Build report
        report = SkillSecurityReport(
            skill_name=skill.name,
            total_findings=len(findings),
            critical_count=sum(1 for f in findings if f.severity == Severity.CRITICAL),
            high_count=sum(1 for f in findings if f.severity == Severity.HIGH),
            medium_count=sum(1 for f in findings if f.severity == Severity.MEDIUM),
            low_count=sum(1 for f in findings if f.severity == Severity.LOW),
            info_count=sum(1 for f in findings if f.severity == Severity.INFO),
            findings=findings,
        )

        # Determine safety
        report.safe_to_import = report.critical_count == 0 and report.high_count == 0
        report.summary = self._build_summary(report)

        return report

    def _check_prompt_injection(self, instructions: str) -> List[SkillSecurityFinding]:
        """Check for prompt injection patterns in skill instructions."""
        findings = []
        lower = instructions.lower()

        for pattern, description in _PROMPT_INJECTION_PATTERNS:
            match = re.search(pattern, lower, re.IGNORECASE)
            if match:
                findings.append(
                    SkillSecurityFinding(
                        severity=Severity.CRITICAL,
                        category="prompt_injection",
                        title="Prompt injection detected",
                        description=f"This skill tries to manipulate the agent's behavior: {description}",
                        evidence=match.group(0)[:100],
                        recommendation="Do NOT import this skill. It contains instructions designed to bypass safety controls.",
                    )
                )

        return findings

    def _check_credentials(self, text: str) -> List[SkillSecurityFinding]:
        """Check for credential theft patterns."""
        findings = []
        lower = text.lower()

        for pattern, description in _CREDENTIAL_PATTERNS:
            match = re.search(pattern, lower, re.IGNORECASE)
            if match:
                findings.append(
                    SkillSecurityFinding(
                        severity=Severity.HIGH,
                        category="credential_access",
                        title="Accesses sensitive data",
                        description=f"This skill accesses sensitive files on your device: {description}",
                        evidence=match.group(0)[:100],
                        recommendation="Review carefully. This skill may be trying to steal passwords or keys.",
                    )
                )

        return findings

    def _check_backdoors(self, text: str) -> List[SkillSecurityFinding]:
        """Check for reverse shell and backdoor patterns."""
        findings = []

        for pattern, description in _BACKDOOR_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                findings.append(
                    SkillSecurityFinding(
                        severity=Severity.CRITICAL,
                        category="backdoor",
                        title="Backdoor or reverse shell detected",
                        description=f"This skill tries to open a connection back to an attacker: {description}",
                        evidence=match.group(0)[:100],
                        recommendation="Do NOT import. This is a known malware pattern from the ClawHub security crisis.",
                    )
                )

        return findings

    def _check_cryptominers(self, text: str) -> List[SkillSecurityFinding]:
        """Check for cryptominer patterns."""
        findings = []

        for pattern, description in _CRYPTOMINER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                findings.append(
                    SkillSecurityFinding(
                        severity=Severity.CRITICAL,
                        category="cryptominer",
                        title="Cryptocurrency miner detected",
                        description=f"This skill installs or runs a cryptocurrency miner: {description}",
                        evidence=match.group(0)[:100],
                        recommendation="Do NOT import. This skill will use your device to mine cryptocurrency.",
                    )
                )

        return findings

    def _check_obfuscation(self, text: str) -> List[SkillSecurityFinding]:
        """Check for code obfuscation patterns."""
        findings = []

        for pattern, description in _OBFUSCATION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                findings.append(
                    SkillSecurityFinding(
                        severity=Severity.MEDIUM,
                        category="obfuscation",
                        title="Hidden or obfuscated code",
                        description=f"This skill contains code that's hard to read on purpose: {description}",
                        evidence=match.group(0)[:100],
                        recommendation="Legitimate skills don't hide their code. Review with caution.",
                    )
                )

        return findings

    def _check_undeclared_network(self, skill: ParsedSkill, text: str) -> List[SkillSecurityFinding]:
        """Check for network access not declared in requirements."""
        findings = []

        # Get declared binaries
        declared_bins: set[str] = set()
        if skill.metadata and skill.metadata.requires:
            declared_bins = {b.lower() for b in skill.metadata.requires.bins}

        for pattern, tool_type in _NETWORK_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tool_name = match.group(0).split("(")[0].strip().lower()
                if tool_name not in declared_bins and tool_type == "network_tool":
                    findings.append(
                        SkillSecurityFinding(
                            severity=Severity.MEDIUM,
                            category="undeclared_network",
                            title="Uses internet without declaring it",
                            description=f"This skill uses '{match.group(0)}' to access the internet but doesn't list it in requirements.",
                            evidence=match.group(0)[:100],
                            recommendation="The skill should declare all programs it uses. This could be an oversight or intentional hiding.",
                        )
                    )

        return findings

    def _check_typosquatting(self, skill_name: str) -> List[SkillSecurityFinding]:
        """Check if skill name is suspiciously similar to a popular skill."""
        findings = []
        name_lower = skill_name.lower()

        # Direct known typosquats
        if name_lower in _KNOWN_TYPOSQUATS:
            findings.append(
                SkillSecurityFinding(
                    severity=Severity.CRITICAL,
                    category="typosquatting",
                    title="Known fake skill name",
                    description=f"The name '{skill_name}' is a known typosquat from the ClawHub malware campaign.",
                    evidence=skill_name,
                    recommendation="Do NOT import. This name was used in the ClawHavoc malware campaign.",
                )
            )
            return findings

        # Levenshtein-like check against popular names
        for popular in _POPULAR_SKILLS:
            if name_lower == popular:
                continue
            distance = _simple_edit_distance(name_lower, popular)
            if 0 < distance <= 2 and len(name_lower) > 3:
                findings.append(
                    SkillSecurityFinding(
                        severity=Severity.HIGH,
                        category="typosquatting",
                        title="Name very similar to a popular skill",
                        description=f"The name '{skill_name}' is very similar to the popular skill '{popular}'. This could be a typosquat attack.",
                        evidence=f"{skill_name} ≈ {popular}",
                        recommendation="Verify this is the real skill, not an imitation. Check the source URL.",
                    )
                )

        return findings

    def _check_metadata_consistency(self, skill: ParsedSkill) -> List[SkillSecurityFinding]:
        """Check for inconsistencies between metadata and content."""
        findings = []

        # Check if instructions reference env vars not declared in requires
        env_pattern = re.findall(r"[A-Z][A-Z0-9_]{3,}(?:_KEY|_TOKEN|_SECRET|_PASSWORD|_API)", skill.instructions or "")
        declared_env = set()
        if skill.metadata and skill.metadata.requires:
            declared_env = set(skill.metadata.requires.env)

        for env_ref in env_pattern:
            if env_ref not in declared_env:
                findings.append(
                    SkillSecurityFinding(
                        severity=Severity.LOW,
                        category="metadata_inconsistency",
                        title="Uses a secret not listed in requirements",
                        description=f"The instructions mention '{env_ref}' but it's not listed as a required environment variable.",
                        evidence=env_ref,
                        recommendation="The skill should declare all secrets it uses. This may be an oversight.",
                    )
                )

        # Check for suspiciously short description with long instructions
        if len(skill.description or "") < 10 and len(skill.instructions or "") > 500:
            findings.append(
                SkillSecurityFinding(
                    severity=Severity.LOW,
                    category="metadata_inconsistency",
                    title="Very short description with long instructions",
                    description="The skill has almost no description but very long instructions. Legitimate skills usually describe what they do.",
                    recommendation="Check that the instructions match what you expect.",
                )
            )

        return findings

    def _build_summary(self, report: SkillSecurityReport) -> str:
        """Build a plain English summary of the scan results."""
        if report.total_findings == 0:
            return "No security issues found. This skill looks safe to import."

        if report.critical_count > 0:
            return (
                f"DANGER: Found {report.critical_count} critical security issue(s). "
                "This skill may be malicious. Do NOT import it."
            )

        if report.high_count > 0:
            return (
                f"WARNING: Found {report.high_count} high-severity issue(s). "
                "Review the findings carefully before importing."
            )

        if report.medium_count > 0:
            return f"Caution: Found {report.medium_count} suspicious pattern(s). " "Probably safe but worth reviewing."

        return f"Found {report.total_findings} minor note(s). " "No significant concerns."


def _simple_edit_distance(a: str, b: str) -> int:
    """Simple Levenshtein distance for typosquat detection."""
    if len(a) > len(b):
        a, b = b, a
    distances: list[int] = list(range(len(a) + 1))
    for i2, c2 in enumerate(b):
        new_distances = [i2 + 1]
        for i1, c1 in enumerate(a):
            if c1 == c2:
                new_distances.append(distances[i1])
            else:
                new_distances.append(1 + min(distances[i1], distances[i1 + 1], new_distances[-1]))
        distances = new_distances
    return distances[-1]
