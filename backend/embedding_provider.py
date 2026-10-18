"""
Local-device embedding provider foundation.
Uses locally installed Ollama embedding models (default: nomic-embed-text, 768 dimensions).
Resume text is embedded locally on-device and is NEVER sent to any cloud service.
"""
import json
import math
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

DEFAULT_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")
DEFAULT_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "nomic-embed-text")
DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
DEFAULT_EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60.0"))


class EmbeddingModelSetupError(RuntimeError):
    """Raised when the local embedding model fails to initialize or is not found."""
    pass


class EmbeddingProvider(ABC):
    """Abstract provider interface for document and query embeddings."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The identifier of the active embedding model."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The expected vector dimension."""
        pass

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for a list of document chunks."""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Generate a vector embedding for a search query."""
        pass


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Local-only embedding provider powered by local Ollama daemon.
    Default model: nomic-embed-text (768 dimensions).
    Calls POST {base_url}/api/embed using Python standard library (no external network or cloud).
    Resume text strictly remains on this device.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
    ):
        self._model_name = model_name or DEFAULT_MODEL_NAME
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)).rstrip("/")
        self.timeout = max(1.0, float(timeout))
        self._expected_dimension: Optional[int] = 768 if "nomic" in self._model_name.lower() else None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._expected_dimension or 768

    def _call_embed_api(self, input_data: str | list[str]) -> list[list[float]]:
        """
        Call local Ollama /api/embed endpoint via urllib.request and return validated vectors.
        """
        url = f"{self.base_url}/api/embed"
        payload = {
            "model": self._model_name,
            "input": input_data,
        }
        try:
            req_data = json.dumps(payload).encode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Failed to serialize embedding request: {str(e)}") from e

        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise EmbeddingModelSetupError(
                    f"Local Ollama embedding model '{self._model_name}' was not found. "
                    f"Ensure it is installed locally with 'ollama pull {self._model_name}'."
                ) from e
            try:
                err_body = e.read(128).decode("utf-8", errors="replace").strip()[:80]
            except Exception:
                err_body = ""
            raise RuntimeError(f"Local Ollama embedding API returned HTTP {e.code}: {err_body or e.reason}") from e
        except urllib.error.URLError as e:
            reason = str(getattr(e, "reason", ""))
            raise EmbeddingModelSetupError(
                f"Failed to connect to local Ollama service at {self.base_url} ({reason}). "
                "Ensure the local Ollama server is running on this device."
            ) from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error communicating with local Ollama embed API: {str(e)}") from e

        if not isinstance(data, dict) or "embeddings" not in data:
            raise RuntimeError("Local Ollama embedding API returned an invalid response structure (missing 'embeddings').")

        raw_embeddings = data["embeddings"]
        if not isinstance(raw_embeddings, list):
            raise RuntimeError("Local Ollama embedding API returned non-list 'embeddings'.")

        # Validate vectors: finite floats and consistent dimensions
        validated: list[list[float]] = []
        target_dim: Optional[int] = self._expected_dimension

        for idx, vec in enumerate(raw_embeddings):
            if not isinstance(vec, list) or len(vec) == 0:
                raise RuntimeError(f"Invalid embedding at index {idx}: expected non-empty vector.")

            if target_dim is None:
                target_dim = len(vec)
                self._expected_dimension = target_dim
            elif len(vec) != target_dim:
                raise RuntimeError(
                    f"Inconsistent vector dimensions: index {idx} has {len(vec)}, expected {target_dim}."
                )

            float_vec: list[float] = []
            for val_idx, val in enumerate(vec):
                try:
                    f_val = float(val)
                except (ValueError, TypeError):
                    raise RuntimeError(f"Non-numeric vector value at embedding {idx}, position {val_idx}.")
                if not math.isfinite(f_val):
                    raise RuntimeError(f"Non-finite vector value at embedding {idx}, position {val_idx}.")
                float_vec.append(f_val)

            validated.append(float_vec)

        return validated

    # nomic-embed-text was trained with task prefixes; omitting them noticeably hurts retrieval quality.
    def _doc_prefix(self) -> str:
        return "search_document: " if "nomic" in self._model_name.lower() else ""

    def _query_prefix(self) -> str:
        return "search_query: " if "nomic" in self._model_name.lower() else ""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # Batch in chunks of 32 to stay within safe request limits
        batch_size = 32
        all_embeddings: list[list[float]] = []
        prefix = self._doc_prefix()

        for i in range(0, len(texts), batch_size):
            batch = [prefix + t for t in texts[i : i + batch_size]]
            batch_vectors = self._call_embed_api(batch)
            if len(batch_vectors) != len(batch):
                raise RuntimeError(
                    f"Ollama embedding API returned {len(batch_vectors)} vectors for a batch of {len(batch)} items."
                )
            all_embeddings.extend(batch_vectors)

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        if not text or not text.strip():
            # Return zero vector of appropriate dimension if query is empty
            dim = self.dimension
            return [0.0] * dim

        vectors = self._call_embed_api(self._query_prefix() + text.strip())
        if not vectors:
            raise RuntimeError("Ollama embedding API returned empty vector for query.")
        return vectors[0]


_provider_instance: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    """
    Get the configured embedding provider singleton.
    Configured via EMBEDDING_PROVIDER and EMBEDDING_MODEL_NAME.
    Defaults to local Ollama with nomic-embed-text (768 dimensions).
    """
    global _provider_instance
    if _provider_instance is None:
        provider_name = os.getenv("EMBEDDING_PROVIDER", DEFAULT_PROVIDER).lower()
        model_name = os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_MODEL_NAME)

        if provider_name == "ollama":
            _provider_instance = OllamaEmbeddingProvider(model_name=model_name)
        else:
            raise ValueError(f"Unsupported embedding provider: '{provider_name}'. Supported: 'ollama'.")

    return _provider_instance
