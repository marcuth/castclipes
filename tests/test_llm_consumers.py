from jaguar_xiv_missao.analysis.constraints import ClipConstraints
from jaguar_xiv_missao.analysis.selector import ClipSuggestion, ClipSuggestions, LLMClipSelector
from jaguar_xiv_missao.config import Settings
from jaguar_xiv_missao.metadata.generator import LLMMetadataGenerator, MetadataSuggestion
from jaguar_xiv_missao.models import (
    ClipCandidate,
    ClipPattern,
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
        start=0, end=700, topic=" Flávio ", pattern="reaction", speakers=["Renan Santos"],
        target="", score=0.9, summary="resumo",
    )
    transcript = Transcript([TranscriptSegment(i, i + 10, "x") for i in range(0, 1000, 10)], "youtube")
    rules = ClipConstraints(600, 1200, 0.6, 3, 0)
    selector = LLMClipSelector(FakeLLM(ClipSuggestions(clips=[suggestion])), rules, 900, 3600, 300)
    [clip] = selector.select(SourceVideo(id="v", title="t"), transcript)
    assert clip.topic == "Flávio" and clip.pattern is ClipPattern.REACTION
    assert clip.target is None and clip.speakers == ("Renan Santos",)


def test_metadata_formats_ai_title():
    llm = FakeLLM(MetadataSuggestion(title="arthur do val reage a vídeo bizarro!", summary="s", tags=["MBL", "x"]))
    meta = LLMMetadataGenerator(llm, Settings(_env_file=None)).generate(
        SourceVideo(id="v", title="orig", channel_title="TV"), ClipCandidate(0, 700, "t", 0.9)
    )
    assert meta.title == "ARTHUR do VAL REAGE a VÍDEO BIZARRO!"
    assert "https://www.youtube.com/watch?v=v" in meta.description and "x" in meta.tags


def test_metadata_falls_back_when_ai_fails():
    cand = ClipCandidate(0, 700, "assunto", 0.9, ClipPattern.REACTION, ("Arthur do Val",), "Nikolas")
    meta = LLMMetadataGenerator(FakeLLM(RuntimeError("x")), Settings(_env_file=None)).generate(
        SourceVideo(id="v", title="orig"), cand
    )
    assert meta.title == "ARTHUR do VAL REAGE a NIKOLAS!"
