"""Security and Data Sanitization Utilities (SEC-007)."""

import re

# Patterns matching sensitive API keys and tokens
API_KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),               # Google Gemini / Firebase API keys
    re.compile(r"AQ[0-9A-Za-z\-_]{20,}"),                # Google Service Account / Vertex tokens
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),               # OpenAI / Generic standard keys
    re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}"),           # Anthropic API keys
]


def mask_sensitive_data(text: str) -> str:
    """Masks API keys and secrets in strings, logs and error messages (SEC-007)."""
    if not text or not isinstance(text, str):
        return text

    sanitized = text
    for pattern in API_KEY_PATTERNS:
        def _replace_match(match: re.Match) -> str:
            val = match.group(0)
            if len(val) <= 8:
                return "[REDACTED_SECRET]"
            prefix = val[:4]
            suffix = val[-2:]
            return f"{prefix}...***...{suffix}"

        sanitized = pattern.sub(_replace_match, sanitized)

    return sanitized
