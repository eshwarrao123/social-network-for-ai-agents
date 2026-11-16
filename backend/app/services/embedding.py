"""
Embedding service — wraps Ollama nomic-embed-text.
Returns real 768-dimensional embeddings. No mocked values.
"""
from __future__ import annotations

import structlog
import httpx

from app.config import get_settings

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """
    Client for Ollama's nomic-embed-text model.
    
    Produces genuine 768-dimensional sentence embeddings.
    Falls back gracefully if Ollama is unavailable — logs the error
    and returns None. Callers must handle None (embedding_status=failed).
    """

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_embed_model
        self.dimensions = settings.embedding_dimensions
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def embed(self, text: str) -> list[float] | None:
        """
        Embed a single text string.
        Returns a list of 768 floats or None on failure.
        """
        try:
            payload = {"model": self.model, "prompt": text}
            response = await self._client.post("/api/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding")
            if not embedding or len(embedding) != self.dimensions:
                logger.error(
                    "embedding_dimension_mismatch",
                    expected=self.dimensions,
                    got=len(embedding) if embedding else 0,
                )
                return None
            return embedding
        except httpx.ConnectError:
            logger.warning("ollama_unavailable", url=self.base_url)
            return None
        except Exception as exc:
            logger.error("embedding_failed", error=str(exc))
            return None

    async def embed_agent_profile(self, agent) -> list[float] | None:
        """
        Build an embedding from an agent's interest profile.
        Concatenates description + industries + capabilities + tags.
        """
        parts = []
        if agent.description:
            parts.append(agent.description)
        if agent.industries:
            parts.append("Industries: " + ", ".join(agent.industries))
        if agent.capabilities:
            parts.append("Capabilities: " + ", ".join(agent.capabilities))
        if agent.tags:
            parts.append("Tags: " + ", ".join(agent.tags))

        if not parts:
            logger.warning("empty_agent_profile", agent_id=str(agent.id))
            return None

        profile_text = ". ".join(parts)
        return await self.embed(profile_text)

    async def embed_post(self, post) -> list[float] | None:
        """
        Build an embedding from a post's title + content + tags.
        """
        text = f"{post.title}\n\n{post.content}"
        if post.tags:
            text += "\n\nTopics: " + ", ".join(post.tags)
        return await self.embed(text)

    async def close(self):
        await self._client.aclose()


# Module-level singleton — shared across workers
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
