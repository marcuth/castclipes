import itertools

import pytest

from castclipes.analysis.constraints import ClipConstraints
from castclipes.analysis.heuristics import (
    HeuristicClipSelector,
    build_units,
    heat_at,
    keywords,
    score_units,
)
from castclipes.analysis.selector import LLMClipSelector
from castclipes.config import Settings
from castclipes.container import _create_selector
from castclipes.downloader import _heatmap
from castclipes.models import ClipFormat, SourceVideo, Transcript, TranscriptSegment

VIDEO = SourceVideo(id="v", title="t")
FILLER = "então a gente foi lá e ficou conversando sobre outras coisas do dia"
HOT = "Olha só, eu nunca te contei essa história, aconteceu uma coisa inacreditável comigo!"


def transcript(hot_at: set[int], total: int = 600, step: int = 5) -> Transcript:
    """Segmentos de 5 s; os índices em `hot_at` têm texto de alto impacto."""
    segs = [
        TranscriptSegment(t, t + step, HOT if t // step in hot_at else FILLER)
        for t in range(0, total, step)
    ]
    return Transcript(segs, "youtube")


def short_selector(**kw) -> HeuristicClipSelector:
    rules = ClipConstraints(20, 85, 0.3, kw.pop("max_clips", 3), 0)
    return HeuristicClipSelector(ClipFormat.SHORT, rules, 45, **kw)


def test_build_units_groups_short_caption_segments():
    units = build_units(transcript(set(), total=60))
    assert all(6 <= end - start <= 15 for start, end, _ in units[:-1])
    assert units[0][0] == 0 and units[-1][1] == 60


def test_scoring_rewards_hooks_and_blocks_ctas_and_intro():
    raw = [
        (0.0, 8.0, HOT),  # dentro da intro
        (200.0, 208.0, HOT),
        (210.0, 218.0, FILLER),
        (220.0, 228.0, "Gente, se inscreve no canal e deixa o like!"),
    ]
    hot, plain, cta = score_units(raw, skip_intro_seconds=60)[1:]
    intro = score_units(raw, skip_intro_seconds=60)[0]
    assert intro.blocked and intro.score == 0
    assert hot.score > plain.score > 0 and not hot.blocked
    assert cta.blocked and cta.score == 0


def test_short_selector_picks_the_hot_moment_with_hook_first():
    clips = short_selector(skip_intro_seconds=30).select(VIDEO, transcript({40, 41, 42}))  # t = 200..215
    assert clips, "esperava ao menos um short"
    best = max(clips, key=lambda c: c.score)
    assert 185 <= best.start <= 210 and best.format is ClipFormat.SHORT
    assert "Olha só" in best.hook and best.score <= 1.0
    assert 20 <= best.duration <= 85


def test_short_selector_rejects_windows_with_cta_and_flat_video():
    cta = "Então pessoal, se inscreve no canal e ativa o sininho!"
    segs = [TranscriptSegment(t, t + 5, cta if 40 <= t < 60 else FILLER) for t in range(0, 300, 5)]
    for clip in short_selector(skip_intro_seconds=0).select(VIDEO, Transcript(segs, "youtube")):
        assert clip.end <= 40 or clip.start >= 60
    assert short_selector(skip_intro_seconds=0).select(VIDEO, Transcript([], "youtube")) == []


def test_selector_returns_non_overlapping_sorted_clips():
    clips = short_selector(skip_intro_seconds=0, max_clips=3).select(
        VIDEO, transcript({10, 11, 40, 41, 80, 81, 110, 111}, total=900)
    )
    assert 1 < len(clips) <= 3
    assert all(a.end <= b.start for a, b in itertools.pairwise(clips))


def test_long_selector_builds_long_clip_with_keyword_topic():
    text = "Olha só, a gente falou muito sobre empreendedorismo e sobre dinheiro, eu achei incrível."
    segs = [
        TranscriptSegment(t, t + 10, text if (t // 10) % 3 == 0 else FILLER)
        for t in range(0, 4000, 10)
    ]
    rules = ClipConstraints(600, 2400, 0.1, 2, 0)
    selector = HeuristicClipSelector(ClipFormat.LONG, rules, 1320, skip_intro_seconds=60)
    clips = selector.select(VIDEO, Transcript(segs, "youtube"))
    assert clips and all(600 <= c.duration <= 2400 for c in clips)
    assert clips[0].topic.startswith("Conversa sobre")
    assert "empreendedorismo" in clips[0].topic or "dinheiro" in clips[0].topic


def test_heatmap_boosts_matching_units():
    raw = [(100.0, 108.0, FILLER), (200.0, 208.0, FILLER)]
    heat = ((190.0, 215.0, 1.0),)
    cold, warm = score_units(raw, 0, heat)
    assert warm.score > cold.score
    assert heat_at(heat, 0, 50) == 0 and heat_at(heat, 195, 205) == 1.0


def test_ytdlp_heatmap_is_normalized():
    raw = [{"start_time": 0, "end_time": 5, "value": 0.5}, {"start_time": 5, "end_time": 9, "value": 1}]
    assert _heatmap(raw) == ((0.0, 5.0, 0.5), (5.0, 9.0, 1.0))
    assert _heatmap(None) == () and _heatmap([{"x": 1}]) == ()


def test_keywords_ignore_stopwords_and_singletons():
    words = keywords(["empreendedorismo é difícil", "sobre empreendedorismo e dinheiro", "dinheiro"])
    assert words[:2] == ["empreendedorismo", "dinheiro"]


@pytest.mark.parametrize(("engine", "cls"), [("heuristics", HeuristicClipSelector), ("ai", LLMClipSelector)])
def test_factory_picks_selector_by_engine(engine, cls):
    settings = Settings(_env_file=None, selector_engine=engine)
    assert isinstance(_create_selector(settings, object(), ClipFormat.SHORT), cls)
