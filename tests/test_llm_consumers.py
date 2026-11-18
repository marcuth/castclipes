from castclipes.analysis.constraints import ClipConstraints
from castclipes.analysis.selector import ClipSuggestion, ClipSuggestions, LLMClipSelector
from castclipes.config import Settings
from castclipes.metadata.generator import LLMMetadataGenerator, MetadataSuggestion
from castclipes.models import (
    ClipCandidate,
    ClipFormat,
    SourceVideo,
    Transcript,
    TranscriptSegment,
)


class FakeLLM:
    def __init__(self, response):
        self.response = response

    def generate(self, system, user, output_type):
        if isinstance(self.response, Exception):
            raise self.response
        assert isinstance(self.response, output_type)
        return self.response


def test_selector_converts_and_enforces():
    suggestion = ClipSuggestion(
        start=0, end=700, topic=" A história do primeiro milhão ", hook="Eu quebrei três vezes",
        speakers=["Convidado"], score=0.9, summary="resumo",
    )
    transcript = Transcript([TranscriptSegment(i, i + 10, "x") for i in range(0, 1000, 10)], "youtube")
    rules = ClipConstraints(600, 1200, 0.6, 3, 0)
    selector = LLMClipSelector(
        FakeLLM(ClipSuggestions(clips=[suggestion])), ClipFormat.LONG, rules, 900, 3600, 300
    )
    [clip] = selector.select(SourceVideo(id="v", title="t"), transcript)
    assert clip.topic == "A história do primeiro milhão" and clip.format is ClipFormat.LONG
    assert clip.hook == "Eu quebrei três vezes" and clip.speakers == ("Convidado",)


def test_short_selector_uses_short_prompt_and_format():
    prompts = []

    class Spy(FakeLLM):
        def generate(self, system, user, output_type):
            prompts.append(system)
            return super().generate(system, user, output_type)

    suggestion = ClipSuggestion(start=100, end=140, topic="t", score=0.9)
    transcript = Transcript([TranscriptSegment(i, i + 5, "x") for i in range(0, 600, 5)], "youtube")
    rules = ClipConstraints(20, 85, 0.7, 5, 0.2)
    selector = LLMClipSelector(
        Spy(ClipSuggestions(clips=[suggestion])), ClipFormat.SHORT, rules, 45, 3600, 300
    )
    [clip] = selector.select(SourceVideo(id="v", title="t"), transcript)
    assert clip.format is ClipFormat.SHORT and 20 <= clip.duration <= 85
    assert "SHORT vertical" in prompts[0] and "corte LONGO" not in prompts[0]


def test_metadata_formats_ai_title():
    llm = FakeLLM(MetadataSuggestion(title="o dia em que ele quebrou 3 vezes", summary="s", tags=["MBL", "x"]))
    meta = LLMMetadataGenerator(llm, Settings(_env_file=None)).generate(
        SourceVideo(id="v", title="orig", channel_title="TV"), ClipCandidate(0, 700, "t", 0.9)
    )
    assert meta.title == "O dia em que ele quebrou 3 vezes"
    assert "https://www.youtube.com/watch?v=v" in meta.description and "x" in meta.tags
    assert "#shorts" not in meta.description


def test_metadata_upper_style():
    llm = FakeLLM(MetadataSuggestion(title="fulano reage a vídeo bizarro!", summary="s", tags=[]))
    meta = LLMMetadataGenerator(llm, Settings(_env_file=None, title_style="upper")).generate(
        SourceVideo(id="v", title="orig"), ClipCandidate(0, 700, "t", 0.9)
    )
    assert meta.title == "FULANO REAGE a VÍDEO BIZARRO!"


def test_short_metadata_gets_shorts_hashtag_and_tag():
    llm = FakeLLM(MetadataSuggestion(title="Gancho forte", summary="s", tags=[]))
    cand = ClipCandidate(0, 40, "t", 0.9, ClipFormat.SHORT)
    meta = LLMMetadataGenerator(llm, Settings(_env_file=None)).generate(
        SourceVideo(id="v", title="orig"), cand
    )
    assert "#shorts" in meta.description and "shorts" in meta.tags


def test_metadata_falls_back_when_ai_fails():
    cand = ClipCandidate(0, 700, "assunto do corte", 0.9, speakers=("Fulano",))
    meta = LLMMetadataGenerator(FakeLLM(RuntimeError("x")), Settings(_env_file=None)).generate(
        SourceVideo(id="v", title="orig"), cand
    )
    assert meta.title == "Assunto do corte"
