"""
Embedding service — provides deterministic text construction and vector generation
using Ollama's nomic-embed-text model (768 dimensions).
"""
from __future__ import annotations

import abc
import math
from typing import Any, Sequence

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

# Constants
NOMIC_DOC_PREFIX = "search_document: "
NOMIC_QUERY_PREFIX = "search_query: "
DEFAULT_EMBEDDING_DIMENSIONS = 768


# ─────────────────────────────────────────────────────────────────────────────
# Exception Hierarchy
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingError(Exception):
    """Base exception for embedding pipeline errors."""


class EmbeddingConnectionError(EmbeddingError):
    """Raised when the embedding provider is unreachable or times out."""


class EmbeddingDimensionError(EmbeddingError):
    """Raised when the returned vector does not match expected dimensions."""


class EmbeddingValueError(EmbeddingError):
    """Raised when the vector contains NaN, infinity, invalid types, or degenerate zeros."""


class EmbeddingResponseError(EmbeddingError):
    """Raised when the embedding provider returns an unexpected HTTP or JSON payload."""


# ─────────────────────────────────────────────────────────────────────────────
# Provider Interface
# ─────────────────────────────────────────────────────────────────────────────

class BaseEmbeddingProvider(abc.ABC):
    """Abstract interface for semantic embedding providers."""

    @abc.abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generates a semantic embedding vector for the provided text string."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Closes any underlying network connections."""
        ...


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """
    Ollama-backed embedding provider using nomic-embed-text.
    Calls POST /api/embed (with graceful fallback to /api/embeddings for legacy servers).
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        endpoint: str | None = None,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_embed_model
        self.dimensions = dimensions or settings.embedding_dimensions
        self.endpoint = endpoint or getattr(settings, "ollama_embed_endpoint", "/api/embed")
        self._connect_timeout = connect_timeout or getattr(settings, "ollama_connect_timeout", 5.0)
        self._read_timeout = read_timeout or getattr(settings, "ollama_read_timeout", 30.0)

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            timeout = httpx.Timeout(
                connect=self._connect_timeout,
                read=self._read_timeout,
                write=10.0,
                pool=10.0,
            )
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
            self._owns_client = True

    async def embed(self, text: str) -> list[float]:
        """
        Calls Ollama to generate an embedding.
        Validates the returned vector for dimension, numeric validity, and degeneracy.
        """
        if not text or not text.strip():
            raise EmbeddingValueError("Cannot embed empty or whitespace-only text.")

        payload = {"model": self.model, "input": text}

        try:
            response = await self._client.post(self.endpoint, json=payload)
            # If endpoint is /api/embed and returns 404, attempt legacy fallback to /api/embeddings
            if response.status_code == 404 and self.endpoint == "/api/embed":
                logger.info("ollama_embed_fallback_to_embeddings", url=f"{self.base_url}/api/embeddings")
                legacy_payload = {"model": self.model, "prompt": text}
                response = await self._client.post("/api/embeddings", json=legacy_payload)

            response.raise_for_status()
            data = response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            logger.warning("ollama_connection_error", url=self.base_url, error=str(exc))
            raise EmbeddingConnectionError(f"Ollama server unavailable at {self.base_url}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            logger.error("ollama_http_error", status_code=exc.response.status_code, response=exc.response.text)
            raise EmbeddingResponseError(f"Ollama HTTP error {exc.response.status_code}: {exc.response.text}") from exc
        except Exception as exc:
            logger.error("ollama_request_failed", error=str(exc))
            raise EmbeddingResponseError(f"Ollama request failed: {exc}") from exc

        # Parse vector from response
        raw_vector = self._parse_vector(data)
        self._validate_vector(raw_vector)
        return raw_vector

    def _parse_vector(self, data: dict[str, Any]) -> list[float]:
        # Ollama /api/embed format: {"embeddings": [[0.1, ...]]}
        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and len(embeddings) > 0:
            first = embeddings[0]
            if isinstance(first, list):
                return first
            return embeddings

        # Legacy /api/embeddings format: {"embedding": [0.1, ...]}
        embedding = data.get("embedding")
        if isinstance(embedding, list):
            return embedding

        raise EmbeddingResponseError(
            f"Ollama response missing 'embeddings' or 'embedding' array. Got keys: {list(data.keys())}"
        )

    def _validate_vector(self, vector: Sequence[Any]) -> None:
        """Enforces strictly 768 dimensions, valid numeric floats, and non-degeneracy."""
        if len(vector) != self.dimensions:
            raise EmbeddingDimensionError(
                f"Embedding dimension mismatch: expected {self.dimensions}, got {len(vector)}"
            )

        all_zeros = True
        for idx, val in enumerate(vector):
            if not isinstance(val, (int, float)):
                raise EmbeddingValueError(f"Invalid non-numeric value at vector index {idx}: {type(val)}")
            if math.isnan(val) or math.isinf(val):
                raise EmbeddingValueError(f"Invalid numeric value (NaN or Inf) at vector index {idx}")
            if val != 0.0:
                all_zeros = False

        if all_zeros:
            raise EmbeddingValueError("Degenerate vector: all dimensions are zero.")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


# ─────────────────────────────────────────────────────────────────────────────
# Text Builders (Deterministic & Prefix-Compliant)
# ─────────────────────────────────────────────────────────────────────────────

def build_post_text(
    title: str,
    content: str,
    tags: list[str] | None = None,
    target_industries: list[str] | None = None,
) -> str:
    """
    Constructs deterministic embedding input for an incoming post.
    In accordance with the asymmetric retrieval direction (post queries against agent documents),
    incoming posts use the Nomic prefix: 'search_query: '.
    """
    parts = [f"Title: {title.strip()}", f"Content: {content.strip()}"]
    if tags:
        clean_tags = sorted(list({t.strip().lower() for t in tags if t and t.strip()}))
        if clean_tags:
            parts.append("Tags: " + ", ".join(clean_tags))
    if target_industries:
        clean_ind = sorted(list({i.strip().lower() for i in target_industries if i and i.strip()}))
        if clean_ind:
            parts.append("Target Industries: " + ", ".join(clean_ind))

    body = "\n\n".join(parts)
    return f"{NOMIC_QUERY_PREFIX}{body}"


def build_agent_text(
    name: str,
    company: str,
    description: str | None = None,
    industries: list[str] | None = None,
    tags: list[str] | None = None,
    capabilities: list[str] | None = None,
) -> str:
    """
    Constructs deterministic embedding input for an agent interest profile.
    In accordance with the asymmetric retrieval direction (agent interest profiles as corpus documents),
    agent manifestos use the Nomic prefix: 'search_document: '.
    """
    parts = [f"Agent: {name.strip()}", f"Company: {company.strip()}"]
    if description and description.strip():
        parts.append(f"Manifesto: {description.strip()}")
    if industries:
        clean_ind = sorted(list({i.strip().lower() for i in industries if i and i.strip()}))
        if clean_ind:
            parts.append("Industries: " + ", ".join(clean_ind))
    if tags:
        clean_tags = sorted(list({t.strip().lower() for t in tags if t and t.strip()}))
        if clean_tags:
            parts.append("Tags: " + ", ".join(clean_tags))
    if capabilities:
        clean_cap = sorted(list({c.strip().lower() for c in capabilities if c and c.strip()}))
        if clean_cap:
            parts.append("Capabilities: " + ", ".join(clean_cap))

    body = "\n\n".join(parts)
    return f"{NOMIC_DOC_PREFIX}{body}"


# ─────────────────────────────────────────────────────────────────────────────
# High-Level Embedding Service
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingService:
    """
    High-level embedding service providing model coordination, text generation,
    and vector extraction for Agents and Posts.
    """

    def __init__(self, provider: BaseEmbeddingProvider | None = None) -> None:
        self.provider = provider or OllamaEmbeddingProvider()

    @property
    def model(self) -> str:
        if isinstance(self.provider, OllamaEmbeddingProvider):
            return self.provider.model
        return "custom"

    @property
    def dimensions(self) -> int:
        if isinstance(self.provider, OllamaEmbeddingProvider):
            return self.provider.dimensions
        return DEFAULT_EMBEDDING_DIMENSIONS

    def build_post_text(self, post: Any) -> str:
        """Constructs deterministic search_query text from a Post ORM instance."""
        return build_post_text(
            title=post.title,
            content=post.content,
            tags=post.tags,
            target_industries=post.target_industries,
        )

    def build_agent_text(self, agent: Any) -> str:
        """Constructs deterministic search_document text from an Agent ORM instance."""
        return build_agent_text(
            name=agent.name,
            company=agent.company,
            description=agent.description,
            industries=agent.industries,
            tags=agent.tags,
            capabilities=agent.capabilities,
        )

    async def embed(self, text: str) -> list[float]:
        """Generates embedding for a raw text string."""
        return await self.provider.embed(text)

    async def embed_post(self, post: Any) -> list[float]:
        """Constructs formatted post text and generates a 768-dim query vector."""
        text = self.build_post_text(post)
        return await self.provider.embed(text)

    async def embed_agent_profile(self, agent: Any) -> list[float]:
        """Constructs formatted agent manifesto text and generates a 768-dim document vector."""
        text = self.build_agent_text(agent)
        return await self.provider.embed(text)

    async def close(self) -> None:
        await self.provider.close()


# Module-level singleton
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
