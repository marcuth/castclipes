from castclipes.analysis.constraints import ClipConstraints, enforce, windows
from castclipes.models import ClipCandidate, Transcript, TranscriptSegment


def make_transcript(total: int = 3600, seg: int = 10) -> Transcript:
    return Transcript(
        [TranscriptSegment(i, i + seg, f"frase {i}") for i in range(0, total, seg)], "youtube"
    )


def cand(start: float, end: float, score: float = 0.9) -> ClipCandidate:
    return ClipCandidate(start=start, end=end, topic="t", score=score)


RULES = ClipConstraints(min_seconds=600, max_seconds=1200, min_score=0.6, max_clips=2, edge_padding=0)


def test_respects_max_duration():
    [c] = enforce([cand(100, 2000)], make_transcript(), RULES)
    assert c.duration <= 1200


def test_extends_short_clip_to_min():
    [c] = enforce([cand(100, 200)], make_transcript(), RULES)
    assert 600 <= c.duration <= 1200


def test_drops_when_transcript_too_short():
    assert enforce([cand(0, 100)], make_transcript(300), RULES) == []


def test_pulls_start_back_near_end_of_video():
    [c] = enforce([cand(3500, 3600)], make_transcript(3600), RULES)
    assert c.end == 3600 and c.duration >= 600


def test_drops_low_score_and_overlaps_and_limits():
    cands = [cand(0, 700, 0.9), cand(300, 1000, 0.7), cand(1500, 2200, 0.8),
             cand(2500, 3200, 0.95), cand(3300, 3600, 0.2)]
    result = enforce(cands, make_transcript(), RULES)
    assert [(c.start, c.score) for c in result] == [(0.0, 0.9), (2500.0, 0.95)]


def test_padding_never_exceeds_max():
    rules = ClipConstraints(600, 1200, 0.6, 1, edge_padding=2)
    [c] = enforce([cand(100, 5000)], make_transcript(), rules)
    assert c.duration <= 1200


def test_windows():
    assert windows(1000, 3600, 300) == [(0.0, 1000)]
    w = windows(7200, 3600, 300)
    assert w[0] == (0.0, 3600) and w[-1][1] == 7200 and w[1][0] == 3300
