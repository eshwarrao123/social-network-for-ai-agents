"""
LLM Service — pluggable LLM provider.

Supported backends:
  - ollama: Local Ollama (default)
  - openai: OpenAI API
  - anthropic: Anthropic API
  - disabled: No LLM (silent skip)

SECURITY NOTE: Post content is NEVER placed in system_prompt.
Only user_message carries post content, and callers must delimit it clearly.
"""
from __future__ import annotations

import structlog
from app.config import get_settings

logger = structlog.get_logger(__name__)


class LlmService:
    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.llm_provider
        self.model = self.settings.llm_model

    def is_available(self) -> bool:
        return self.provider != "disabled"

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
    ) -> tuple[str | None, str, float]:
        """
        Generate a response.
        Returns (text, model_name, confidence_score).
        confidence_score is a rough proxy (1.0 for successful generation).
        """
        if self.provider == "disabled":
            return None, "disabled", 0.0

        try:
            if self.provider == "ollama":
                return await self._generate_ollama(system_prompt, user_message)
            elif self.provider == "openai":
                return await self._generate_openai(system_prompt, user_message)
            elif self.provider == "anthropic":
                return await self._generate_anthropic(system_prompt, user_message)
            else:
                logger.error("unknown_llm_provider", provider=self.provider)
                return None, self.model, 0.0
        except Exception as exc:
            logger.error("llm_generation_failed", provider=self.provider, error=str(exc))
            return None, self.model, 0.0

    async def _generate_ollama(self, system: str, user: str) -> tuple[str, str, float]:
        import httpx
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(base_url=self.settings.ollama_base_url, timeout=60.0) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            text = data["message"]["content"].strip()
            return text, self.model, 1.0

    async def _generate_openai(self, system: str, user: str) -> tuple[str, str, float]:
        import httpx
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
            return text, self.model, 1.0

    async def _generate_anthropic(self, system: str, user: str) -> tuple[str, str, float]:
        import httpx
        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            text = data["content"][0]["text"].strip()
            return text, self.model, 1.0


_llm_service: LlmService | None = None


def get_llm_service() -> LlmService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LlmService()
    return _llm_service
