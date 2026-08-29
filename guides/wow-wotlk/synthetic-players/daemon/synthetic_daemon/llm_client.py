"""Async vLLM / OpenAI-compatible client for synthetic players."""

from __future__ import annotations

import logging
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field
from .config import LLMConfig
from .director import IntentType

logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    """Encapsulates generated text, parsed action commands, and latency."""
    content: str
    action_command: Optional[str] = None
    intent_type: Optional[IntentType] = None
    control_tag_rejected: bool = False
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

            had_intent_tag = bool(re.search(r"\[INTENT:\s*[^\]]+\]", raw_text, flags=re.IGNORECASE))
            clean_text, intent_type = self._extract_intent(raw_text)
            clean_text, action = self._extract_action(clean_text)
            control_tag_rejected = had_intent_tag and intent_type is None
            if action and intent_type:
                logger.warning("Model emitted both an action and a director intent; rejecting both controls")
                action = None
                intent_type = None
                control_tag_rejected = True
            elif control_tag_rejected:
                action = None
            return LLMResponse(
                content=clean_text,
                action_command=action,
                intent_type=intent_type,
                control_tag_rejected=control_tag_rejected,
                latency_ms=latency_ms,
            )

        except httpx.HTTPStatusError as e:
            logger.error("LLM HTTP error %d: %s", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.error("LLM inference error: %s", e)
            raise

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_message: str,
        schema_name: str,
        json_schema: Dict[str, Any],
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Generate one schema-constrained planning document.

        This path is used for bounded, one-shot planning rather than persona
        dialogue. Callers must still validate the decoded document against
        their own allowlist before persisting or executing it.
        """
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": json_schema,
                },
            },
        }

        try:
            resp = await self.client.post(
                "/chat/completions",
                json=body,
                timeout=max(self.config.timeout_seconds, 120.0),
            )
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"].strip()
            decoded = json.loads(raw_text)
            if not isinstance(decoded, dict):
                raise ValueError("Structured LLM response must be a JSON object")
            return decoded
        except httpx.HTTPStatusError as e:
            logger.error("Structured LLM HTTP error %d: %s", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.error("Structured LLM inference error: %s", e)
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

    @staticmethod
    def _extract_intent(text: str) -> Tuple[str, Optional[IntentType]]:
        """Strip intent tags and return one member of the finite catalog."""
        pattern = r"\[INTENT:\s*([^\]]+)\]"
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        cleaned_text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

        if len(matches) != 1:
            return cleaned_text, None

        requested = "_".join(matches[0].upper().split())
        try:
            return cleaned_text, IntentType(requested)
        except ValueError:
            return cleaned_text, None
