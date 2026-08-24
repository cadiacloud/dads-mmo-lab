"""Async vLLM / OpenAI-compatible client for synthetic players."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field
from .config import LLMConfig

logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    """Encapsulates generated text, parsed action commands, and latency."""
    content: str
    action_command: Optional[str] = None
    latency_ms: float = 0.0


class SyntheticLLMClient:
    """Async client for vLLM / OpenAI-compatible chat completion servers."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        }
        self.client = httpx.AsyncClient(
            base_url=config.api_base.rstrip("/"),
            headers=headers,
            timeout=config.timeout_seconds,
        )

    async def close(self) -> None:
        """Close async HTTP client."""
        await self.client.aclose()

    async def health_check(self) -> bool:
        """Verify the vLLM / LLM server is accessible."""
        try:
            resp = await self.client.get("/models")
            return resp.status_code in (200, 401)
        except Exception as e:
            logger.warning("LLM health check failed: %s", e)
            return False

    async def generate_response(
        self,
        system_prompt: str,
        messages_history: List[Dict[str, str]],
        user_message: str,
    ) -> LLMResponse:
        """Generate in-character response with latency tracking and action parsing."""
        payload_messages = [{"role": "system", "content": system_prompt}]
        payload_messages.extend(messages_history)
        payload_messages.append({"role": "user", "content": user_message})

        body = {
            "model": self.config.model,
            "messages": payload_messages,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_tokens,
        }

        start_time = time.perf_counter()
        try:
            resp = await self.client.post("/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"].strip()
            latency_ms = (time.perf_counter() - start_time) * 1000

            clean_text, action = self._extract_action(raw_text)
            return LLMResponse(content=clean_text, action_command=action, latency_ms=latency_ms)

        except httpx.HTTPStatusError as e:
            logger.error("LLM HTTP error %d: %s", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.error("LLM inference error: %s", e)
            raise

    @staticmethod
    def _extract_action(text: str) -> Tuple[str, Optional[str]]:
        """Strip action tags and return one action only when it is allowlisted."""
        pattern = r"\[ACTION:\s*([^\]]+)\]"
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        cleaned_text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

        if len(matches) != 1:
            return cleaned_text, None

        requested = " ".join(matches[0].upper().split())
        if requested in {"STAND", "SIT", "SLEEP", "KNEEL"}:
            return cleaned_text, requested

        if requested == "REFRESHMENT":
            return cleaned_text, requested

        if requested == "BUFF ARCANE BRILLIANCE":
            return cleaned_text, requested

        emote_match = re.fullmatch(r"EMOTE (\d{1,3})", requested)
        if emote_match and int(emote_match.group(1)) <= 500:
            return cleaned_text, f"EMOTE {int(emote_match.group(1))}"

        portal_match = re.fullmatch(r"PORTAL ([A-Z ]{3,24})", requested)
        if portal_match:
            destination = portal_match.group(1).strip()
            aliases = {
                "THUNDERBLUFF": "THUNDER BLUFF",
                "SILVER MOON": "SILVERMOON",
                "UNDER CITY": "UNDERCITY",
            }
            destination = aliases.get(destination, destination)
            allowed_destinations = {
                "STORMWIND",
                "IRONFORGE",
                "DARNASSUS",
                "EXODAR",
                "THERAMORE",
                "ORGRIMMAR",
                "UNDERCITY",
                "THUNDER BLUFF",
                "SILVERMOON",
                "STONARD",
                "SHATTRATH",
                "DALARAN",
            }
            if destination in allowed_destinations:
                return cleaned_text, f"PORTAL {destination}"

        return cleaned_text, None
