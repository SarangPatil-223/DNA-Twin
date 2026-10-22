"""Provider-agnostic LLM and embedding interfaces. Keys come only from environment variables.

Embeddings:  HashingEmbedder (offline default, always available)
             SentenceTransformerEmbedder (if the package and model are installed)
             OllamaEmbedder (if an Ollama server is reachable)
LLMs:        AnthropicProvider (ANTHROPIC_API_KEY), GeminiProvider (GEMINI_API_KEY), OllamaProvider, ExtractiveProvider (no LLM:
             answers by quoting the best-matching retrieved sentences, clearly labelled)
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections import Counter

import httpx
import numpy as np

from app.settings import Settings, get_settings

_WORD = re.compile(r"[a-z0-9]+")
# sentence boundary that does not split after common abbreviations like "Dr." or "e.g."
_SENT = re.compile(r"(?<!\bDr\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bMrs\.)(?<!\bProf\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bal\.)(?<!\bvs\.)(?<=[.!?])\s+|\n+")


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class EmbeddingProvider(ABC):
    name: str
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder(EmbeddingProvider):
    """Feature-hashed unigrams, bigrams and character trigrams, sublinear TF, L2-normalised.
    Deterministic and offline. Weaker than neural embeddings; good enough for lexical RAG."""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _h(self, s: str) -> tuple[int, float]:
        d = hashlib.blake2b(s.encode(), digest_size=8).digest()
        v = int.from_bytes(d, "big")
        return v % self.dim, 1.0 if (v >> 63) & 1 else -1.0

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            toks = tokens(t)
            feats = Counter(toks)
            feats.update(f"{a}_{b}" for a, b in zip(toks, toks[1:]))
            for w in toks:
                w2 = f"#{w}#"
                feats.update(w2[j : j + 3] for j in range(len(w2) - 2))
            for f, c in feats.items():
                j, sgn = self._h(f)
                out[i, j] += sgn * (1 + math.log(c))
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


class SentenceTransformerEmbedder(EmbeddingProvider):
    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer  # optional dependency

        self._m = SentenceTransformer(model)
        self.dim = int(self._m.get_sentence_embedding_dimension())
        self.name = f"st-{model}"

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._m.encode(texts, normalize_embeddings=True), dtype=np.float32)


class OllamaEmbedder(EmbeddingProvider):
    def __init__(self, url: str, model: str):
        self.url, self.model = url.rstrip("/"), model
        v = self._one("dimension probe")
        self.dim = len(v)
        self.name = f"ollama-{model}"

    def _one(self, text: str) -> list[float]:
        r = httpx.post(f"{self.url}/api/embeddings", json={"model": self.model, "prompt": text}, timeout=30)
        r.raise_for_status()
        return r.json()["embedding"]

    def embed(self, texts: list[str]) -> np.ndarray:
        arr = np.asarray([self._one(t) for t in texts], dtype=np.float32)
        return arr / np.maximum(np.linalg.norm(arr, axis=1, keepdims=True), 1e-9)


class LLMProvider(ABC):
    name: str
    is_llm: bool = True

    @abstractmethod
    def generate(self, system: str, prompt: str, max_tokens: int = 700) -> str: ...


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model
        self.name = f"anthropic:{model}"

    def generate(self, system: str, prompt: str, max_tokens: int = 700) -> str:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []))


class GeminiProvider(LLMProvider):
    """Google Gemini via the generateContent REST endpoint. The key goes in a header, not the URL,
    so it never appears in access logs."""

    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model
        self.name = f"gemini:{model}"

    def generate(self, system: str, prompt: str, max_tokens: int = 700) -> str:
        r = httpx.post(
            self.URL.format(model=self.model),
            headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
            json={"systemInstruction": {"parts": [{"text": system}]},
                  "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                  "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2}},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates returned")
            raise RuntimeError(f"Gemini returned no answer ({reason})")
        parts = (cands[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)


class OllamaProvider(LLMProvider):
    def __init__(self, url: str, model: str):
        self.url, self.model = url.rstrip("/"), model
        self.name = f"ollama:{model}"

    def generate(self, system: str, prompt: str, max_tokens: int = 700) -> str:
        r = httpx.post(f"{self.url}/api/generate", json={"model": self.model, "system": system, "prompt": prompt,
                                                        "stream": False, "options": {"num_predict": max_tokens}}, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "")


class ExtractiveProvider(LLMProvider):
    """No language model. Picks the retrieved sentences that best overlap the question and
    returns them with their source tags. Used when no LLM is configured."""

    name = "extractive (no LLM configured)"
    is_llm = False

    def generate(self, system: str, prompt: str, max_tokens: int = 700) -> str:
        q = set(tokens(prompt.split("QUESTION:", 1)[-1]))
        scored = []
        for m in re.finditer(r"\[(S\d+)\]\s*(.*?)(?=\n\[S\d+\]|\nQUESTION:|\Z)", prompt, re.S):
            tag, body = m.group(1), m.group(2)
            body = re.sub(r"#+\s*", "", body)
            for sent in _SENT.split(body):
                t = set(tokens(sent))
                if t:
                    scored.append((len(q & t) / (len(t) ** 0.5), sent.strip(), tag))
        scored.sort(key=lambda x: -x[0])
        best = [f"{s} [{tag}]" for sc, s, tag in scored[:3] if sc > 0]
        if not best:
            return "The recovered data does not contain a passage that matches this question."
        return "Most relevant recovered passages (no LLM configured, quoted verbatim):\n- " + "\n- ".join(best)


def _ollama_up(url: str) -> bool:
    try:
        return httpx.get(f"{url.rstrip('/')}/api/tags", timeout=1.5).status_code == 200
    except Exception:
        return False


_cache: dict[str, object] = {}


def get_embedder(s: Settings | None = None) -> EmbeddingProvider:
    s = s or get_settings()
    key = f"emb:{s.embedding_provider}"
    if key in _cache:
        return _cache[key]  # type: ignore[return-value]
    emb: EmbeddingProvider | None = None
    choice = s.embedding_provider
    if choice in ("sentence-transformers", "auto"):
        try:
            emb = SentenceTransformerEmbedder(s.st_model)
        except Exception:
            if choice == "sentence-transformers":
                raise
    if emb is None and choice == "ollama":
        emb = OllamaEmbedder(s.ollama_url, s.ollama_embed_model)
    if emb is None:
        emb = HashingEmbedder()
    _cache[key] = emb
    return emb


def get_llm(s: Settings | None = None) -> LLMProvider:
    s = s or get_settings()
    c = s.llm_provider
    if c == "anthropic" or (c == "auto" and s.anthropic_api_key):
        if not s.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
        return AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
    if c == "gemini" or (c == "auto" and s.gemini_api_key):
        if not s.gemini_api_key:
            raise RuntimeError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
        return GeminiProvider(s.gemini_api_key, s.gemini_model)
    if c == "ollama" or (c == "auto" and _ollama_up(s.ollama_url)):
        return OllamaProvider(s.ollama_url, s.ollama_model)
    return ExtractiveProvider()


def clear_cache() -> None:
    _cache.clear()
