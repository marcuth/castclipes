import pytest

from jaguar_xiv_missao.ai.factory import create_llm_client
from jaguar_xiv_missao.analysis.triage import TriageVerdict
from jaguar_xiv_missao.config import Settings


def make_client(monkeypatch, outcomes, **overrides):
    settings = Settings(
        _env_file=None, ai_provider="openai", ai_base_url="http://127.0.0.1:1/v1",
        ai_api_key="k", ai_model="m", **overrides,
    )
    client = create_llm_client(settings)
    sleeps: list[float] = []
    client._sleep = sleeps.append
    calls = []

    async def fake_generate(system, user, output_type):
        calls.append(1)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(client, "_generate", fake_generate)
    return client, calls, sleeps


def test_retries_then_succeeds_with_growing_delay(monkeypatch):
    ok = TriageVerdict(score=0.9, reason="ok")
    client, calls, sleeps = make_client(
        monkeypatch, [ValueError("vazio"), ValueError("vazio"), ok],
        ai_max_retries=3, ai_retry_delay_seconds=2, ai_retry_max_delay_seconds=60,
    )
    assert client.generate("s", "u", TriageVerdict) is ok
    assert len(calls) == 3
    assert sleeps == [2, 4]


def test_gives_up_after_max_retries_and_caps_delay(monkeypatch):
    client, calls, sleeps = make_client(
        monkeypatch, [ValueError("falhou")],
        ai_max_retries=3, ai_retry_delay_seconds=10, ai_retry_max_delay_seconds=15,
    )
    with pytest.raises(ValueError, match="falhou"):
        client.generate("s", "u", TriageVerdict)
    assert len(calls) == 4  # 1 + 3 repetições
    assert sleeps == [10, 15, 15]


def test_retry_is_off_by_default(monkeypatch):
    client, calls, sleeps = make_client(monkeypatch, [ValueError("falhou")])
    with pytest.raises(ValueError):
        client.generate("s", "u", TriageVerdict)
    assert len(calls) == 1 and sleeps == []
