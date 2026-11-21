import httpx
import pytest

from app.config import settings
from app.providers import ProviderError, embed, generate


def test_openai_embedding_adapter_contract(monkeypatch):
    monkeypatch.setattr(settings(), "embedding_provider", "openai")
    monkeypatch.setattr(settings(), "openai_api_key", "test-only-key")
    captured = {}
    def post(url, **kwargs):
        captured.update(kwargs["json"])
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1]*384}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    assert len(embed(["some text"])[0]) == 384
    assert captured["model"] == settings().openai_embedding_model
    assert captured["dimensions"] == 384


def test_provider_failure_does_not_silently_fallback(monkeypatch):
    monkeypatch.setattr(settings(), "embedding_provider", "openai")
    monkeypatch.setattr(settings(), "openai_api_key", "")
    with pytest.raises(ProviderError, match="missing"):
        embed(["test"])


def test_hosted_generation_rejects_fabricated_citations(monkeypatch):
    monkeypatch.setattr(settings(), "generation_provider", "openai")
    monkeypatch.setattr(settings(), "openai_model", "test-model")
    monkeypatch.setattr(settings(), "openai_api_key", "test-only-key")
    def post(url, **kwargs):
        assert kwargs["json"]["store"] is False
        assert kwargs["json"]["text"]["format"]["strict"] is True
        import json
        payload = {"refused": False, "claims": [{"text": "Refunds are unlimited", "source_id": "chunk-a", "quote": "Fabricated supporting quotation"}]}
        return httpx.Response(200, json={"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    _, citations, refused = generate("What is the refund period?", [{"chunk_id": "chunk-a", "text": "The refund period is thirty days."}])
    assert refused and not citations
