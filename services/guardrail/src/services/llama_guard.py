"""Llama Guard 3 safety and prompt-injection inspection client (:3007)."""

import re
from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel

from config import settings


class GuardrailDecision(BaseModel):
    """Decision resulting from safety and prompt injection inspection."""

    is_safe: bool
    threat_category: str | None = None
    risk_score: float = 0.0
    action: str = "allow"  # "allow" or "silent_drop"
    details: str | None = None


_INJECTION_PATTERNS = [
    (r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|prompts|directions)\b", "prompt_injection"),
    (r"(?i)\bforget\s+(?:all\s+)?(?:previous|prior)\s+(?:rules|instructions)\b", "prompt_injection"),
    (r"(?i)\b(?:reveal|show|print|output)\s+(?:your\s+)?(?:system\s+prompt|initial\s+prompt|developer\s+mode)\b", "system_prompt_leak"),
    (r"(?i)\b(?:you\s+are\s+now|act\s+as)\s+DAN\b", "jailbreak_dan"),
    (r"(?i)\bdesconsidere\s+(?:todas\s+as\s+)?instru[cç][oõ]es\s+anteriores\b", "prompt_injection"),
    (r"(?i)\b(?:revele|mostre|exiba)\s+(?:o\s+)?prompt\s+(?:do\s+sistema|inicial)\b", "system_prompt_leak"),
    (r"(?i)\bdeveloper\s+mode\s+enabled\b", "jailbreak"),
]


class LlamaGuardClient:
    """Client for Llama Guard 3 via Groq LPU (TC-110, TC-111)."""

    def __init__(
        self,
        api_key: str = settings.GROQ_API_KEY,
        api_base: str = settings.GROQ_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self._client = client

    def check_heuristics(self, text: str) -> GuardrailDecision | None:
        """Runs fast regex heuristics for known prompt injection / jailbreak patterns."""
        for pattern, category in _INJECTION_PATTERNS:
            if re.search(pattern, text):
                logger.warning("Prompt injection detected via heuristic: {cat}", cat=category)
                return GuardrailDecision(
                    is_safe=False,
                    threat_category=category,
                    risk_score=0.98,
                    action="silent_drop",
                    details=f"Matched pattern: {category}",
                )
        return None

    async def inspect(self, text: str) -> GuardrailDecision:
        """Inspects content for safety violations and prompt injections."""
        # 1. Fast regex heuristic check (< 1ms)
        heuristic = self.check_heuristics(text)
        if heuristic:
            return heuristic

        # 2. Call Groq Llama Guard 3 model
        url = f"{self.api_base}/chat/completions"
        client = self._client or httpx.AsyncClient(timeout=10.0)

        payload = {
            "model": settings.LLAMA_GUARD_MODEL,
            "messages": [{"role": "user", "content": text}],
            "temperature": 0.0,
            "max_tokens": 50,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            res_json = resp.json()
            raw_reply = res_json["choices"][0]["message"]["content"].strip()

            if raw_reply.lower().startswith("unsafe"):
                lines = raw_reply.splitlines()
                threat_code = lines[1].strip() if len(lines) > 1 else "unspecified_threat"
                logger.warning("Llama Guard flagged message as unsafe: {threat}", threat=threat_code)
                return GuardrailDecision(
                    is_safe=False,
                    threat_category=threat_code,
                    risk_score=0.95,
                    action="silent_drop",
                    details=raw_reply,
                )

            return GuardrailDecision(
                is_safe=True,
                threat_category=None,
                risk_score=0.05,
                action="allow",
                details="Content passed safety checks",
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Groq Llama Guard HTTP error: {code} - {err}", code=exc.response.status_code, err=exc)
            # Fail-safe policy: return error decision without crashing
            return GuardrailDecision(
                is_safe=False,
                threat_category="guardrail_service_error",
                risk_score=0.5,
                action="silent_drop",
                details=f"HTTP {exc.response.status_code}",
            )
        except Exception as exc:
            logger.error("Unexpected error during Llama Guard inspection: {err}", err=exc)
            return GuardrailDecision(
                is_safe=False,
                threat_category="guardrail_timeout_or_unreachable",
                risk_score=0.5,
                action="silent_drop",
                details=str(exc),
            )
        finally:
            if self._client is None:
                await client.aclose()
