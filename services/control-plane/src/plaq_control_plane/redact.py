"""Secret Redaction Filter for Plaq-OS Control Plane.

Scrubs sensitive tokens, passwords, AWS keys, private keys, and credentials
from tool parameters, standard output, and standard error before persistence
and audit logging.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Pattern, Tuple, Union


class SecretRedactor:
    """Automated scrubber for credentials, API tokens, and private keys."""

    PATTERNS: List[Tuple[Pattern[str], Union[str, Any]]] = [
        # 1. Bearer tokens (JWTs or arbitrary alphanumeric tokens)
        (
            re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE),
            "Bearer [REDACTED_TOKEN]",
        ),
        # 2. GitHub Personal Access Tokens (classic and fine-grained)
        (
            re.compile(r"\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{36,})\b"),
            "[REDACTED_GH_TOKEN]",
        ),
        # 3. Slack Bot and User Tokens
        (
            re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{20,})\b"),
            "[REDACTED_SLACK_TOKEN]",
        ),
        # 4. Basic Auth embedded in HTTP/HTTPS URLs (http://user:password@host)
        (
            re.compile(r"(https?://[^:\s]+:)([^@\s]+)(@)", re.IGNORECASE),
            r"\1[REDACTED]\3",
        ),
        # 5. AWS Access Key IDs (AKIA, ABIA, ACCA, ASIA)
        (
            re.compile(r"\b((?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16})\b"),
            "[REDACTED_AWS_KEY]",
        ),
        # 6. AWS Secret Access Keys (supports base64 characters +, /, =)
        (
            re.compile(
                r"((?:aws_secret_access_key|aws_secret)\s*[:=]\s*['\"]?)([A-Za-z0-9/+=]{16,})(['\"]?)",
                re.IGNORECASE,
            ),
            r"\1[REDACTED_SECRET_KEY]\3",
        ),
        # 7. Generic API keys and passwords in assignments or query parameters
        (
            re.compile(
                r"((?:api[_-]?key|password|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?)([^\s'\"&,;]+)(['\"]?)",
                re.IGNORECASE,
            ),
            r"\1[REDACTED]\3",
        ),
        # 8. Multiline PEM Private Keys (RSA, EC, OPENSSH, DSA, ENCRYPTED)
        (
            re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"),
            "[REDACTED_PRIVATE_KEY]",
        ),
    ]

    SENSITIVE_KEY_ROOTS = {
        "password",
        "secret",
        "token",
        "apikey",
        "authorization",
        "privatekey",
        "accesskey",
    }

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Redact sensitive patterns from arbitrary text while preserving hashes/UUIDs."""
        if not isinstance(text, str):
            return str(text) if text is not None else ""
        if not text:
            return ""

        redacted = text
        for pattern, replacement in cls.PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    @classmethod
    def redact_json(cls, data: Any) -> Any:
        """Recursively redact dictionary and list data structures."""
        if data is None:
            return None
        if isinstance(data, (int, float, bool)):
            return data
        if isinstance(data, str):
            return cls.redact_text(data)

        if isinstance(data, dict):
            new_dict: Dict[str, Any] = {}
            for k, v in data.items():
                k_norm = str(k).lower().replace("_", "").replace("-", "")
                if any(sk in k_norm for sk in cls.SENSITIVE_KEY_ROOTS):
                    new_dict[k] = "[REDACTED]"
                else:
                    new_dict[k] = cls.redact_json(v)
            return new_dict

        if isinstance(data, list):
            return [cls.redact_json(item) for item in data]

        return data


def redact_sensitive_info(data: Any) -> Any:
    """Scrub sensitive information from text strings or arbitrary json data structures."""
    if isinstance(data, str):
        return SecretRedactor.redact_text(data)
    return SecretRedactor.redact_json(data)
