from jaguar_xiv_missao.editing.silence import Silence, parse_silencedetect, plan_keep_ranges

STDERR = """
[silencedetect @ 0x1] silence_start: 10.5
[silencedetect @ 0x1] silence_end: 13.5 | silence_duration: 3
[silencedetect @ 0x1] silence_start: 50
"""


def test_parse_with_trailing_silence():
    result = parse_silencedetect(STDERR, total_duration=60)
    assert result == [Silence(10.5, 13.5), Silence(50, 60)]


def test_parse_ignores_unfinished_without_duration():
    assert parse_silencedetect(STDERR) == [Silence(10.5, 13.5)]


def test_plan_shortens_long_pauses_and_keeps_short_ones():
    silences = [Silence(10, 13), Silence(20, 20.5)]  # 2ª é curta demais
    keep = plan_keep_ranges(30, silences, min_silence=0.8, keep_padding=0.25)
    assert keep == [(0.0, 10.25), (12.75, 30)]


def test_plan_silence_shorter_than_double_padding_is_untouched():
    keep = plan_keep_ranges(30, [Silence(10, 10.4)], min_silence=0.3, keep_padding=0.25)
    assert keep == [(0.0, 30)]


def test_plan_trailing_silence_cut():
    keep = plan_keep_ranges(30, [Silence(25, 30)], min_silence=0.8, keep_padding=0.25)
    assert keep == [(0.0, 25.25), (29.75, 30)]  # folga mantida nas duas pontas
