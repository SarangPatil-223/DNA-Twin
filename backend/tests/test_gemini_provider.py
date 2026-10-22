"""Gemini adapter: request shape and response parsing, without calling Google."""
import httpx
import pytest

from app.kb import providers
from app.settings import Settings


class FakeResp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return self._d


def test_gemini_request_and_parse(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json)
        return FakeResp({"candidates": [{"content": {"parts": [{"text": "Answer "}, {"text": "[S1]"}]}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    out = providers.GeminiProvider("k123", "gemini-3.5-flash-lite").generate("sys", "prompt", 50)
    assert out == "Answer [S1]"
    assert seen["url"].endswith("/models/gemini-3.5-flash-lite:generateContent")
    assert "key=" not in seen["url"] and seen["headers"]["x-goog-api-key"] == "k123"
    assert seen["json"]["systemInstruction"]["parts"][0]["text"] == "sys"
    assert seen["json"]["contents"][0]["parts"][0]["text"] == "prompt"
    assert seen["json"]["generationConfig"]["maxOutputTokens"] == 50


def test_gemini_blocked_raises(monkeypatch):
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: FakeResp({"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(RuntimeError, match="SAFETY"):
        providers.GeminiProvider("k", "m").generate("s", "p")


def test_auto_picks_gemini_when_only_gemini_key(monkeypatch, tmp_path):
    for k in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    llm = providers.get_llm(Settings())
    assert isinstance(llm, providers.GeminiProvider) and llm.name.startswith("gemini:")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        providers.get_llm(Settings())
